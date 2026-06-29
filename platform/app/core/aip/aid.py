"""GB/Z 185.2 智能体身份码（AID）编解码。"""

from __future__ import annotations

import re

from app.config import get_settings

_AID_RE = re.compile(
    r"^aid:(?P<country>[a-z]{2}):(?P<org_type>[a-z]+):(?P<org_id>[^:]+):agent:(?P<agent_type>[^-]+)-(?P<serial>\d+)$"
)


def build_agent_aid(
    agent_id: str,
    *,
    country: str | None = None,
    org_type: str | None = None,
    org_id: str | None = None,
    serial: str | None = None,
) -> str:
    settings = get_settings()
    country = (country or settings.aip_country).strip().lower()
    org_type = (org_type or settings.aip_org_type).strip().lower()
    org_id = (org_id or settings.aip_org_id).strip()
    serial = (serial or settings.aip_agent_serial).strip()
    agent_type = (agent_id or "").strip()
    if not agent_type:
        raise ValueError("agent_id 不能为空")
    return f"aid:{country}:{org_type}:{org_id}:agent:{agent_type}-{serial}"


def orchestrator_aid() -> str:
    return build_agent_aid("orchestrator")


def parse_agent_id_from_aid(aid: str) -> str | None:
    """从 AID 解析内部 agent_id（如 research、platform）。"""
    match = _AID_RE.match((aid or "").strip())
    if not match:
        return None
    return match.group("agent_type")
