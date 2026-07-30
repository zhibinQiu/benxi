"""本析智能 OpenAI 兼容 API 开关（由小析 orchestrator 的「服务开放」控制）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.agent_profile_service import (
    is_agent_service_enabled,
    patch_agent_profile,
)

ORCHESTRATOR_AGENT_ID = "orchestrator"
OPENAI_API_BASE_PATH = "/api/v1/openai/v1"
OPENAI_API_MODEL = "benxi"
OPENAI_API_AUTH_HINT = (
    "Authorization: Bearer sk-aip-…；"
    "model=benxi 完整 Agent，model=grm 直连默认语言模型"
)


def is_openai_api_enabled(db: Session) -> bool:
    """是否开放本析智能 OpenAI 兼容接口（等同小析服务开放）。"""
    return is_agent_service_enabled(db, ORCHESTRATOR_AGENT_ID)


def get_openai_api_settings(db: Session) -> dict:
    return {
        "enabled": is_openai_api_enabled(db),
        "base_path": OPENAI_API_BASE_PATH,
        "model": OPENAI_API_MODEL,
        "auth_hint": OPENAI_API_AUTH_HINT,
    }


def set_openai_api_enabled(db: Session, enabled: bool) -> dict:
    """同步写入小析 Agent 的 service_enabled。"""
    patch_agent_profile(
        db,
        ORCHESTRATOR_AGENT_ID,
        service_enabled=bool(enabled),
    )
    return get_openai_api_settings(db)
