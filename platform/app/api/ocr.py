"""OCR 识别 — 平台 PaddleOCR-VL / layout-parsing 服务。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user, require_feature
from app.core.exceptions import bad_request
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.ocr import OcrExportIn, OcrMetaOut, OcrRecognizeOut
from app.services import ocr_service
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/ocr",
    tags=["ocr"],
    dependencies=[Depends(require_feature("ocr"))],
)


@router.get("/meta", response_model=ApiResponse[OcrMetaOut])
def ocr_meta(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[OcrMetaOut]:
    return ApiResponse(data=ocr_service.get_meta(db))


@router.post("/recognize", response_model=ApiResponse[OcrRecognizeOut])
async def recognize_ocr(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(..., description="图像或 PDF"),
    language: Annotated[str | None, Form()] = None,
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> ApiResponse[OcrRecognizeOut]:
    content = await file.read()
    if not content:
        raise bad_request("空文件")
    try:
        result = ocr_service.recognize_file(
            db,
            content=content,
            file_name=file.filename or "upload.bin",
            mime_type=file.content_type,
            language=language,
        )
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    except ConnectionError as exc:
        raise bad_request(str(exc)) from exc
    except RuntimeError as exc:
        raise bad_request(str(exc)) from exc

    write_audit(
        db,
        user_id=user.id,
        action="ocr.recognize",
        resource_type="ocr",
        detail={
            "filename": file.filename,
            "text_length": len(result.text),
            "model": result.model,
            "blocks": len(result.blocks),
        },
        ip_address=client_ip,
    )
    return ApiResponse(data=result)


@router.post("/export")
def export_ocr_results(
    body: OcrExportIn,
    _: Annotated[User, Depends(get_current_user)],
) -> Response:
    if not body.items:
        raise bad_request("无导出内容")
    data = ocr_service.build_export_zip(body)
    suffix = "md" if body.format == "markdown" else "json"
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=ocr-export-{suffix}.zip",
        },
    )
