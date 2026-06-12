"""系统资源配置 API（模型、服务、知识库基础设施等）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.model_settings import (
    ModelSettingsOut,
    ModelSettingsUpdate,
    ResourceHealthItemOut,
    ResourceHealthOut,
    ResourceHealthTestIn,
)
from app.services.model_settings_service import get_model_settings, save_model_settings
from app.services.resource_health_service import (
    TESTABLE_RESOURCE_IDS,
    check_resource_health,
    check_single_resource_health,
    merge_health_test_config,
    _normalize_resource_id,
)

router = APIRouter(prefix="/admin/model-settings", tags=["admin"])


@router.get("", response_model=ApiResponse[ModelSettingsOut])
def read_model_settings(
    _: Annotated[User, Depends(require_permission("admin.settings"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ModelSettingsOut]:
    return ApiResponse(data=get_model_settings(db))


@router.put("", response_model=ApiResponse[ModelSettingsOut])
def update_model_settings(
    body: ModelSettingsUpdate,
    _: Annotated[User, Depends(require_permission("admin.settings"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ModelSettingsOut]:
    return ApiResponse(data=save_model_settings(db, body))


@router.get("/health", response_model=ApiResponse[ResourceHealthOut])
def read_resource_health(
    _: Annotated[User, Depends(require_permission("admin.settings"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ResourceHealthOut]:
    raw = check_resource_health(db)
    items = {key: ResourceHealthItemOut(**val) for key, val in raw.items()}
    return ApiResponse(data=ResourceHealthOut(items=items))


@router.post("/health/test", response_model=ApiResponse[ResourceHealthItemOut])
def test_resource_health(
    body: ResourceHealthTestIn,
    _: Annotated[User, Depends(require_permission("admin.settings"))],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ResourceHealthItemOut]:
    """保存前按表单草稿探测单项连通性。"""
    rid = _normalize_resource_id(body.resource_id)
    if rid not in TESTABLE_RESOURCE_IDS:
        from app.core.exceptions import bad_request

        raise bad_request(f"不支持测试的资源项：{body.resource_id}")
    draft = body.draft.model_dump(exclude_unset=True)
    for old, new in (
        ("vision_base_url", "vl_base_url"),
        ("vision_api_key", "vl_api_key"),
        ("vision_model", "vl_model"),
    ):
        if old in draft and new not in draft:
            draft[new] = draft[old]
    cfg = merge_health_test_config(db, draft)
    item = check_single_resource_health(rid, cfg, db)
    return ApiResponse(data=ResourceHealthItemOut(**item))
