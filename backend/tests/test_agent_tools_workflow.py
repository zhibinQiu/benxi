from app.services.agent_tools import tool_workflow_meta


def test_web_search_workflow_meta():
    meta = tool_workflow_meta("web_search", '{"query": "碳配额流程"}')
    assert meta["tool"] == "web_search"
    assert "联网" in meta["title"]


def test_knowledge_retrieve_workflow_meta():
    meta = tool_workflow_meta("knowledge_retrieve", '{"query": "制度"}')
    assert meta["tool"] == "knowledge_retrieve"


def test_schedule_notification_workflow_meta_includes_boost_seconds():
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    meta = tool_workflow_meta(
        "schedule_notification",
        f'{{"title": "喝水", "scheduled_at": "{future}"}}',
    )
    assert meta["tool"] == "platform.notification"
    assert 28 <= int(meta["boost_seconds"]) <= 32
    assert " · " in meta["detail"]
    when_part = meta["detail"].split(" · ", 1)[1]
    assert len(when_part) >= 16
