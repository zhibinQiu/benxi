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
    create_kb_folder,
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
    if name in (WEB_FAVORITES_FOLDER_NAME, "资讯管理"):
        folder = ensure_web_favorites_folder(db, user, owner_id=user.id)
        return folder.id, False
    folders = list_document_folders_for_agent(db, user, scope=scope)
    matched = [f for f in folders if (f.get("name") or "").strip() == name]
    if not matched:
        raise bad_request(f"未找到文件夹「{name}」，请先调用 list_document_folders")
    fid = matched[0].get("id")
    return (uuid.UUID(str(fid)) if fid else None), False


def search_documents_by_name_for_agent(
    db: Session,
    user: User,
    *,
    name: str,
    scope: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """按文档标题关键词搜索当前用户可见的文档（默认跨分级）。"""
    limit = max(1, min(int(limit or 20), 50))
    kw = (name or "").strip()
    if not kw:
        raise bad_request("请提供文档名称关键词")
    scope_val = (scope or "").strip() or None
    docs = filter_accessible_documents(
        db,
        user,
        keyword=kw,
        scope=scope_val,
        min_permission_level=PermissionLevel.visible.value,
    )
    return [_serialize_document_summary(db, user, d) for d in docs[:limit]]


def read_document_content_for_agent(
    db: Session,
    user: User,
    *,
    document_id: uuid.UUID | None = None,
    document_name: str | None = None,
    max_chars: int = 16000,
) -> dict[str, Any]:
    """读取平台文档库中已上传文档的解析正文（当前版本）。"""
    from app.core.document_scope import can_read_document
    from app.services.document_service import get_document, resolve_current_version

    doc_id = document_id
    if doc_id is None:
        name = (document_name or "").strip()
        if not name:
            raise bad_request("请提供 document_id 或 document_name")
        matches = search_documents_by_name_for_agent(db, user, name=name, limit=5)
        if not matches:
            raise not_found(f"未找到标题含「{name}」的文档")
        if len(matches) > 1:
            options = "；".join(
                f"{m.get('title') or '?'}({m.get('id')})" for m in matches[:5]
            )
            raise bad_request(f"匹配到 {len(matches)} 份文档，请指定 document_id：{options}")
        doc_id = uuid.UUID(str(matches[0]["id"]))

    doc = get_document(db, doc_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在或已删除")
    if not can_read_document(db, user, doc):
        raise forbidden("无权阅读该文档")
    if not resolve_current_version(db, doc):
        raise bad_request("文档尚未上传文件，无法读取正文")

    from app.services.pageindex_service import get_pageindex_document_content

    payload = get_pageindex_document_content(db, user, doc_id)
    parse_source = "pageindex"
    if not payload:
        from app.services.compare_service import get_document_content

        payload = get_document_content(db, user, doc_id)
        parse_source = "parsed"
    full_text = str(payload.get("full_text") or "")
    limit = max(500, min(int(max_chars or 16000), 80000))
    truncated = len(full_text) > limit
    text_out = full_text[:limit] if truncated else full_text
    total_chars = int(payload.get("char_count") or len(full_text))

    return {
        "document_id": str(doc_id),
        "title": doc.title,
        "file_name": payload.get("file_name"),
        "char_count": total_chars,
        "returned_chars": len(text_out),
        "truncated": truncated,
        "parse_quality": payload.get("parse_quality"),
        "warning": payload.get("warning"),
        "parse_source": parse_source,
        "full_text": text_out,
        "message": (
            f"已读取「{doc.title}」正文 {len(text_out)} 字"
            + (f"（全文共 {total_chars} 字，已截断）" if truncated else "")
            + ("（PageIndex）" if parse_source == "pageindex" else "")
        ),
    }


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
    """列出用户可见的平台文档库文档（含按文件夹筛选，如「资讯管理」）。"""
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


def _resolve_create_folder_id(
    db: Session,
    user: User,
    *,
    scope: str,
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
    dept_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    if folder_id is not None:
        return folder_id
    name = (folder_name or "").strip()
    if not name or name in ("未分类", "uncategorized", "none", "null"):
        return None
    folders = list_document_folders_for_agent(
        db, user, scope=scope, dept_id=dept_id
    )
    matched = [f for f in folders if (f.get("name") or "").strip() == name]
    if not matched:
        raise bad_request(f"未找到文件夹「{name}」，请先调用 list_document_folders 或 create_kb_folder")
    fid = matched[0].get("id")
    return uuid.UUID(str(fid)) if fid else None


def create_kb_folder_for_agent(
    db: Session,
    user: User,
    *,
    name: str,
    scope: str = "personal",
    description: str = "",
    dept_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """在文档库中新建文件夹。"""
    scope = (scope or "personal").strip() or "personal"
    folder = create_kb_folder(
        db,
        user,
        name=name,
        description=description,
        scope=scope,
        dept_id=dept_id,
        owner_id=user.id if scope == "personal" else None,
    )
    db.commit()
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return {
        "id": str(folder.id),
        "name": folder.name,
        "scope": folder.scope,
        "message": f"已创建文件夹「{folder.name}」",
    }


def create_library_document_for_agent(
    db: Session,
    user: User,
    *,
    title: str,
    content: str,
    scope: str = "personal",
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
    description: str = "",
    content_format: str = "markdown",
) -> dict[str, Any]:
    """将文本/Markdown 写入文档库（新建文档并上传首版）。"""
    from app.core.document_scope import resolve_create_params
    from app.services.library_folder_service import resolve_document_folder_id

    label = (title or "").strip()
    if not label:
        raise bad_request("文档标题不能为空")
    body = str(content or "")
    if not body.strip():
        raise bad_request("文档内容不能为空")

    scope = (scope or "personal").strip() or "personal"
    norm_scope, norm_dept = resolve_create_params(
        db, user, scope=scope, dept_id=None
    )
    target_folder_id = _resolve_create_folder_id(
        db,
        user,
        scope=norm_scope,
        folder_id=folder_id,
        folder_name=folder_name,
        dept_id=norm_dept,
    )
    if folder_id is not None or folder_name:
        target_folder_id = resolve_document_folder_id(
            db,
            user,
            scope=norm_scope,
            folder_id=target_folder_id,
            dept_id=norm_dept,
        )

    fmt = (content_format or "markdown").strip().casefold()
    if fmt in ("md", "markdown", "text/markdown"):
        file_name = f"{label[:120]}.md"
        mime_type = "text/markdown"
        payload = body.encode("utf-8")
    elif fmt in ("txt", "plain", "text", "text/plain"):
        file_name = f"{label[:120]}.txt"
        mime_type = "text/plain"
        payload = body.encode("utf-8")
    else:
        raise bad_request("content_format 仅支持 markdown 或 plain")

    doc = document_service.create_document(
        db,
        user,
        title=label,
        description=(description or "").strip(),
        scope=norm_scope,
        dept_id=norm_dept,
        folder_id=target_folder_id,
    )
    document_service.create_initial_uploaded_version(
        db,
        doc,
        user,
        file_name=file_name,
        mime_type=mime_type,
        content=payload,
    )
    db.commit()
    db.refresh(doc)
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    folder_label = folder_name or ("未分类" if not target_folder_id else str(target_folder_id))
    return {
        "id": str(doc.id),
        "title": doc.title,
        "scope": doc.scope,
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "file_name": file_name,
        "message": f"已将「{doc.title}」写入文档库（{folder_label}）",
    }


def update_kb_folder_for_agent(
    db: Session,
    user: User,
    *,
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
    scope: str = "personal",
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    from app.services.library_folder_service import update_kb_folder

    scope = (scope or "personal").strip() or "personal"
    fid = _resolve_create_folder_id(
        db,
        user,
        scope=scope,
        folder_id=folder_id,
        folder_name=folder_name,
    )
    if fid is None:
        raise bad_request("请指定要修改的文件夹")
    folder = update_kb_folder(
        db,
        user,
        fid,
        name=name,
        description=description,
    )
    db.commit()
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return {
        "id": str(folder.id),
        "name": folder.name,
        "message": f"已更新文件夹「{folder.name}」",
    }


def delete_kb_folder_for_agent(
    db: Session,
    user: User,
    *,
    folder_id: uuid.UUID | None = None,
    folder_name: str | None = None,
    scope: str = "personal",
    confirm: bool = False,
) -> dict[str, Any]:
    from app.services.library_folder_service import delete_kb_folder

    if not confirm:
        raise bad_request("删除文件夹需显式设置 confirm=true")
    scope = (scope or "personal").strip() or "personal"
    fid = _resolve_create_folder_id(
        db,
        user,
        scope=scope,
        folder_id=folder_id,
        folder_name=folder_name,
    )
    if fid is None:
        raise bad_request("请指定要删除的文件夹")
    delete_kb_folder(db, user, fid)
    db.commit()
    from app.core.platform_cache import invalidate_document_caches

    invalidate_document_caches(str(user.id))
    return {"message": "已删除文件夹", "folder_id": str(fid)}


def sync_document_knowledge_for_agent(
    db: Session,
    user: User,
    *,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """将文档导入/同步到知识库（与文档详情「同步知识库」相同）。"""
    from app.core.document_scope import can_read_document
    from app.core.user_messages import (
        KNOWLEDGE_SERVICE_UNAVAILABLE,
        KNOWLEDGE_SYNC_DISABLED,
        KNOWLEDGE_SYNC_FAILED,
    )
    from app.domains.knowledge import knowledge
    from app.services.document_service import get_document, resolve_current_version
    from app.services.knowledge_sync_job_service import enqueue_document_knowledge_index

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在或已删除")
    if not can_read_document(db, user, doc):
        raise forbidden("无权访问该文档")
    if not resolve_current_version(db, doc):
        raise bad_request("文档尚未上传文件，无法同步知识库")
    if not knowledge.enabled():
        raise bad_request(KNOWLEDGE_SYNC_DISABLED)
    if not knowledge.stack_reachable():
        raise bad_request(KNOWLEDGE_SERVICE_UNAVAILABLE)

    job = enqueue_document_knowledge_index(
        db,
        user_id=user.id,
        document_id=doc.id,
        version_id=doc.current_version_id,
        force=True,
        document_title=doc.title,
    )
    if not job:
        raise bad_request(KNOWLEDGE_SYNC_FAILED)
    db.commit()
    return {
        "document_id": str(doc.id),
        "title": doc.title,
        "knowledge_job_id": str(job.id),
        "message": "已加入后台任务，正在同步并解析知识库，请在「后台任务」查看进度。",
    }


def reindex_document_for_agent(
    db: Session,
    user: User,
    *,
    document_id: uuid.UUID,
    parser_id: str | None = None,
    resync: bool = False,
) -> dict[str, Any]:
    from app.services.knowledge_library_service import reindex_document

    result = reindex_document(
        db,
        user,
        document_id,
        parser_id=parser_id,
        resync=resync,
    )
    db.commit()
    return {
        **result,
        "message": result.get("message")
        or "已加入后台任务，正在重新索引，请在「后台任务」查看进度。",
    }
