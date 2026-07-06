"""AIP 会话消息总线 — agentkit 适配（注入平台 AidConfig）。"""

from agentkit_aip import AipSessionBus

from app.core.aip._platform_config import platform_handoff_builder

_default_bus = AipSessionBus(handoff_builder=platform_handoff_builder())


def get_session_bus() -> AipSessionBus:
    """返回进程内默认 AIP 会话总线单例。"""
    return _default_bus


__all__ = ["AipSessionBus", "get_session_bus"]
