"""AIP 会话总线与外部注册表单元测试。"""

from __future__ import annotations

from app.core.aip.external_registry import clear_external_agent_cache
from app.core.aip.handoff import build_specialist_handoff_message
from app.core.aip.session_bus import get_session_bus
from app.config import get_settings


def test_session_bus_publish_and_task_request(monkeypatch):
    bus = get_session_bus()
    bus.reset("sess-bus-1")
    prior = build_specialist_handoff_message(
        agent_id="platform",
        session_id="sess-bus-1",
        task_id="t1",
        text="第一步完成",
        satisfied=True,
    )
    bus.publish("sess-bus-1", prior)
    llm_text = bus.format_task_request_for_llm(
        session_id="sess-bus-1",
        task_id="t2",
        target_agent_id="research",
        user_message="继续调研",
    )
    assert "第一步完成" in llm_text
    assert "继续调研" in llm_text
    assert len(bus.handoffs("sess-bus-1")) == 1


def test_external_registry_from_config(monkeypatch):
    clear_external_agent_cache()
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "aip_external_agents_json",
        '[{"aid":"aid:cn:ent:demo:agent:legal-001","name":"法务","description":"审核","service_endpoint":"https://example.com/aip/interact"}]',
    )
    clear_external_agent_cache()
    from app.core.aip.external_registry import list_external_agents, get_external_agent

    items = list_external_agents()
    assert len(items) == 1
    assert get_external_agent("aid:cn:ent:demo:agent:legal-001") is not None
    clear_external_agent_cache()
