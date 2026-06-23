"""本析智能 — 文档库管理工具（仅对当前用户具可修改权限的文档生效）。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.document_scope import (
    can_delete_document,
    can_grant_document_permissions,
    can_modify_document,
)
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import LEVEL_ORDER, PermissionLevel, normalize_permission_level
from app.models.org import User
from app.services import document_service
from app.services.documents.listing import filter_accessible_documents
from app.core.permissions import PermissionLevel
from app.services.documents.listing import filter_accessible_documents
from app.services.library_folder_service import (
    WEB_FAVORITES_FOLDER_NAME,
    ensure_web_favorites_folder,
    list_kb_folders,
)


def _require_manageable(db: Session, user: User, document_id: uuid.UUID):
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在或已删除")
    if not can_modify_document(db, user, doc):
        raise forbidden("无权管理该文档")
    return doc


def _serialize_document_summary(db: Session, user: User, doc) -> dict[str, Any]:
    folder_name = None
    if doc.folder_id:
        from app.models.document import DocumentLibraryFolder

        folder = db.get(DocumentLibraryFolder, doc.folder_id)
        folder_name = folder.name if folder else None
    return {
        "id": str(doc.id),
        "title": doc.title,
        "scope": doc.scope or "personal",
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "folder_name": folder_name,
        "can_share": can_grant_document_permissions(db, user, doc),
    }


def _resolve_agent_folder_filter(
    db: Session,
    user: User,
    *,
    scope: str,
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
) -> tuple[uuid.UUID | None, bool]:
    """解析文件夹筛选：返回 (folder_id, uncategorized_only)。"""
    if folder_id is not None:
        return folder_id, False
    name = (folder_name or "").strip()
    if not name:
        return None, False
    if name in ("未分类", "uncategorized", "none", "null"):
        return None, True
    if name in (WEB_FAVORITES_FOLDER_NAME, "网站收藏"):
        folder = ensure_web_favorites_folder(db, user, owner_id=user.id)
        return folder.id, False
    folders = list_document_folders_for_agent(db, user, scope=scope)
    matched = [f for f in folders if (f.get("name") or "").strip() == name]
    if not matched:
        raise bad_request(f"未找到文件夹「{name}」，请先调用 list_document_folders")
    fid = matched[0].get("id")
    return (uuid.UUID(str(fid)) if fid else None), False


def list_library_documents_for_agent(
    db: Session,
    user: User,
    *,
    scope: str = "personal",
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
    keyword: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """列出用户可见的平台文档库文档（含按文件夹筛选，如「网页收藏」）。"""
    scope = (scope or "personal").strip() or "personal"
    limit = max(1, min(int(limit or 30), 50))
    kw = (keyword or "").strip() or None
    target_folder_id, uncategorized_only = _resolve_agent_folder_filter(
        db,
        user,
        scope=scope,
        folder_id=folder_id,
        folder_name=folder_name,
    )
    docs = filter_accessible_documents(
        db,
        user,
        keyword=kw,
        scope=scope,
        min_permission_level=PermissionLevel.visible.value,
        folder_id=target_folder_id,
        uncategorized_only=uncategorized_only,
    )
    return [_serialize_document_summary(db, user, d) for d in docs[:limit]]


def list_manageable_documents(
    db: Session,
    user: User,
    *,
    keyword: str | None = None,
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
    scope: str = "personal",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """列出当前用户拥有可修改（完全管理）权限的文档。"""
    scope = (scope or "personal").strip() or "personal"
    limit = max(1, min(int(limit or 20), 50))
    kw = (keyword or "").strip() or None
    target_folder_id, uncategorized_only = _resolve_agent_folder_filter(
        db,
        user,
        scope=scope,
        folder_id=folder_id,
        folder_name=folder_name,
    )
    docs = filter_accessible_documents(
        db,
        user,
        keyword=kw,
        scope=scope,
        min_permission_level=PermissionLevel.modify.value,
        folder_id=target_folder_id,
        uncategorized_only=uncategorized_only,
    )
    return [_serialize_document_summary(db, user, d) for d in docs[:limit]]


def list_document_folders_for_agent(
    db: Session,
    user: User,
    *,
    scope: str,
    dept_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    scope = (scope or "").strip()
    if not scope:
        raise bad_request("请提供 scope")
    payload = list_kb_folders(db, user, scope=scope, dept_id=dept_id)
    items = payload.get("items") if isinstance(payload, dict) else []
    out: list[dict[str, Any]] = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        kind = row.get("kind")
        if kind == "shared":
            continue
        fid = row.get("id")
        out.append(
            {
                "id": str(fid) if fid else None,
                "name": row.get("name") or "",
                "scope": scope,
                "kind": kind or "normal",
                "is_system": bool(row.get("is_system")),
            }
        )
    return out


def _resolve_folder_id(
    db: Session,
    user: User,
    doc,
    *,
    folder_id: uuid.UUID | None,
    folder_name: str | None,
) -> uuid.UUID | None:
    if folder_id is not None:
        return folder_id
    name = (folder_name or "").strip()
    if not name or name in ("未分类", "uncategorized", "none", "null"):
        return None
    folders = list_document_folders_for_agent(
        db, user, scope=doc.scope or "personal", dept_id=doc.dept_id
    )
    matched = [f for f in folders if (f.get("name") or "").strip() == name]
    if not matched:
        raise bad_request(f"未找到文件夹「{name}」，请先调用 list_document_folders")
    fid = matched[0].get("id")
    return uuid.UUID(str(fid)) if fid else None


def rename_document_for_agent(
    db: Session,
    user: User,
    *,
    document_id: uuid.UUID,
    new_title: str,
) -> dict[str, Any]:
    doc = _require_manageable(db, user, document_id)
    title = (new_title or "").strip()
    if not title:
        raise bad_request("新标题不能为空")
    doc = document_service.update_document(db, user, doc, title=title)
    return {
        "id": str(doc.id),
        "title": doc.title,
        "message": f"已将文档重命名为「{doc.title}」",
    }


def move_document_for_agent(
    db: Session,
    user: User,
    *,
    document_id: uuid.UUID,
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
) -> dict[str, Any]:
    doc = _require_manageable(db, user, document_id)
    target_folder_id = _resolve_folder_id(
        db, user, doc, folder_id=folder_id, folder_name=folder_name
    )
    doc = document_service.move_document_to_folder(
        db, user, doc, folder_id=target_folder_id
    )
    folder_label = folder_name or ("未分类" if not target_folder_id else str(target_folder_id))
    return {
        "id": str(doc.id),
        "title": doc.title,
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "message": f"已将「{doc.title}」移动到 {folder_label}",
    }


def delete_document_for_agent(
    db: Session,
    user: User,
    *,
    document_id: uuid.UUID,
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        raise bad_request("删除文档需显式设置 confirm=true")
    doc = document_service.get_document(db, document_id)
    if not doc:
        raise not_found("文档不存在")
    if not can_delete_document(db, user, doc):
        raise forbidden("无权删除该文档")
    title = doc.title
    document_service.permanently_delete_document(db, user, doc, defer_knowflow=True)
    return {
        "id": str(document_id),
        "title": title,
        "message": f"已永久删除文档「{title}」",
    }


def _resolve_share_user_ids(
    db: Session,
    document,
    identifiers: list[str],
) -> list[uuid.UUID]:
    from app.models.org import User as UserModel

    raw = [str(x).strip() for x in identifiers if str(x).strip()]
    if not raw:
        raise bad_request("请提供要分享的用户姓名或账号")
    candidates = document_service.list_acl_user_candidates(db, document)
    by_name: dict[str, uuid.UUID] = {}
    for row in candidates:
        uid = row.get("id")
        if not uid:
            continue
        for key in ("username", "display_name"):
            label = str(row.get(key) or "").strip().casefold()
            if label:
                by_name.setdefault(label, uid)
    resolved: list[uuid.UUID] = []
    missing: list[str] = []
    for ident in raw:
        key = ident.casefold()
        uid = by_name.get(key)
        if uid:
            resolved.append(uid)
            continue
        partial = [
            row["id"]
            for row in candidates
            if key in str(row.get("display_name") or "").casefold()
            or key in str(row.get("username") or "").casefold()
        ]
        if len(partial) == 1:
            resolved.append(partial[0])
        else:
            missing.append(ident)
    if missing:
        raise bad_request(f"无法唯一匹配用户：{', '.join(missing)}")
    if not resolved:
        raise bad_request("未匹配到可分享的用户")
    return list(dict.fromkeys(resolved))


def share_document_for_agent(
    db: Session,
    user: User,
    *,
    document_id: uuid.UUID,
    user_names: list[str],
    level: str = "query",
) -> dict[str, Any]:
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在或已删除")
    if not can_grant_document_permissions(db, user, doc):
        raise forbidden("无权分享该文档")
    norm = normalize_permission_level(level)
    if norm not in LEVEL_ORDER:
        raise bad_request("分享级别无效，可选：visible、query、modify")
    user_ids = _resolve_share_user_ids(db, doc, user_names)
    shares = document_service.set_document_shares(
        db, user, doc, user_ids=user_ids, level=norm
    )
    labels = [s.get("user_name") or str(s.get("user_id")) for s in shares]
    return {
        "id": str(doc.id),
        "title": doc.title,
        "level": norm,
        "shared_with": labels,
        "message": f"已将「{doc.title}」分享给 {len(user_ids)} 人（{norm}）",
    }
