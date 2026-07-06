"""报告生成 — 综合 Agent 撰写 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import Response, StreamingResponse

from app.api.deps import get_client_ip, get_current_user, require_feature
from app.api.streaming_utils import stream_sse_payloads
from app.core.exceptions import bad_request
from app.database import get_db
from app.integrations.markdown_docx_export import (
    build_docx_download_filename,
    markdown_to_docx_bytes,
)
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.report_generation import (
    ReportAgentSkillOut,
    ReportExportDocxRequest,
    ReportGenerationChatRequest,
    ReportGenerationMetaOut,
    ReportImportLibraryOut,
    ReportImportLibraryRequest,
    ReportMindmapOut,
    ReportMindmapRequest,
    ReportOptimizePresetOut,
)
from app.services import audit_service
from app.services import report_generation_service as svc

router = APIRouter(
    prefix="/report-generation",
    tags=["report-generation"],
    dependencies=[Depends(require_feature("report_generation"))],
)


@router.get("/meta", response_model=ApiResponse[ReportGenerationMetaOut])
def report_generation_meta(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ReportGenerationMetaOut]:
    return ApiResponse(data=ReportGenerationMetaOut.model_validate(svc.get_meta(db)))


@router.get("/presets", response_model=ApiResponse[list[ReportOptimizePresetOut]])
def report_generation_presets(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[ReportOptimizePresetOut]]:
    return ApiResponse(
        data=[
            ReportOptimizePresetOut.model_validate(p) for p in svc.list_optimize_presets()
        ]
    )


@router.get("/skills", response_model=ApiResponse[list[ReportAgentSkillOut]])
def report_generation_skills(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[ReportAgentSkillOut]]:
    return ApiResponse(
        data=[
            ReportAgentSkillOut.model_validate(item)
            for item in svc.list_report_agent_skills(db, user)
        ]
    )


@router.post("/chat/stream")
async def report_generation_chat_stream(
    body: ReportGenerationChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    user_id = user.id

    async def payloads():
        async for payload in svc.iter_report_generation_stream(
            user_id=user_id,
            message=body.message,
            history=body.history,
            conversation_id=body.conversation_id,
            document_ids=body.document_ids,
        ):
            yield payload

    return StreamingResponse(
        stream_sse_payloads(db, payloads),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/mindmap", response_model=ApiResponse[ReportMindmapOut])
def report_generation_mindmap(
    body: ReportMindmapRequest,
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ReportMindmapOut]:
    mermaid, source = svc.generate_report_mindmap(
        question=body.question,
        answer=body.answer,
    )
    if not mermaid:
        raise bad_request("思维导图生成失败，请稍后重试")
    return ApiResponse(data=ReportMindmapOut(mermaid=mermaid, source=source))


@router.post("/export/docx")
def report_generation_export_docx(
    body: ReportExportDocxRequest,
    _: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        data = markdown_to_docx_bytes(
            title=body.title,
            markdown_text=body.markdown,
            for_export=True,
        )
    except Exception as exc:
        raise bad_request(f"Word 导出失败: {exc}") from exc
    filename = build_docx_download_filename(body.title)
    from urllib.parse import quote

    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/import-library", response_model=ApiResponse[ReportImportLibraryOut])
def report_generation_import_library(
    body: ReportImportLibraryRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ReportImportLibraryOut]:
    data = svc.import_report_to_library(
        db,
        user,
        title=body.title,
        markdown=body.markdown,
        sync_knowflow=body.sync_knowflow,
    )
    audit_service.write_audit(
        db,
        user_id=user.id,
        action="report_generation.import_library",
        resource_type="document",
        resource_id=str(data["document_id"]),
        ip_address=get_client_ip(request),
        detail={"title": data.get("title")},
    )
    return ApiResponse(data=ReportImportLibraryOut.model_validate(data))
