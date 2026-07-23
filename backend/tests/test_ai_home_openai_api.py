"""本析智能 OpenAI 兼容 API 测试。"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.models.org import User
from app.schema_migrate import ensure_platform_ai_home_settings_schema
from app.services import ai_home_api_settings_service as settings_svc
from app.services.aip_secret_key_service import create_secret_key, delete_secret_key


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema():
    ensure_platform_ai_home_settings_schema(engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sk_and_user(db):
    user = db.scalar(select(User).limit(1))
    assert user is not None
    created = create_secret_key(db, user, purpose="openai-compat-test")
    yield created.secret_key, user
    try:
        delete_secret_key(db, created.id)
    except Exception:
        pass


def _set_enabled(db, enabled: bool) -> None:
    settings_svc.set_openai_api_enabled(db, enabled)


def test_settings_get_put(client: TestClient, admin_token: str, db):
    _set_enabled(db, False)
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/ai-chat/openai-api-settings", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["enabled"] is False
    assert data["base_path"] == "/api/v1/openai/v1"
    assert data["model"] == "benxi"

    r2 = client.put(
        "/api/v1/ai-chat/openai-api-settings",
        headers=headers,
        json={"enabled": True},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["enabled"] is True

    r3 = client.get("/api/v1/ai-chat/openai-api-settings", headers=headers)
    assert r3.json()["data"]["enabled"] is True
    _set_enabled(db, False)


def test_openai_disabled_returns_403(client: TestClient, db, sk_and_user):
    sk, _ = sk_and_user
    _set_enabled(db, False)
    r = client.get(
        "/api/v1/openai/v1/models",
        headers={"Authorization": f"Bearer {sk}"},
    )
    assert r.status_code == 403
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == 403


def test_openai_rejects_non_sk(client: TestClient, admin_token: str, db):
    _set_enabled(db, True)
    try:
        r = client.get(
            "/api/v1/openai/v1/models",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["type"] == "authentication_error"
    finally:
        _set_enabled(db, False)


def test_openai_models_with_sk(client: TestClient, db, sk_and_user):
    sk, _ = sk_and_user
    _set_enabled(db, True)
    try:
        r = client.get(
            "/api/v1/openai/v1/models",
            headers={"Authorization": f"Bearer {sk}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["object"] == "list"
        ids = {item["id"] for item in body["data"]}
        assert "benxi" in ids
        assert "benxi-ai" in ids
        assert "grm" in ids
    finally:
        _set_enabled(db, False)


def test_chat_completions_non_stream(client: TestClient, db, sk_and_user):
    sk, _ = sk_and_user
    _set_enabled(db, True)

    async def _fake_stream(**kwargs):
        yield json.dumps(
            {
                "workflow": {
                    "phase": "agent_thinking",
                    "title": "规划",
                    "detail": "先检索再回答",
                }
            },
            ensure_ascii=False,
        )
        yield json.dumps({"delta": "你好，我是小析"}, ensure_ascii=False)
        yield json.dumps({"done": True}, ensure_ascii=False)

    try:
        with patch(
            "app.api.openai_compat.iter_chat_with_ai_agent_stream",
            side_effect=_fake_stream,
        ):
            r = client.post(
                "/api/v1/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {sk}"},
                json={
                    "model": "benxi",
                    "messages": [{"role": "user", "content": "你好"}],
                    "stream": False,
                },
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["object"] == "chat.completion"
        msg = body["choices"][0]["message"]
        assert msg["role"] == "assistant"
        assert msg["content"] == "你好，我是小析"
        assert "先检索再回答" in msg["reasoning_content"]
        assert msg["reasoning"] == msg["reasoning_content"]
        assert body["choices"][0]["finish_reason"] == "stop"
    finally:
        _set_enabled(db, False)


def test_chat_completions_stream(client: TestClient, db, sk_and_user):
    sk, _ = sk_and_user
    _set_enabled(db, True)

    async def _fake_stream(**kwargs):
        yield json.dumps(
            {
                "workflow": {
                    "phase": "thinking_delta",
                    "title": "思考",
                    "delta": "分析中",
                }
            },
            ensure_ascii=False,
        )
        yield json.dumps({"delta": "你"}, ensure_ascii=False)
        yield json.dumps({"delta": "好"}, ensure_ascii=False)
        yield json.dumps({"done": True}, ensure_ascii=False)

    try:
        with patch(
            "app.api.openai_compat.iter_chat_with_ai_agent_stream",
            side_effect=_fake_stream,
        ):
            with client.stream(
                "POST",
                "/api/v1/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {sk}"},
                json={
                    "model": "benxi",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                },
            ) as r:
                assert r.status_code == 200, r.read()
                text = "".join(r.iter_text())
        assert "chat.completion.chunk" in text
        assert "data: [DONE]" in text
        assert '"content": "你"' in text or '"content":"你"' in text
        assert "reasoning_content" in text
        assert "分析中" in text
    finally:
        _set_enabled(db, False)


def test_openai_event_mapper_replace_suffix_only():
    from app.api.openai_compat import _OpenAiEventMapper

    mapper = _OpenAiEventMapper()
    pieces = mapper.feed({"delta": "你好"})
    assert pieces[0].content == "你好"
    pieces = mapper.feed({"replace": "你好，世界"})
    assert pieces[0].content == "，世界"
    pieces = mapper.feed({"replace": "你好，世界"})
    assert pieces == []


def test_openai_event_mapper_skips_ui_workflow_noise():
    from app.api.openai_compat import _OpenAiEventMapper

    mapper = _OpenAiEventMapper()
    pieces = mapper.feed(
        {"workflow": {"phase": "workflow_started", "title": "收到请求"}}
    )
    assert pieces == []
    pieces = mapper.feed(
        {
            "workflow": {
                "phase": "tool_call",
                "tool": "web_search",
                "title": "检索",
                "detail": "碳市场",
            }
        }
    )
    assert pieces and "web_search" in (pieces[0].reasoning or "")


def test_chat_completions_benxi_ai_alias(client: TestClient, db, sk_and_user):
    sk, _ = sk_and_user
    _set_enabled(db, True)

    async def _fake_stream(**kwargs):
        yield json.dumps({"delta": "ok"}, ensure_ascii=False)
        yield json.dumps({"done": True}, ensure_ascii=False)

    try:
        with patch(
            "app.api.openai_compat.iter_chat_with_ai_agent_stream",
            side_effect=_fake_stream,
        ):
            r = client.post(
                "/api/v1/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {sk}"},
                json={
                    "model": "benxi-ai",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        assert r.status_code == 200, r.text
        assert r.json()["model"] == "benxi-ai"
        assert r.json()["choices"][0]["message"]["content"] == "ok"
    finally:
        _set_enabled(db, False)


def test_chat_completions_grm_direct_llm(client: TestClient, db, sk_and_user):
    sk, _ = sk_and_user
    _set_enabled(db, True)

    async def _fake_grm(**kwargs):
        return "直接来自默认 LLM", "thinking…"

    try:
        with patch(
            "app.api.openai_compat._grm_non_stream",
            side_effect=_fake_grm,
        ):
            r = client.post(
                "/api/v1/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {sk}"},
                json={
                    "model": "grm",
                    "messages": [
                        {"role": "system", "content": "简洁回答"},
                        {"role": "user", "content": "你好"},
                    ],
                    "stream": False,
                },
            )
        assert r.status_code == 200, r.text
        msg = r.json()["choices"][0]["message"]
        assert msg["content"] == "直接来自默认 LLM"
        assert msg["reasoning_content"] == "thinking…"
        assert r.json()["model"] == "grm"
    finally:
        _set_enabled(db, False)


def test_resolve_model_accepts_grm_prefix():
    from app.api.openai_compat import _resolve_model

    assert _resolve_model("grm") == "grm"
    assert _resolve_model("GRM-2.6-Opus") == "grm"


def test_chat_completions_rejects_unknown_model(client: TestClient, db, sk_and_user):
    sk, _ = sk_and_user
    _set_enabled(db, True)
    try:
        r = client.post(
            "/api/v1/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {sk}"},
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert r.status_code == 404
        assert "does not exist" in r.json()["error"]["message"]
    finally:
        _set_enabled(db, False)


def test_map_messages_requires_user():
    from app.api.openai_compat import _map_messages
    from app.core.exceptions import AppError
    from app.schemas.ai_home_openai import OpenAiChatMessage

    with pytest.raises(AppError):
        _map_messages([OpenAiChatMessage(role="system", content="x")])
