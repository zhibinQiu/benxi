"""AIP handoff 与 AID 单元测试。"""

from __future__ import annotations

from app.core.aip.aid import build_agent_aid, orchestrator_aid, parse_agent_id_from_aid
from app.core.aip.acdl import build_agent_acdl
from app.core.aip.handoff import (
    build_sequential_task_request,
    build_specialist_handoff_message,
    format_task_request_for_llm,
    handoff_text_from_message,
)
from app.agentkit.aip.types import AipMessage


def test_build_and_parse_aid():
    aid = build_agent_aid("research")
    assert aid.startswith("aid:cn:")
    assert aid.endswith("agent:research-001")
    assert parse_agent_id_from_aid(aid) == "research"
    assert parse_agent_id_from_aid("invalid") is None


def test_orchestrator_aid():
    aid = orchestrator_aid()
    assert parse_agent_id_from_aid(aid) == "orchestrator"


def test_specialist_handoff_message_structure():
    msg = build_specialist_handoff_message(
        agent_id="platform",
        session_id="sess-1",
        task_id="t1",
        text="已在文档库创建文件夹「测试」",
        loop_state={"tool_outcome_lines": ["create_folder：完成"]},
        satisfied=True,
        citations=[{"title": "doc"}],
    )
    assert msg.senderRole == "service"
    assert msg.artifact is True
    assert msg.final is True
    assert msg.sessionId == "sess-1"
    assert msg.taskId == "t1"
    assert handoff_text_from_message(msg) == "已在文档库创建文件夹「测试」"
    assert msg.payload and msg.payload.get("agent_id") == "platform"


def test_sequential_task_request_roundtrip():
    prior = build_specialist_handoff_message(
        agent_id="platform",
        session_id="sess-1",
        task_id="t1",
        text="第一步完成",
        satisfied=True,
    )
    request = build_sequential_task_request(
        user_message="继续第二步",
        prior_handoffs=[prior],
        session_id="sess-1",
        task_id="t2",
        target_agent_id="research",
    )
    assert request.message_type and request.message_type.value == "task_request"
    assert request.senderRole == "request"
    llm_text = format_task_request_for_llm(request)
    assert "继续第二步" in llm_text
    assert "第一步完成" in llm_text
    assert "【已完成】" in llm_text


def test_build_agent_acdl():
    acdl = build_agent_acdl("research")
    assert acdl is not None
    assert acdl.aid.endswith("agent:research-001")
    assert acdl.capabilities
    assert acdl.capabilities[0].id == "cap:research"


def test_aip_message_json_roundtrip():
    msg = build_specialist_handoff_message(
        agent_id="diagram",
        session_id="s",
        task_id="t",
        text="图表已生成",
        satisfied=True,
    )
    raw = msg.model_dump(mode="json")
    restored = AipMessage.model_validate(raw)
    assert restored.id == msg.id
    assert handoff_text_from_message(restored) == "图表已生成"
