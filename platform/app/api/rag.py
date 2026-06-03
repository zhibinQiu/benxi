"""知识问答 API — 薄控制器，业务编排见 app.domains.knowledge。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.domains.knowledge import knowledge
from app.integrations.knowflow_client import get_knowflow_client_for_user
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.knowledge_search import (
    KnowledgeSearchHitOut,
    KnowledgeSearchOut,
    KnowledgeSearchRequest,
)
from app.schemas.rag import RagAskRequest, RagDocumentOut, RagSessionCreate, RagSessionOut
from app.services import rag_service
from app.services.compare_service import list_compare_documents
from app.services.knowledge_search_service import search_knowledge

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/meta", dependencies=[Depends(require_feature("rag_qa"))])
def rag_meta(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    return ApiResponse(data=knowledge.meta_payload(db, user))


@router.post(
    "/search",
    response_model=ApiResponse[KnowledgeSearchOut],
    dependencies=[Depends(require_feature("knowledge_search"))],
)
def knowledge_search(
    body: KnowledgeSearchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeSearchOut]:
    data = search_knowledge(
        db,
        user,
        query=body.query,
        scope=body.scope,
        limit=body.limit,
    )
    return ApiResponse(
        data=KnowledgeSearchOut(
            query=data["query"],
            hits=[KnowledgeSearchHitOut.model_validate(h) for h in data["hits"]],
            knowflow_enabled=data["knowflow_enabled"],
            search_mode=data["search_mode"],
        )
    )


@router.get("/embed-session", dependencies=[Depends(require_feature("rag_qa"))])
def rag_embed_session(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    sync: bool | None = Query(
        None,
        description="是否全量同步 KnowFlow 目录；默认读配置，false 可加快 iframe 首屏",
    ),
) -> ApiResponse[dict]:
    data = knowledge.build_embed_session(db, user, sync_catalog=sync)
    db.commit()
    return ApiResponse(data=data)


@router.get(
    "/documents",
    response_model=ApiResponse[PageResult[RagDocumentOut]],
    dependencies=[Depends(require_feature("rag_qa"))],
)
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


@router.get("/sessions", dependencies=[Depends(require_feature("rag_qa"))])
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


@router.post(
    "/sessions",
    response_model=ApiResponse[RagSessionOut],
    dependencies=[Depends(require_feature("rag_qa"))],
)
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


@router.get(
    "/sessions/{session_id}",
    response_model=ApiResponse[RagSessionOut],
    dependencies=[Depends(require_feature("rag_qa"))],
)
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


@router.post(
    "/sessions/{session_id}/ask",
    response_model=ApiResponse[dict],
    dependencies=[Depends(require_feature("rag_qa"))],
)
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
