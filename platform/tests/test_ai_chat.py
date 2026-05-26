"""AI 首页对话 API。"""


def test_ai_chat_requires_auth(client):
    r = client.post(
        "/api/v1/ai-chat/chat",
        json={"message": "你好"},
    )
    assert r.status_code == 401


def test_ai_chat_stream_requires_auth(client):
    r = client.post(
        "/api/v1/ai-chat/chat/stream",
        json={"message": "你好"},
    )
    assert r.status_code == 401
