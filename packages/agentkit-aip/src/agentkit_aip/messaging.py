"""AIP 消息序列化与 complete 事件读写 — 全链路唯一边界。"""

from __future__ import annotations

from typing import Any

from agentkit_aip.handoff import handoff_text_from_message
from agentkit_aip.types import AipMessage

_COMPLETE_HANDOFF_KEY = "aip_handoff"


def parse_message(data: dict[str, Any] | AipMessage | None) -> AipMessage | None:
    """将 dict / 模型统一解析为 AipMessage；无效输入返回 None。"""
    if data is None:
        return None
    if isinstance(data, AipMessage):
        return data
    try:
        return AipMessage.model_validate(data)
    except Exception:
        return None


def serialize_message(message: AipMessage | None) -> dict[str, Any] | None:
    """AipMessage → JSON 可序列化 dict。"""
    if message is None:
        return None
    return message.model_dump(mode="json")


def handoff_from_complete(complete: dict[str, Any] | None) -> AipMessage | None:
    """从 tool loop / hop 的 complete 事件提取结构化 handoff。"""
    if not complete:
        return None
    raw = complete.get(_COMPLETE_HANDOFF_KEY)
    if not isinstance(raw, dict):
        return None
    return parse_message(raw)


def reply_text_from_complete(complete: dict[str, Any] | None) -> str:
    """从 complete 事件提取验收文本：优先 AIP handoff，回退 reply 字段。"""
    message = handoff_from_complete(complete)
    text = handoff_text_from_message(message)
    if text:
        return text
    return str((complete or {}).get("reply") or "").strip()


def attach_handoff_to_complete(
    complete: dict[str, Any],
    message: AipMessage | None,
) -> dict[str, Any]:
    """将 AIP handoff 写入 complete 事件（无 message 时移除字段）。"""
    out = dict(complete)
    if message is None:
        out.pop(_COMPLETE_HANDOFF_KEY, None)
        return out
    out[_COMPLETE_HANDOFF_KEY] = serialize_message(message)
    return out
