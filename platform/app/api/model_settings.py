"""系统模型配置 API（只读）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.core.exceptions import bad_request
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.model_settings import ModelSettingsOut
from app.services.model_settings_service import get_model_settings

router = APIRouter(prefix="/admin/model-settings", tags=["admin"])


@router.get("", response_model=ApiResponse[ModelSettingsOut])
def read_model_settings(
    _: Annotated[User, Depends(require_permission("admin.settings"))],
) -> ApiResponse[ModelSettingsOut]:
    return ApiResponse(data=get_model_settings())


@router.put("", response_model=ApiResponse[dict])
def update_model_settings(
    _: Annotated[User, Depends(require_permission("admin.settings"))],
) -> ApiResponse[dict]:
    raise bad_request(
        "模型配置暂不支持在线保存，请修改 platform/.env 中的环境变量并重启平台 API。"
    )
