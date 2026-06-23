from app.services.agent_intent import (
    is_chitchat_message,
    is_scheduled_reminder_request,
    parse_scheduled_reminder_request,
)


def test_parse_reminder_seconds():
    parsed = parse_scheduled_reminder_request("30秒后提醒我喝水")
    assert parsed is not None
    assert parsed["delay_seconds"] == 30
    assert parsed["delay_minutes"] is None
    assert parsed["title"] == "喝水"


def test_parse_reminder_minutes():
    parsed = parse_scheduled_reminder_request("5分钟后提醒我开会")
    assert parsed is not None
    assert parsed["delay_minutes"] == 5
    assert parsed["title"] == "开会"


def test_reminder_not_chitchat():
    text = "30秒后提醒我喝水"
    assert is_scheduled_reminder_request(text)
    assert not is_chitchat_message(text)


def test_non_reminder_returns_none():
    assert parse_scheduled_reminder_request("你好") is None
    assert parse_scheduled_reminder_request("提醒我喝水") is None
