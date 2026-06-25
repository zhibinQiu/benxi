from app.services.agent_tools import tool_workflow_meta


def test_web_search_workflow_meta():
    meta = tool_workflow_meta("web_search", '{"query": "碳配额流程"}')
    assert meta["tool"] == "web_search"
    assert "联网" in meta["title"]


def test_knowledge_retrieve_workflow_meta():
    meta = tool_workflow_meta("knowledge_retrieve", '{"query": "制度"}')
    assert meta["tool"] == "knowledge_retrieve"


def test_schedule_notification_workflow_meta_includes_boost_seconds():
    meta = tool_workflow_meta(
        "schedule_notification",
        '{"title": "喝水", "delay_seconds": 30}',
    )
    assert meta["tool"] == "platform.notification"
    assert 28 <= int(meta["boost_seconds"]) <= 30
    assert " · " in meta["detail"]
    when_part = meta["detail"].split(" · ", 1)[1]
    assert len(when_part) >= 16

    meta_min = tool_workflow_meta(
        "schedule_notification",
        '{"title": "开会", "delay_minutes": 5}',
    )
    assert 298 <= int(meta_min["boost_seconds"]) <= 300
    assert "开会" in meta_min["detail"]
    assert ":" in meta_min["detail"]
