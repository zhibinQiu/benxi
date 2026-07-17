"""agentkit-aip — 智能体互操作协议（AIP）精简实现。

基于 GB/Z 185 系列标准的 **消息 / handoff / 会话总线** 子集，
用于单进程或多服务场景下的专精智能体协作。
"""

from app.agentkit import __version__  # noqa: F401

from app.agentkit.aip.aid import AidConfig, build_agent_aid, orchestrator_aid, parse_agent_id_from_aid
from app.agentkit.aip.auth import generate_aip_sk, hash_aip_sk, is_aip_sk_token, sk_display_prefix
from app.agentkit.aip.handoff import (
    HandoffBuilder,
    HandoffParams,
    SpecialistHandoffResult,
    build_sequential_task_request,
    build_specialist_handoff_message,
    build_specialist_handoff_result,
    format_task_request_for_llm,
    handoff_text_from_message,
)
from app.agentkit.aip.messaging import (
    attach_handoff_to_complete,
    handoff_from_complete,
    parse_message,
    reply_text_from_complete,
    serialize_message,
)
from app.agentkit.aip.orchestration import best_reply_from_hops, merge_hop_citations
from app.agentkit.aip.session_bus import AipSessionBus, get_session_bus
from app.agentkit.aip.types import (
    AipAgentDescription,
    AipCapability,
    AipDataItem,
    AipInteractEnvelope,
    AipMessage,
    AipMessageType,
    AipTask,
    AipTaskStatus,
    SenderRole,
)

__all__ = [
    "AidConfig",
    "AipAgentDescription",
    "AipCapability",
    "AipDataItem",
    "AipInteractEnvelope",
    "AipMessage",
    "AipMessageType",
    "AipSessionBus",
    "AipTask",
    "AipTaskStatus",
    "HandoffBuilder",
    "SenderRole",
    "SpecialistHandoffResult",
    "attach_handoff_to_complete",
    "best_reply_from_hops",
    "build_agent_aid",
    "build_sequential_task_request",
    "build_specialist_handoff_message",
    "build_specialist_handoff_result",
    "format_task_request_for_llm",
    "generate_aip_sk",
    "get_session_bus",
    "handoff_from_complete",
    "handoff_text_from_message",
    "hash_aip_sk",
    "is_aip_sk_token",
    "merge_hop_citations",
    "orchestrator_aid",
    "parse_agent_id_from_aid",
    "parse_message",
    "reply_text_from_complete",
    "serialize_message",
    "sk_display_prefix",
]
