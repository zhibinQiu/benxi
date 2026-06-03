"""切片管理 / KnowFlow 嵌入（全体登录用户，不依赖编码管理权限）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.domains.knowledge import knowledge
from app.models.org import User
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


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
