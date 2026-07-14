"""AIP 会话消息总线 — 子智能体经标准消息在同一 session 内互通。"""

from __future__ import annotations

import threading
from typing import Any

from app.agentkit.aip.handoff import HandoffBuilder, build_sequential_task_request, format_task_request_for_llm
from app.agentkit.aip.types import AipMessage

_bus_lock = threading.Lock()
_sessions: dict[str, list[AipMessage]] = {}


class AipSessionBus:
    """进程内会话级 AIP 消息总线（GB/Z 185.6 群组/混合模式的轻量实现）。

    专精智能体完成子任务后 ``publish`` handoff；后续智能体通过 ``handoffs``
    读取前置成果，或由 ``build_task_request`` 生成标准 task_request。
    """

    def __init__(self, *, handoff_builder: HandoffBuilder | None = None) -> None:
        self._builder = handoff_builder or HandoffBuilder()

    def reset(self, session_id: str) -> None:
        """清空指定会话（测试或新编排开始时调用）。"""
        key = (session_id or "").strip()
        if not key:
            return
        with _bus_lock:
            _sessions.pop(key, None)

    def publish(self, session_id: str, message: AipMessage) -> None:
        """投递一条 AIP 消息到会话（通常为服务智能体 handoff）。"""
        key = (session_id or "").strip()
        if not key or message is None:
            return
        with _bus_lock:
            _sessions.setdefault(key, []).append(message)

    def handoffs(self, session_id: str) -> list[AipMessage]:
        """返回会话内已发布的全部 handoff 消息（按时间顺序）。"""
        key = (session_id or "").strip()
        if not key:
            return []
        with _bus_lock:
            return list(_sessions.get(key, []))

    def build_task_request(
        self,
        *,
        session_id: str,
        task_id: str,
        target_agent_id: str,
        user_message: str,
    ) -> AipMessage:
        """基于会话内已有 handoff 构建下一条 task_request。"""
        return build_sequential_task_request(
            user_message=user_message,
            prior_handoffs=self.handoffs(session_id),
            session_id=session_id,
            task_id=task_id,
            target_agent_id=target_agent_id,
            builder=self._builder,
        )

    def format_task_request_for_llm(
        self,
        *,
        session_id: str,
        task_id: str,
        target_agent_id: str,
        user_message: str,
    ) -> str:
        """task_request → 专精 LLM 可读的 user 消息。"""
        request = self.build_task_request(
            session_id=session_id,
            task_id=task_id,
            target_agent_id=target_agent_id,
            user_message=user_message,
        )
        return format_task_request_for_llm(request)

    def snapshot(self, session_id: str) -> list[dict[str, Any]]:
        """会话消息 JSON 快照（调试 / 对外透出）。"""
        return [msg.model_dump(mode="json") for msg in self.handoffs(session_id)]


_default_bus = AipSessionBus()


def get_session_bus() -> AipSessionBus:
    """返回进程内默认 AIP 会话总线单例。"""
    return _default_bus
