"""辅助写作 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_feature
from app.models.org import User
from app.schemas.assist_writing import (
    AssistPresetOut,
    AssistWritingRequest,
    AssistWritingResponse,
)
from app.schemas.common import ApiResponse
from app.services.assist_writing_service import assist_markdown, list_presets

router = APIRouter(
    prefix="/assist-writing",
    tags=["assist-writing"],
    dependencies=[Depends(require_feature("assist_writing"))],
)


@router.get("/presets", response_model=ApiResponse[list[AssistPresetOut]])
def get_presets(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[AssistPresetOut]]:
    return ApiResponse(
        data=[AssistPresetOut.model_validate(p) for p in list_presets()]
    )


@router.post("/compose", response_model=ApiResponse[AssistWritingResponse])
async def compose(
    body: AssistWritingRequest,
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AssistWritingResponse]:
    result = await assist_markdown(
        markdown=body.markdown,
        instruction=body.instruction,
        preset_id=body.preset_id,
    )
    return ApiResponse(data=AssistWritingResponse.model_validate(result))
