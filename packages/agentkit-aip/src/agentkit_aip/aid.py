"""GB/Z 185.2 智能体身份码（AID）编解码。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_AID_RE = re.compile(
    r"^aid:(?P<country>[a-z]{2}):(?P<org_type>[a-z]+):(?P<org_id>[^:]+):agent:(?P<agent_type>[^-]+)-(?P<serial>\d+)$"
)


@dataclass(frozen=True, slots=True)
class AidConfig:
    """AID 命名空间配置；由宿主应用注入，避免全局 settings 依赖。"""

    country: str = "cn"
    org_type: str = "platform"
    org_id: str = "default"
    serial: str = "001"
    orchestrator_id: str = "orchestrator"


def build_agent_aid(agent_id: str, config: AidConfig | None = None) -> str:
    """根据 agent_id 与命名空间配置生成 AID。"""
    cfg = config or AidConfig()
    agent_type = (agent_id or "").strip()
    if not agent_type:
        raise ValueError("agent_id 不能为空")
    country = cfg.country.strip().lower()
    org_type = cfg.org_type.strip().lower()
    org_id = cfg.org_id.strip()
    serial = cfg.serial.strip()
    return f"aid:{country}:{org_type}:{org_id}:agent:{agent_type}-{serial}"


def orchestrator_aid(config: AidConfig | None = None) -> str:
    """调度智能体 AID。"""
    cfg = config or AidConfig()
    return build_agent_aid(cfg.orchestrator_id, cfg)


def parse_agent_id_from_aid(aid: str) -> str | None:
    """从 AID 解析内部 agent_id（如 research、platform）。"""
    match = _AID_RE.match((aid or "").strip())
    if not match:
        return None
    return match.group("agent_type")
