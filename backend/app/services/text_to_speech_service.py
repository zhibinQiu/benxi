"""语音合成业务层。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.integrations.siliconflow_tts_client import (
    DEFAULT_FORMAT,
    EMOTION_PROMPTS,
    MAX_INPUT_CHARS,
    SUPPORTED_FORMATS,
    SYSTEM_VOICES,
    is_configured,
    synthesize_speech,
)
from app.schemas.text_to_speech import TtsMetaOut, TtsVoiceOut

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_EMOTION_OPTIONS = [
    {"id": "happy", "label": "高兴"},
    {"id": "excited", "label": "兴奋"},
    {"id": "sad", "label": "悲伤"},
    {"id": "angry", "label": "愤怒"},
    {"id": "gentle", "label": "温柔"},
]


def get_meta(db: Session | None = None) -> TtsMetaOut:
    from app.integrations.siliconflow_tts_client import resolve_tts_settings

    _, _, model_name = resolve_tts_settings(db)
    display_model = model_name if is_configured(db) else ""
    return TtsMetaOut(
        configured=is_configured(db),
        provider="",
        model=display_model,
        max_input_chars=MAX_INPUT_CHARS,
        supported_formats=list(SUPPORTED_FORMATS),
        default_format=DEFAULT_FORMAT,
        voices=[TtsVoiceOut.model_validate(v) for v in SYSTEM_VOICES],
        emotions=_EMOTION_OPTIONS,
    )


async def synthesize(
    *,
    db: Session | None,
    text: str,
    voice_id: str = "alex",
    emotion: str | None = None,
    speed: float = 1.0,
    response_format: str = DEFAULT_FORMAT,
) -> tuple[bytes, str, str]:
    if emotion and emotion not in EMOTION_PROMPTS:
        emotion = None
    valid_voice_ids = {v["id"] for v in SYSTEM_VOICES}
    vid = voice_id if voice_id in valid_voice_ids else "alex"
    audio, media_type = await synthesize_speech(
        db=db,
        text=text,
        voice_id=vid,
        emotion=emotion,
        speed=speed,
        response_format=response_format,
    )
    fmt = (response_format or DEFAULT_FORMAT).strip().lower()
    return audio, media_type, fmt
