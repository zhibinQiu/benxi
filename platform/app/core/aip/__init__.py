"""GB/Z 185 智能体互联（AIP）— 统一入口。"""

from app.core.aip.acdl import build_agent_acdl, list_builtin_agent_acdl
from app.core.aip.aid import build_agent_aid, orchestrator_aid, parse_agent_id_from_aid
from app.core.aip.external_registry import (
    ExternalAgentRecord,
    get_external_agent,
    is_external_aid,
    list_external_agents,
)
from app.core.aip.handoff import (
    SpecialistHandoffResult,
    build_sequential_task_request,
    build_specialist_handoff_message,
    build_specialist_handoff_result,
    format_task_request_for_llm,
    handoff_text_from_message,
)
from app.core.aip.messaging import (
    attach_handoff_to_complete,
    handoff_from_complete,
    parse_message,
    reply_text_from_complete,
    serialize_message,
)
from app.core.aip.session_bus import AipSessionBus, get_session_bus
from app.core.aip.types import (
    AipAgentDescription,
    AipCapability,
    AipDataItem,
    AipInteractEnvelope,
    AipMessage,
    AipMessageType,
    SenderRole,
)

__all__ = [
    "AipAgentDescription",
    "AipCapability",
    "AipDataItem",
    "AipInteractEnvelope",
    "AipMessage",
    "AipMessageType",
    "AipSessionBus",
    "ExternalAgentRecord",
    "SenderRole",
    "SpecialistHandoffResult",
    "attach_handoff_to_complete",
    "build_agent_acdl",
    "build_agent_aid",
    "build_sequential_task_request",
    "build_specialist_handoff_message",
    "build_specialist_handoff_result",
    "format_task_request_for_llm",
    "get_external_agent",
    "get_session_bus",
    "handoff_from_complete",
    "handoff_text_from_message",
    "is_external_aid",
    "list_builtin_agent_acdl",
    "list_external_agents",
    "orchestrator_aid",
    "parse_agent_id_from_aid",
    "parse_message",
    "reply_text_from_complete",
    "serialize_message",
]
