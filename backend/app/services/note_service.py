"""工作笔记 — 数据访问层。"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.note import Note, NoteFolder


def new_share_token() -> str:
    """生成公开分享令牌（URL-safe）。"""
    return secrets.token_urlsafe(32)


def ensure_share_token(db: Session, note: Note) -> str:
    """确保笔记有 share_token，缺失则补齐。"""
    if note.share_token:
        return note.share_token
    note.share_token = new_share_token()
    db.commit()
    db.refresh(note)
    return note.share_token or ""


def regenerate_share_token(db: Session, note: Note) -> str:
    """重新生成分享令牌（覆盖旧链接）。"""
    note.share_token = new_share_token()
    db.commit()
    db.refresh(note)
    return note.share_token or ""


def revoke_share_token(db: Session, note: Note) -> None:
    """撤销公开分享链接。"""
    note.share_token = None
    db.commit()
    db.refresh(note)


def get_note_by_share_token(db: Session, share_token: str) -> Note | None:
    """根据公开分享令牌获取笔记。"""
    token = (share_token or "").strip()
    if not token:
        return None
    return db.scalar(select(Note).where(Note.share_token == token))


# ── 文件夹 ──────────────────────────────────────────────────


def list_folders(db: Session, user_id: uuid.UUID) -> list[NoteFolder]:
    stmt = (
        select(NoteFolder)
        .where(NoteFolder.user_id == user_id)
        .order_by(NoteFolder.sort_order.asc(), NoteFolder.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def get_folder_note_counts(
    db: Session, user_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """返回 {folder_id: note_count} 映射（包含无笔记的文件夹）。"""
    from sqlalchemy import func
    stmt = (
        select(NoteFolder.id, func.count(Note.id))
        .outerjoin(Note, Note.folder_id == NoteFolder.id)
        .where(NoteFolder.user_id == user_id)
        .group_by(NoteFolder.id)
    )
    return {row[0]: row[1] for row in db.execute(stmt).all()}


def create_folder(
    db: Session, user_id: uuid.UUID, name: str, parent_id: uuid.UUID | None = None
) -> NoteFolder:
    from sqlalchemy import func

    max_order = db.scalar(
        select(func.max(NoteFolder.sort_order)).where(NoteFolder.user_id == user_id)
    ) or 0
    sort_order = max_order + 1

    folder = NoteFolder(
        user_id=user_id, name=name, parent_id=parent_id, sort_order=sort_order
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def update_folder(
    db: Session, user_id: uuid.UUID, folder_id: uuid.UUID, **kwargs
) -> NoteFolder | None:
    folder = db.get(NoteFolder, folder_id)
    if not folder or folder.user_id != user_id:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(folder, k):
            setattr(folder, k, v)
    folder.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, user_id: uuid.UUID, folder_id: uuid.UUID) -> bool:
    folder = db.get(NoteFolder, folder_id)
    if not folder or folder.user_id != user_id:
        return False
    # 将文件夹内的笔记移出
    stmt = (
        update(Note)
        .where(Note.folder_id == folder_id)
        .values(folder_id=None)
    )
    db.execute(stmt)
    # 子文件夹 parent 置空
    stmt2 = (
        update(NoteFolder)
        .where(NoteFolder.parent_id == folder_id)
        .values(parent_id=None)
    )
    db.execute(stmt2)
    db.delete(folder)
    db.commit()
    return True


# ── 笔记 ──────────────────────────────────────────────────────


def list_notes(
    db: Session, user_id: uuid.UUID, folder_id: uuid.UUID | None = None
) -> list[Note]:
    stmt = select(Note).where(Note.user_id == user_id)
    if folder_id is not None:
        stmt = stmt.where(Note.folder_id == folder_id)
    stmt = stmt.order_by(
        Note.is_pinned.desc(),
        Note.sort_order.asc(),
        Note.updated_at.desc(),
    )
    return list(db.scalars(stmt).all())


def get_note(db: Session, user_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
    note = db.get(Note, note_id)
    if not note or note.user_id != user_id:
        return None
    return note


def create_note(
    db: Session,
    user_id: uuid.UUID,
    *,
    folder_id: uuid.UUID | None = None,
    title: str = "",
    content: str = "",
) -> Note:
    note = Note(
        user_id=user_id,
        folder_id=folder_id,
        title=title,
        content=content,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def update_note(
    db: Session, user_id: uuid.UUID, note_id: uuid.UUID, **kwargs
) -> Note | None:
    note = db.get(Note, note_id)
    if not note or note.user_id != user_id:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(note, k):
            setattr(note, k, v)
    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


def delete_note(db: Session, user_id: uuid.UUID, note_id: uuid.UUID) -> bool:
    note = db.get(Note, note_id)
    if not note or note.user_id != user_id:
        return False
    db.delete(note)
    db.commit()
    return True


def batch_delete_notes(
    db: Session, user_id: uuid.UUID, note_ids: list[uuid.UUID]
) -> int:
    """批量删除笔记，返回实际删除数量。"""
    from sqlalchemy import delete as sa_delete

    stmt = (
        sa_delete(Note)
        .where(Note.user_id == user_id)
        .where(Note.id.in_(note_ids))
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
