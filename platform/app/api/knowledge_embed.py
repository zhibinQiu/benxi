"""知识库原生 API：分级库、文档树、切片与问答（不嵌入 KnowFlow 前端）。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.database import get_db
from app.domains.knowledge import knowledge
from app.models.org import User
from app.schemas.common import ApiResponse, PageResult
from app.schemas.knowledge_library import (
    KnowledgeChunksOut,
    KnowledgeLibraryDocumentOut,
    KnowledgeLibraryListOut,
    KnowledgeLibraryOut,
    KnowledgeQaAskRequest,
    KnowledgeQaChatStreamRequest,
    KnowledgeQaMindmapOut,
    KnowledgeQaMindmapRequest,
    KnowledgeQaSessionCreate,
    KnowledgeReindexRequest,
    KnowledgeScopeTreeOut,
)
from app.schemas.rag import RagSessionOut
from app.services import rag_service
from app.services.knowledge_library_service import (
    list_document_chunks,
    list_knowledge_libraries,
    list_library_documents,
    reindex_document,
)
from app.services.knowledge_parser_service import list_parser_options
from app.services.knowledge_qa_service import (
    fetch_citation_image_bytes,
    fetch_citation_preview_bytes,
    generate_knowledge_mindmap,
    iter_knowledge_qa_stream,
)
from app.services.knowledge_scope_tree_service import build_knowledge_scope_tree

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_knowledge_search = Depends(require_feature("knowledge_search"))


@router.get("/meta")
def knowledge_meta(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    return ApiResponse(data=knowledge.meta_payload(db, user))


@router.get("/embed-session")
def knowledge_embed_session(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    sync: bool | None = Query(
        None,
        description="是否同步 KnowFlow 分级库；默认 false，登录后已在后台同步",
    ),
) -> ApiResponse[dict]:
    data = knowledge.build_embed_session(db, user, sync_catalog=sync)
    db.commit()
    return ApiResponse(data=data)


@router.get(
    "/libraries",
    response_model=ApiResponse[KnowledgeLibraryListOut],
    dependencies=[_knowledge_search],
)
def knowledge_libraries(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeLibraryListOut]:
    data = list_knowledge_libraries(db, user)
    return ApiResponse(
        data=KnowledgeLibraryListOut(
            items=[KnowledgeLibraryOut.model_validate(x) for x in data.get("items") or []],
            knowflow_enabled=bool(data.get("knowflow_enabled")),
        )
    )


@router.get(
    "/scope-tree",
    response_model=ApiResponse[KnowledgeScopeTreeOut],
    dependencies=[_knowledge_search],
)
def knowledge_scope_tree(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    refresh: bool = Query(False, description="跳过服务端缓存，拉取最新索引状态"),
) -> ApiResponse[KnowledgeScopeTreeOut]:
    data = build_knowledge_scope_tree(db, user, force_refresh=refresh)
    return ApiResponse(data=KnowledgeScopeTreeOut.model_validate(data))


@router.get(
    "/libraries/{dataset_id}/documents",
    response_model=ApiResponse[PageResult[KnowledgeLibraryDocumentOut]],
    dependencies=[_knowledge_search],
)
def knowledge_library_documents(
    dataset_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    keyword: str | None = None,
    folder_id: uuid.UUID | None = None,
    virtual_folder: str | None = None,
) -> ApiResponse[PageResult[KnowledgeLibraryDocumentOut]]:
    rows, total = list_library_documents(
        db,
        user,
        dataset_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        folder_id=folder_id,
        virtual_folder=virtual_folder,
    )
    return ApiResponse(
        data=PageResult(
            items=[KnowledgeLibraryDocumentOut.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/documents/{document_id}/chunks",
    response_model=ApiResponse[KnowledgeChunksOut],
    dependencies=[_knowledge_search],
)
def knowledge_document_chunks(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    version_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    keywords: str | None = None,
) -> ApiResponse[KnowledgeChunksOut]:
    data = list_document_chunks(
        db,
        user,
        document_id,
        version_id=version_id,
        page=page,
        page_size=page_size,
        keywords=keywords,
    )
    return ApiResponse(data=KnowledgeChunksOut.model_validate(data))


@router.get(
    "/parsers",
    dependencies=[_knowledge_search],
)
def knowledge_parsers() -> ApiResponse[dict]:
    return ApiResponse(data=list_parser_options())


@router.post(
    "/documents/{document_id}/reindex",
    dependencies=[_knowledge_search],
)
def knowledge_document_reindex(
    document_id: uuid.UUID,
    body: KnowledgeReindexRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    data = reindex_document(
        db,
        user,
        document_id,
        version_id=body.version_id,
        parser_id=body.parser_id,
        layout_recognize=body.layout_recognize,
        resync=body.resync,
    )
    db.commit()
    return ApiResponse(data=data)


@router.get(
    "/citations/preview",
    dependencies=[_knowledge_search],
)
def knowledge_citation_preview(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    image_id: str | None = Query(None),
    chunk_id: str | None = Query(None),
    dataset_id: str | None = Query(None),
    ragflow_document_id: str | None = Query(None),
    document_id: str | None = Query(None, description="平台文档 ID，用于定位 PDF"),
    page: int | None = Query(None, ge=1),
    bbox: str | None = Query(None, description="高亮框 left,right,top,bottom（RAGFlow 格式）"),
    bbox_format: str | None = Query(None, description="bbox 坐标格式，默认 auto"),
    snippet: str | None = Query(None, max_length=800, description="引用片段，用于无 bbox 时文本层高亮"),
) -> Response:
    """返回引用在源 PDF 中的 KnowFlow 切片截图（非提取文本）。"""
    from app.core.exceptions import not_found
    from app.services.knowledge_qa_service import parse_citation_bbox_param

    doc_uuid = None
    if document_id:
        try:
            doc_uuid = uuid.UUID(document_id.strip())
        except ValueError:
            doc_uuid = None

    result = fetch_citation_preview_bytes(
        db,
        user,
        image_id=image_id,
        chunk_id=chunk_id,
        dataset_id=dataset_id,
        ragflow_document_id=ragflow_document_id,
        platform_document_id=doc_uuid,
        page=page,
        bbox=parse_citation_bbox_param(bbox),
        bbox_format=(bbox_format or "auto").strip() or "auto",
        highlight_text=snippet,
    )
    if not result:
        raise not_found(
            "引用原文截图不可用：当前文档可能以 Markdown 分块方式索引，未生成页级快照。"
            "PDF / Word / Excel / 文本等请在文档详情 → 知识索引中勾选「重新同步」后重试。"
        )
    data, content_type = result
    return Response(content=data, media_type=content_type)


@router.get(
    "/citations/images/{image_id:path}",
    dependencies=[_knowledge_search],
)
def knowledge_citation_image(
    image_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    from app.core.exceptions import not_found

    result = fetch_citation_image_bytes(db, user, image_id)
    if not result:
        raise not_found(
            "引用原文截图不可用：当前文档可能以 Markdown 分块方式索引，未生成页级快照。"
            "PDF / Word / Excel / 文本等请在文档详情 → 知识索引中勾选「重新同步」后重试。"
        )
    data, content_type = result
    return Response(content=data, media_type=content_type)


@router.post(
    "/qa/sessions",
    response_model=ApiResponse[RagSessionOut],
    dependencies=[_knowledge_search],
)
def create_knowledge_qa_session(
    body: KnowledgeQaSessionCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[RagSessionOut]:
    session = rag_service.create_session(
        db,
        user,
        document_ids=body.document_ids,
        title=body.title,
    )
    return ApiResponse(data=rag_service.session_to_dict(db, session))


@router.post(
    "/qa/sessions/{session_id}/ask",
    response_model=ApiResponse[dict],
    dependencies=[_knowledge_search],
)
def ask_knowledge_qa_session(
    session_id: str,
    body: KnowledgeQaAskRequest,
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
            "session_id": session_id,
            "message": {
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations or [],
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            },
        }
    )


@router.post(
    "/qa/chat/stream",
    dependencies=[_knowledge_search],
)
async def knowledge_qa_chat_stream(
    body: KnowledgeQaChatStreamRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    async def sse_body():
        async for payload in iter_knowledge_qa_stream(
            db,
            user,
            question=body.message,
            session_id=body.conversation_id,
            document_ids=body.document_ids,
        ):
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        sse_body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/qa/mindmap",
    response_model=ApiResponse[KnowledgeQaMindmapOut],
    dependencies=[_knowledge_search],
)
def knowledge_qa_mindmap(
    body: KnowledgeQaMindmapRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KnowledgeQaMindmapOut]:
    mermaid = generate_knowledge_mindmap(question=body.question, answer=body.answer)
    source = "llm"
    if not mermaid:
        from app.services.knowledge_mindmap_service import build_mindmap_from_answer

        mermaid = build_mindmap_from_answer(body.question, body.answer)
        source = "local"
    if not mermaid:
        from app.core.exceptions import bad_request

        raise bad_request("思维导图生成失败，请稍后重试")
    return ApiResponse(data=KnowledgeQaMindmapOut(mermaid=mermaid, source=source))
