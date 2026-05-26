"""知识问答 — 平台内嵌 KnowFlow / RAGFlow 自带 Web UI；可选 API 供后续文档同步。"""

from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.config import get_settings
from app.database import get_db
from app.integrations.knowflow_client import get_knowflow_client_for_user, knowflow_stack_reachable
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.rag import RagAskRequest, RagDocumentOut, RagSessionCreate, RagSessionOut
from app.services import rag_service
from app.services.compare_service import list_compare_documents
from app.services.ragflow_identity_service import build_embed_session, resolve_ui_embed_base
from app.services.ragflow_naming import dataset_name_for_user

router = APIRouter(
    prefix="/rag",
    tags=["rag"],
    dependencies=[Depends(require_feature("rag_qa"))],
)


def _ragflow_ui_available(url: str) -> bool:
    try:
        with httpx.Client(timeout=3.0, follow_redirects=True) as client:
            r = client.get(url.rstrip("/") + "/")
            if r.status_code >= 500:
                return False
            # :9380 若直连 Python API，根路径会返回 JSON 404，不是 Web UI
            ct = (r.headers.get("content-type") or "").lower()
            if "html" in ct or r.text.lstrip().startswith("<"):
                return True
            return False
    except Exception:
        return False


@router.get("/meta")
def rag_meta(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    settings = get_settings()
    kf = get_knowflow_client_for_user(db, user)
    direct = settings.knowflow_ui_url.rstrip("/")
    embed_base = resolve_ui_embed_base()
    check_url = direct if embed_base.startswith("http") else direct
    ui_available = _ragflow_ui_available(check_url)
    stack_on = settings.knowflow_enabled and knowflow_stack_reachable()
    mode = (settings.knowflow_ui_embed_mode or "iframe").strip().lower()
    if mode not in ("iframe", "redirect"):
        mode = "iframe"
    ui_hint = ""
    if settings.knowflow_enabled and not ui_available:
        ui_hint = "知识问答 Web 服务未响应，请联系管理员检查服务状态。"
    elif not settings.knowflow_enabled:
        ui_hint = "知识问答未启用，请联系管理员在平台配置中开启。"
    return ApiResponse(
        data={
            "knowflow_enabled": stack_on,
            "knowflow_ready": kf.enabled(),
            "health": kf.health(),
            "integration_phase": 4,
            "ui_embed_url": f"{embed_base}/",
            "ui_direct_url": direct,
            "ui_embed_mode": mode,
            "ui_available": ui_available,
            "ui_hint": ui_hint,
            "dataset_name": dataset_name_for_user(user.id),
            "features": [
                "knowflow_native_ui",
                "citation_trace",
                "pdf_page_bbox",
                "knowflow_api",
                "per_user_dataset",
                "sso_auto_login",
                "doc_sync",
                "ui_whitelabel",
            ],
        }
    )


@router.get("/embed-session")
def rag_embed_session(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    """平台登录用户嵌入 KnowFlow（阶段 2 将返回 authorization）。"""
    data = build_embed_session(db, user)
    db.commit()
    return ApiResponse(data=data)


@router.get("/documents", response_model=ApiResponse[PageResult[RagDocumentOut]])
def list_rag_documents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
) -> ApiResponse[PageResult[RagDocumentOut]]:
    rows, total = list_compare_documents(
        db, user, page=page, page_size=page_size, keyword=keyword
    )
    items = [
        RagDocumentOut(
            id=r["id"],
            title=r["title"],
            file_name=r["file_name"],
            file_size=r["file_size"],
            updated_at=r.get("updated_at"),
        )
        for r in rows
    ]
    return ApiResponse(data=PageResult(items=items, total=total, page=page, page_size=page_size))


@router.get("/sessions")
def list_sessions(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> ApiResponse[dict]:
    items, total = rag_service.list_user_sessions(
        db, user.id, page=page, page_size=page_size
    )
    return ApiResponse(
        data={
            "items": [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "document_ids": s.document_ids,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/sessions", response_model=ApiResponse[RagSessionOut])
def create_session(
    body: RagSessionCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[RagSessionOut]:
    session = rag_service.create_session(
        db,
        user,
        document_ids=body.document_ids,
        title=body.title,
    )
    data = rag_service.session_to_dict(db, session)
    data["knowflow"] = get_knowflow_client_for_user(db, user).health()
    return ApiResponse(data=data)


@router.get("/sessions/{session_id}", response_model=ApiResponse[RagSessionOut])
def get_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[RagSessionOut]:
    sid = uuid.UUID(session_id)
    session = rag_service.get_user_session(db, sid, user.id)
    if not session:
        from app.core.exceptions import not_found

        raise not_found("会话不存在")
    data = rag_service.session_to_dict(db, session)
    data["knowflow"] = get_knowflow_client_for_user(db, user).health()
    return ApiResponse(data=data)


@router.post("/sessions/{session_id}/ask", response_model=ApiResponse[dict])
def ask_session(
    session_id: str,
    body: RagAskRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    sid = uuid.UUID(session_id)
    session = rag_service.get_user_session(db, sid, user.id)
    if not session:
        from app.core.exceptions import not_found

        raise not_found("会话不存在")
    msg = rag_service.ask(db, session, user, body.question)
    return ApiResponse(
        data={
            "message": {
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations or [],
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            },
            "knowflow": get_knowflow_client_for_user(db, user).health(),
        }
    )
