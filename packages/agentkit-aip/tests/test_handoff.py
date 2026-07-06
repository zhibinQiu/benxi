"""agentkit-aip handoff 与 session bus 测试。"""

from agentkit_aip import (
    AipSessionBus,
    HandoffBuilder,
    build_specialist_handoff_result,
    handoff_text_from_message,
)


def test_handoff_roundtrip():
    bus = AipSessionBus()
    result = build_specialist_handoff_result(
        ok=True,
        text="done",
        agent_id="research",
        session_id="s1",
        task_id="t1",
    )
    assert result.message is not None
    bus.publish("s1", result.message)
    assert len(bus.handoffs("s1")) == 1
    assert handoff_text_from_message(result.message) == "done"


def test_sequential_task_request():
    bus = AipSessionBus(handoff_builder=HandoffBuilder())
    result = build_specialist_handoff_result(
        ok=True,
        text="step1",
        agent_id="research",
        session_id="s2",
        task_id="t1",
    )
    bus.publish("s2", result.message)
    llm_msg = bus.format_task_request_for_llm(
        session_id="s2",
        task_id="t2",
        target_agent_id="report",
        user_message="写报告",
    )
    assert "写报告" in llm_msg
    assert "step1" in llm_msg
