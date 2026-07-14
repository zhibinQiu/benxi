"""GB/Z 185.2 智能体身份码（AID）— agentkit 适配层。"""

from __future__ import annotations

from app.agentkit.aip.aid import (
    AidConfig,
    build_agent_aid as _build_agent_aid,
    orchestrator_aid as _orchestrator_aid,
    parse_agent_id_from_aid,
)

from app.core.aip._platform_config import platform_aid_config

__all__ = [
    "AidConfig",
    "build_agent_aid",
    "orchestrator_aid",
    "parse_agent_id_from_aid",
]


def build_agent_aid(
    agent_id: str,
    *,
    country: str | None = None,
    org_type: str | None = None,
    org_id: str | None = None,
    serial: str | None = None,
) -> str:
    cfg = platform_aid_config()
    if any(v is not None for v in (country, org_type, org_id, serial)):
        cfg = AidConfig(
            country=country or cfg.country,
            org_type=org_type or cfg.org_type,
            org_id=org_id or cfg.org_id,
            serial=serial or cfg.serial,
            orchestrator_id=cfg.orchestrator_id,
        )
    return _build_agent_aid(agent_id, cfg)


def orchestrator_aid() -> str:
    return _orchestrator_aid(platform_aid_config())
