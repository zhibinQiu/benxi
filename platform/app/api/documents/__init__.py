"""文档库 REST API（按域拆分子路由）。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.documents import access, crud, delete, folders, listing, sync, upload, versions
from app.api.documents.listing import create_document, list_documents
from app.schemas.common import ApiResponse, PageResult
from app.schemas.document import DocumentDetail, DocumentListItem

router = APIRouter(prefix="/documents", tags=["documents"])
router.get("", response_model=ApiResponse[PageResult[DocumentListItem]])(list_documents)
router.post("", response_model=ApiResponse[DocumentDetail])(create_document)
router.include_router(folders.router)
router.include_router(listing.router)
router.include_router(crud.router)
router.include_router(upload.router)
router.include_router(sync.router)
router.include_router(access.router)
router.include_router(versions.router)
router.include_router(delete.router)
