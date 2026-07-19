"""文档公开分享 API（鉴权生成令牌 + 免登录预览）。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.documents.serializers import inline_disposition
from app.core.document_scope import can_modify_document
from app.core.exceptions import bad_request, forbidden, not_found
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.services import document_service
from app.services.documents import share as share_svc
from app.services.document_share_render import render_document_share_html

router = APIRouter()
public_router = APIRouter(prefix="/share/documents", tags=["document-share"])


class DocumentShareIn(BaseModel):
    regenerate: bool = Field(True, description="是否重新生成令牌（覆盖旧链接）")


class DocumentShareOut(BaseModel):
    share_token: str


@router.post("/{document_id}/share", response_model=ApiResponse[DocumentShareOut])
def create_document_share(
    document_id: uuid.UUID,
    body: DocumentShareIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentShareOut]:
    """生成/覆盖文档公开分享令牌（可修改权限）。"""
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在")
    if not can_modify_document(db, user, doc):
        raise forbidden("无权生成分享链接")
    version = document_service.resolve_current_version(db, doc)
    if not version or not document_service.is_version_uploaded(version):
        raise bad_request("文档尚未上传文件，无法生成分享链接")
    if body.regenerate or not doc.share_token:
        token = share_svc.regenerate_share_token(db, doc)
    else:
        token = share_svc.ensure_share_token(db, doc)
    return ApiResponse(data=DocumentShareOut(share_token=token))


@router.delete("/{document_id}/share", response_model=ApiResponse)
def revoke_document_public_share(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse:
    """撤销文档公开分享链接。"""
    doc = document_service.get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found("文档不存在")
    if not can_modify_document(db, user, doc):
        raise forbidden("无权取消分享链接")
    share_svc.revoke_share_token(db, doc)
    return ApiResponse(data={"share_token": None})


@public_router.get("/{share_token}", response_class=HTMLResponse)
def view_shared_document(
    share_token: str,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """公开分享页：无需登录即可预览最新版本。"""
    doc = share_svc.get_document_by_share_token(db, share_token)
    if not doc:
        return HTMLResponse(content="<h1>文档不存在或链接已失效</h1>", status_code=404)
    try:
        _data, file_name, mime, version = share_svc.read_shared_document_file(db, doc)
    except Exception:
        return HTMLResponse(content="<h1>文档文件不可用</h1>", status_code=404)
    # 与前端 getDocumentShareUrl / getNoteShareUrl 一致，走 /ai 反代前缀
    file_url = f"/ai/api/v1/share/documents/{share_token}/file"
    html = render_document_share_html(
        title=doc.title or "文档",
        file_name=file_name,
        mime_type=mime,
        file_size=int(version.file_size or 0),
        updated_at=doc.updated_at or version.created_at,
        file_url=file_url,
    )
    return HTMLResponse(content=html)


@public_router.get("/{share_token}/file")
def download_shared_document_file(
    share_token: str,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """公开分享文件流：始终返回当前最新版本（inline 便于预览）。"""
    doc = share_svc.get_document_by_share_token(db, share_token)
    if not doc:
        raise not_found("文档不存在或链接已失效")
    content, file_name, mime, _version = share_svc.read_shared_document_file(db, doc)
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": inline_disposition(file_name)},
    )
