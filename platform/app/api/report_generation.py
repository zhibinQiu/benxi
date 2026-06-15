"""报告生成 — 综合 Agent 撰写 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import Response, StreamingResponse

from app.api.deps import get_current_user, require_feature
from app.core.exceptions import bad_request
from app.database import get_db
from app.integrations.markdown_docx_export import (
    build_docx_download_filename,
    markdown_to_docx_bytes,
)
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.report_generation import (
    ReportExportDocxRequest,
    ReportGenerationChatRequest,
    ReportGenerationMetaOut,
    ReportMindmapOut,
    ReportMindmapRequest,
    ReportOptimizePresetOut,
)
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


@router.post("/chat/stream")
async def report_generation_chat_stream(
    body: ReportGenerationChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    async def sse_body():
        async for payload in svc.iter_report_generation_stream(
            db,
            user,
            message=body.message,
            history=body.history,
            conversation_id=body.conversation_id,
            document_ids=body.document_ids,
            use_web_search=body.use_web_search,
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
        data = markdown_to_docx_bytes(title=body.title, markdown_text=body.markdown)
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
