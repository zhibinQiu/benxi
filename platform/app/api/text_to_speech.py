"""语音合成 API（硅基流动）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user, require_feature
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.text_to_speech import TtsMetaOut, TtsSynthesizeIn
from app.services import text_to_speech_service
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/text-to-speech",
    tags=["text-to-speech"],
    dependencies=[Depends(require_feature("text_to_speech"))],
)


@router.get("/meta", response_model=ApiResponse[TtsMetaOut])
def tts_meta(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[TtsMetaOut]:
    return ApiResponse(data=text_to_speech_service.get_meta(db))


@router.post("/synthesize")
async def synthesize(
    body: TtsSynthesizeIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
) -> Response:
    audio, media_type, fmt = await text_to_speech_service.synthesize(
        db=db,
        text=body.text,
        voice_id=body.voice_id,
        emotion=body.emotion,
        speed=body.speed,
        response_format=body.response_format,
    )
    write_audit(
        db,
        user_id=user.id,
        action="text_to_speech.synthesize",
        resource_type="text_to_speech",
        detail={
            "text_length": len(body.text),
            "voice_id": body.voice_id,
            "emotion": body.emotion,
            "format": fmt,
        },
        ip_address=client_ip,
    )
    filename = f"speech.{fmt}"
    return Response(
        content=audio,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
