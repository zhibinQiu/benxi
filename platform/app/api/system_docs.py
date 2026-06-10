"""系统说明文档 API（Markdown + 静态资源）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.core.exceptions import not_found
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.system_docs import SystemDocContentOut, SystemDocGroupOut
from app.services import system_docs_service

router = APIRouter(prefix="/system/docs", tags=["system-docs"])


@router.get("/catalog", response_model=ApiResponse[list[SystemDocGroupOut]])
def doc_catalog(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[SystemDocGroupOut]]:
    return ApiResponse(data=system_docs_service.list_doc_catalog())


@router.get("/content", response_model=ApiResponse[SystemDocContentOut])
def doc_content(
    _: Annotated[User, Depends(get_current_user)],
    path: Annotated[str, Query(min_length=1, max_length=512)],
) -> ApiResponse[SystemDocContentOut]:
    try:
        data = system_docs_service.read_doc_content(path)
    except ValueError as exc:
        raise not_found(str(exc)) from exc
    except FileNotFoundError as exc:
        raise not_found(f"Document not found: {path}") from exc
    return ApiResponse(data=SystemDocContentOut.model_validate(data))


@router.get("/assets/{asset_path:path}")
def doc_asset(
    _: Annotated[User, Depends(get_current_user)],
    asset_path: str,
) -> FileResponse:
    try:
        full, mime = system_docs_service.resolve_doc_asset(asset_path)
    except (ValueError, FileNotFoundError) as exc:
        raise not_found(str(exc)) from exc
    return FileResponse(full, media_type=mime, filename=full.name)
