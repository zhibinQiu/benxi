"""工作笔记 API — 文件夹与笔记 CRUD。"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.note import (
    ImageUploadOut,
    NoteBatchDelete,
    NoteCreate,
    NoteFolderCreate,
    NoteFolderOut,
    NoteFolderUpdate,
    NoteOut,
    NotePolishIn,
    NotePolishOut,
    NotePublishIn,
    NotePublishOut,
    NoteShareIn,
    NoteShareOut,
    NoteSummaryOut,
    NoteUpdate,
)
from app.services import note_service as svc

router = APIRouter(
    prefix="/notes",
    tags=["notes"],
    dependencies=[Depends(require_feature("notes"))],
)

# 公开分享：无登录、无功能权限依赖
public_router = APIRouter(prefix="/share/notes", tags=["note-share"])


# ── 文件夹 ─────────────────────────────────────────────────────


@router.get("/folders", response_model=ApiResponse)
def list_folders(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """获取用户的所有文件夹。"""
    folders = svc.list_folders(db, user.id)
    note_counts = svc.get_folder_note_counts(db, user.id)
    out = [
        NoteFolderOut(
            **{
                "id": f.id,
                "name": f.name,
                "parent_id": f.parent_id,
                "sort_order": f.sort_order,
                "created_at": f.created_at,
                "updated_at": f.updated_at,
                "note_count": note_counts.get(f.id, 0),
            }
        )
        for f in folders
    ]
    return ApiResponse(data=out)


@router.post("/folders", response_model=ApiResponse)
def create_folder(
    body: NoteFolderCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """创建文件夹。"""
    parent_id = uuid.UUID(body.parent_id) if body.parent_id else None
    folder = svc.create_folder(db, user.id, name=body.name, parent_id=parent_id)
    return ApiResponse(data=NoteFolderOut.model_validate(folder))


@router.put("/folders/{folder_id}", response_model=ApiResponse)
def update_folder(
    folder_id: uuid.UUID,
    body: NoteFolderUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """更新文件夹。"""
    kwargs = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.parent_id is not None:
        kwargs["parent_id"] = uuid.UUID(body.parent_id) if body.parent_id else None
    folder = svc.update_folder(db, user.id, folder_id, **kwargs)
    if not folder:
        return ApiResponse(code=404, message="文件夹不存在")
    return ApiResponse(data=NoteFolderOut.model_validate(folder))


@router.delete("/folders/{folder_id}", response_model=ApiResponse)
def delete_folder(
    folder_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """删除文件夹（笔记移出）。"""
    ok = svc.delete_folder(db, user.id, folder_id)
    return ApiResponse(data={"deleted": ok})


# ── 笔记 ───────────────────────────────────────────────────────


@router.get("", response_model=ApiResponse)
def list_notes(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    folder_id: str | None = None,
) -> ApiResponse:
    """获取用户的笔记列表。"""
    fid = uuid.UUID(folder_id) if folder_id else None
    notes = svc.list_notes(db, user.id, folder_id=fid)
    out = [NoteSummaryOut.model_validate(n) for n in notes]
    return ApiResponse(data=out)


@router.get("/{note_id}", response_model=ApiResponse)
def get_note(
    note_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """获取单篇笔记详情（含正文）。"""
    note = svc.get_note(db, user.id, note_id)
    if not note:
        return ApiResponse(code=404, message="笔记不存在")
    return ApiResponse(data=NoteOut.model_validate(note))


@router.post("", response_model=ApiResponse)
def create_note(
    body: NoteCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """创建笔记。"""
    folder_id = uuid.UUID(body.folder_id) if body.folder_id else None
    note = svc.create_note(
        db, user.id, folder_id=folder_id, title=body.title, content=body.content
    )
    return ApiResponse(data=NoteOut.model_validate(note))


@router.put("/{note_id}", response_model=ApiResponse)
def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """更新笔记。"""
    kwargs = {}
    if body.title is not None:
        kwargs["title"] = body.title
    if body.content is not None:
        kwargs["content"] = body.content
    if body.folder_id is not None:
        kwargs["folder_id"] = uuid.UUID(body.folder_id) if body.folder_id else None
    if body.is_pinned is not None:
        kwargs["is_pinned"] = body.is_pinned
    note = svc.update_note(db, user.id, note_id, **kwargs)
    if not note:
        return ApiResponse(code=404, message="笔记不存在")
    return ApiResponse(data=NoteOut.model_validate(note))


@router.delete("/{note_id}", response_model=ApiResponse)
def delete_note(
    note_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """删除笔记。"""
    ok = svc.delete_note(db, user.id, note_id)
    return ApiResponse(data={"deleted": ok})


@router.post("/{note_id}/share", response_model=ApiResponse)
def share_note(
    note_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    body: NoteShareIn | None = None,
) -> ApiResponse:
    """生成笔记公开分享令牌；默认重新生成以覆盖旧链接。"""
    note = svc.get_note(db, user.id, note_id)
    if not note:
        return ApiResponse(code=404, message="笔记不存在")
    regenerate = True if body is None else bool(body.regenerate)
    if regenerate or not note.share_token:
        token = svc.regenerate_share_token(db, note)
    else:
        token = svc.ensure_share_token(db, note)
    return ApiResponse(data=NoteShareOut(share_token=token))


@router.delete("/{note_id}/share", response_model=ApiResponse)
def unshare_note(
    note_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """撤销笔记公开分享链接。"""
    note = svc.get_note(db, user.id, note_id)
    if not note:
        return ApiResponse(code=404, message="笔记不存在")
    svc.revoke_share_token(db, note)
    return ApiResponse(data={"share_token": None})


def _import_note_to_library_job(
    user_id: uuid.UUID, title: str, content: str
) -> None:
    """后台：将笔记 Markdown 导入个人文档库。"""
    from app.database import SessionLocal
    from app.services.report_generation_service import import_report_to_library

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            return
        import_report_to_library(
            db,
            user,
            title=title or "工作笔记",
            markdown=content or "",
            description="由工作笔记导入",
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "note import library failed user=%s", user_id
        )
    finally:
        db.close()


@router.post("/{note_id}/publish", response_model=ApiResponse)
def publish_note(
    note_id: uuid.UUID,
    body: NotePublishIn,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """发布笔记：可选导入文档库（后台）与生成/覆盖分享链接。"""
    if not body.to_library and not body.share_link:
        return ApiResponse(code=400, message="请至少选择一项")

    note = svc.get_note(db, user.id, note_id)
    if not note:
        return ApiResponse(code=404, message="笔记不存在")

    share_token = None
    library_queued = False
    parts: list[str] = []

    if body.share_link:
        share_token = svc.regenerate_share_token(db, note)
        parts.append("已生成分享链接")

    if body.to_library:
        background_tasks.add_task(
            _import_note_to_library_job,
            user.id,
            note.title or "工作笔记",
            note.content or "",
        )
        library_queued = True
        parts.append("正在后台发布到文档库")

    return ApiResponse(
        data=NotePublishOut(
            share_token=share_token,
            library_queued=library_queued,
            message="；".join(parts),
        )
    )


@public_router.get("/{share_token}", response_class=HTMLResponse)
def view_shared_note(
    share_token: str,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """公开分享页：无需登录即可查看笔记。"""
    from app.services.note_share_render import render_note_html

    note = svc.get_note_by_share_token(db, share_token)
    if not note:
        return HTMLResponse(content="<h1>笔记不存在或链接已失效</h1>", status_code=404)
    try:
        note.view_count = int(note.view_count or 0) + 1
        db.commit()
        db.refresh(note)
    except Exception:
        db.rollback()
    html = render_note_html(
        note.content or "",
        title=note.title or "无标题笔记",
        updated_at=note.updated_at,
        view_count=int(note.view_count or 0),
    )
    return HTMLResponse(content=html)


_NOTE_POLISH_SYSTEM = (
    "你是中文 Markdown 润色助手。"
    "润色用户提供的中文 Markdown 文本：改进语句通顺度与用词，保留原有结构与语义。"
    "不要增删章节层级，不要添加解释性前后缀。"
    "只输出润色后的 Markdown 正文，不要用代码围栏包裹。"
)


@router.post("/polish", response_model=ApiResponse)
async def polish_note_content(
    body: NotePolishIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """AI 润色笔记 Markdown 正文（可带润色方向）。"""
    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    if not is_configured():
        return ApiResponse(code=503, message="AI 服务未配置")

    content = (body.content or "").strip()
    if not content:
        return ApiResponse(code=400, message="内容不能为空")

    direction = (body.direction or "").strip()
    system = _NOTE_POLISH_SYSTEM
    if direction:
        system = (
            f"{_NOTE_POLISH_SYSTEM}\n"
            f"用户指定的润色方向：{direction}\n"
            "请在不违背上述约束的前提下，按该方向润色。"
        )

    user_payload = content
    if direction:
        user_payload = f"【润色方向】{direction}\n\n【待润色内容】\n{content}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_payload},
    ]
    choice = await chat_completion_message_async(
        messages=messages, temperature=0.3, timeout=120.0
    )
    if not choice:
        return ApiResponse(code=502, message="润色失败，请稍后重试")

    msg = choice.get("message") or {}
    polished = str(msg.get("content") or "").strip()
    if not polished:
        return ApiResponse(code=502, message="润色结果为空")

    if polished.startswith("```") and polished.endswith("```"):
        lines = polished.split("\n")
        if len(lines) >= 3:
            polished = "\n".join(lines[1:-1]).strip()

    return ApiResponse(data=NotePolishOut(content=polished))


@router.post("/batch-delete", response_model=ApiResponse)
def batch_delete_notes(
    body: NoteBatchDelete,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse:
    """批量删除笔记。"""
    ids = [uuid.UUID(i) for i in body.ids if i]
    if not ids:
        return ApiResponse(code=400, message="未提供要删除的 ID")
    count = svc.batch_delete_notes(db, user.id, ids)
    return ApiResponse(data={"deleted_count": count})


# ── 图片上传 ───────────────────────────────────────────────────


@router.post("/images", response_model=ApiResponse)
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiResponse:
    """上传粘贴的图片文件。"""
    data_root = os.environ.get("DATA_ROOT", "./data")
    upload_dir = os.path.join(data_root, "notes_images", str(user.id))
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "image.png")[1] or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)

    content = await file.read()

    def _write():
        with open(filepath, "wb") as f:
            f.write(content)

    await asyncio.to_thread(_write)

    url = f"/api/v1/notes/images/{user.id}/{filename}"
    return ApiResponse(data=ImageUploadOut(url=url))


@router.get("/images/{user_id}/{filename}")
async def get_image(
    user_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """获取已上传的笔记图片。"""
    data_root = os.environ.get("DATA_ROOT", "./data")
    filepath = os.path.join(data_root, "notes_images", user_id, filename)

    real = os.path.realpath(filepath)
    allowed_base = os.path.realpath(os.path.join(data_root, "notes_images"))
    if not real.startswith(allowed_base):
        return Response(status_code=403)

    if not os.path.isfile(real):
        return Response(status_code=404)

    ext = os.path.splitext(filename)[1].lower()
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")

    return FileResponse(real, media_type=media_type)

