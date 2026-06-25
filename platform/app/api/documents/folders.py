from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.document import (
    KbFolderCreate,
    KbFolderListOut,
    KbFolderOut,
    KbFolderUpdate,
)
from app.services import library_folder_service
from app.core.platform_cache import invalidate_document_caches

router = APIRouter()

@router.get("/kb-folders", response_model=ApiResponse[KbFolderListOut])
def list_kb_folders(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    scope: str = Query(..., pattern="^(company|department|team|personal)$"),
    dept_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> ApiResponse[KbFolderListOut]:
    data = library_folder_service.list_kb_folders(
        db, user, scope=scope, dept_id=dept_id, owner_id=owner_id
    )
    return ApiResponse(
        data=KbFolderListOut(
            scope=data["scope"],
            dept_id=data["dept_id"],
            can_manage_folders=data["can_manage_folders"],
            items=[KbFolderOut.model_validate(i) for i in data["items"]],
        )
    )


@router.post("/kb-folders", response_model=ApiResponse[KbFolderOut])
def create_kb_folder(
    body: KbFolderCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KbFolderOut]:
    folder = library_folder_service.create_kb_folder(
        db,
        user,
        name=body.name,
        description=body.description,
        scope=body.scope,
        dept_id=body.dept_id,
        owner_id=body.owner_id,
    )
    db.commit()
    invalidate_document_caches(str(user.id))
    return ApiResponse(
        data=KbFolderOut(
            id=folder.id,
            name=folder.name,
            description=folder.description or "",
            scope=folder.scope,
            dept_id=folder.dept_id,
            kind="normal",
            is_system=False,
            document_count=0,
            can_manage=True,
        )
    )


@router.patch("/kb-folders/{folder_id}", response_model=ApiResponse[KbFolderOut])
def update_kb_folder(
    folder_id: uuid.UUID,
    body: KbFolderUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KbFolderOut]:
    folder = library_folder_service.update_kb_folder(
        db,
        user,
        folder_id,
        name=body.name,
        description=body.description,
    )
    db.commit()
    invalidate_document_caches(str(user.id))
    return ApiResponse(
        data=KbFolderOut(
            id=folder.id,
            name=folder.name,
            description=folder.description or "",
            scope=folder.scope,
            dept_id=folder.dept_id,
            kind="normal",
            is_system=False,
            document_count=0,
            can_manage=True,
        )
    )


@router.delete("/kb-folders/{folder_id}", response_model=ApiResponse[dict])
def delete_kb_folder(
    folder_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict]:
    library_folder_service.delete_kb_folder(db, user, folder_id)
    db.commit()
    invalidate_document_caches(str(user.id))
    return ApiResponse(data={"ok": True})

