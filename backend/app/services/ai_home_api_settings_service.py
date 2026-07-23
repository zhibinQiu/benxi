"""本析智能 OpenAI 兼容 API 平台开关。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.platform_ai_home_settings import SINGLETON_ID, PlatformAiHomeSettings


def _ensure_row(db: Session) -> PlatformAiHomeSettings:
    row = db.get(PlatformAiHomeSettings, SINGLETON_ID)
    if row is None:
        row = PlatformAiHomeSettings(id=SINGLETON_ID, openai_api_enabled=False)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def is_openai_api_enabled(db: Session) -> bool:
    return bool(_ensure_row(db).openai_api_enabled)


def get_openai_api_settings(db: Session) -> dict:
    row = _ensure_row(db)
    return {
        "enabled": bool(row.openai_api_enabled),
        "base_path": "/api/v1/openai/v1",
        "model": "benxi",
        "auth_hint": (
            "Authorization: Bearer sk-aip-…；"
            "model=benxi 完整 Agent，model=grm 直连默认语言模型"
        ),
    }


def set_openai_api_enabled(db: Session, enabled: bool) -> dict:
    row = _ensure_row(db)
    row.openai_api_enabled = bool(enabled)
    db.commit()
    db.refresh(row)
    return get_openai_api_settings(db)
