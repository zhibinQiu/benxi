"""Agent 记忆层 MEMORY.md 读写。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.agent_memory_service import (
    append_user_memory,
    build_memory_prompt_context,
    read_user_memory,
)


def test_read_empty_when_missing():
    uid = uuid.uuid4()
    store = MagicMock()
    store.get_object_bytes.side_effect = FileNotFoundError
    with patch("app.services.agent_memory_service.get_object_store", return_value=store):
        assert read_user_memory(uid) == ""


def test_append_creates_memory_file():
    uid = uuid.uuid4()
    store = MagicMock()
    store.get_object_bytes.side_effect = FileNotFoundError
    with patch("app.services.agent_memory_service.get_object_store", return_value=store):
        ok = append_user_memory(uid, "偏好简洁回答")
    assert ok is True
    store.put_object_bytes.assert_called_once()
    key, payload, _ctype = store.put_object_bytes.call_args[0]
    assert key == f"agent-memory/{uid}/MEMORY.md"
    assert "偏好简洁回答" in payload.decode("utf-8")


def test_build_memory_prompt_context_includes_override_hint():
    uid = uuid.uuid4()
    store = MagicMock()
    store.get_object_bytes.return_value = "# Agent Memory\n\n- 系统名字为阿凡提".encode("utf-8")
    with patch("app.services.agent_memory_service.get_object_store", return_value=store):
        ctx = build_memory_prompt_context(uid)
    assert "阿凡提" in ctx
    assert "【用户记忆】" in ctx
    assert "以记忆为准" in ctx


def test_build_memory_prompt_context_empty_when_no_memory():
    uid = uuid.uuid4()
    store = MagicMock()
    store.get_object_bytes.side_effect = FileNotFoundError
    with patch("app.services.agent_memory_service.get_object_store", return_value=store):
        assert build_memory_prompt_context(uid) == ""
