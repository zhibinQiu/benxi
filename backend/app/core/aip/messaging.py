"""AIP 消息序列化 — 自 agentkit-aip 再导出。"""

from agentkit_aip.messaging import (
    attach_handoff_to_complete,
    handoff_from_complete,
    parse_message,
    reply_text_from_complete,
    serialize_message,
)

__all__ = [
    "attach_handoff_to_complete",
    "handoff_from_complete",
    "parse_message",
    "reply_text_from_complete",
    "serialize_message",
]
