"""GB/Z 185.4 智能体能力描述（ACDL 精简）。"""

from __future__ import annotations

from app.config import get_settings
from app.core.agent_profiles import AGENT_PROFILES, AgentProfileDef, get_agent_profile
from app.core.aip.aid import build_agent_aid
from app.core.aip.types import AipAgentDescription, AipCapability


def _capability_for_profile(defn: AgentProfileDef) -> AipCapability:
    cap_id = f"cap:{defn.id}"
    skill_names = list(defn.default_skill_names)
    return AipCapability(
        id=cap_id,
        name=defn.title,
        description=defn.description,
        input={
            "type": "object",
            "properties": {
                "user_message": {
                    "type": "string",
                    "description": "用户自然语言诉求",
                },
                "session_id": {
                    "type": "string",
                    "description": "会话标识符",
                },
                "task_id": {
                    "type": "string",
                    "description": "任务标识符",
                },
            },
            "required": ["user_message"],
        },
        output={
            "type": "object",
            "properties": {
                "handoff_summary": {"type": "string"},
                "citations": {"type": "array"},
            },
        },
        constraints={
            "skills": skill_names,
            "default_skills": skill_names,
        },
    )


def build_agent_acdl(
    agent_id: str,
    *,
    enabled: bool = True,
    service_endpoint: str | None = None,
) -> AipAgentDescription | None:
    defn = get_agent_profile(agent_id)
    if not defn or not enabled:
        return None
    settings = get_settings()
    endpoint = service_endpoint
    if endpoint is None and settings.aip_service_base_url:
        base = settings.aip_service_base_url.rstrip("/")
        aid = build_agent_aid(agent_id)
        endpoint = f"{base}/aip/interact?target_aid={aid}"
    return AipAgentDescription(
        aid=build_agent_aid(agent_id),
        name=defn.title,
        version=settings.platform_version,
        description=defn.description,
        capabilities=[_capability_for_profile(defn)],
        service_endpoint=endpoint,
    )


def list_builtin_agent_acdl(
    *,
    include_orchestrator: bool = False,
    enabled_only: bool = True,
    enabled_map: dict[str, bool] | None = None,
    service_enabled_map: dict[str, bool] | None = None,
) -> list[AipAgentDescription]:
    """从内置 AGENT_PROFILES 生成 ACDL 列表。"""
    enabled_map = enabled_map or {}
    service_enabled_map = service_enabled_map or {}
    out: list[AipAgentDescription] = []
    for defn in sorted(AGENT_PROFILES, key=lambda item: item.sort_order):
        if defn.id == "orchestrator" and not include_orchestrator:
            continue
        enabled = enabled_map.get(defn.id, True)
        if enabled_only and not enabled:
            continue
        if service_enabled_map and not service_enabled_map.get(defn.id, True):
            continue
        acdl = build_agent_acdl(defn.id, enabled=enabled)
        if acdl:
            out.append(acdl)
    return out
