"""workflow 回放参数替换测试。"""

from app.integrations.browser_automation.workflow_replay import apply_params, parse_replay_params


def test_apply_params():
    assert apply_params("https://{{host}}/x", {"host": "example.com"}) == "https://example.com/x"
    assert apply_params("fixed", {}) == "fixed"


def test_parse_replay_params_kv():
    assert parse_replay_params(["url=https://a.com", "name=Test"]) == {
        "url": "https://a.com",
        "name": "Test",
    }


def test_parse_replay_params_json():
    assert parse_replay_params(['{"url":"https://b.com"}']) == {"url": "https://b.com"}
