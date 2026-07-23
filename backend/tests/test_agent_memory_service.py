"""Agent 记忆层 MEMORY.md 读写。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.agent_memory_service import (
    append_user_memory,
    build_memory_prompt_context,
    build_turn_memory_note,
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


def test_build_turn_memory_note_compact():
    note = build_turn_memory_note("查询今日碳价", "全国 CEA 均价约 80 元/吨。")
    assert "对话摘要" in note
    assert "碳价" in note
    assert "80" in note


def test_append_keeps_newest_when_over_limit():
    uid = uuid.uuid4()
    store = MagicMock()
    # 模拟已接近上限的旧记忆
    old = "# Agent Memory\n\n" + "\n".join(f"- [2020-01-01 00:00] old-{i}-{'x' * 80}" for i in range(40))
    store.get_object_bytes.return_value = old.encode("utf-8")
    with (
        patch("app.services.agent_memory_service.get_object_store", return_value=store),
        patch("app.services.agent_memory_service.get_settings") as gs,
    ):
        gs.return_value.agent_memory_max_chars = 1200
        gs.return_value.agent_memory_entry_max_chars = 200
        ok = append_user_memory(uid, "最新对话摘要：用户问碳价")
    assert ok is True
    body = store.put_object_bytes.call_args[0][1].decode("utf-8")
    assert "最新对话摘要" in body
    assert len(body) <= 1200


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
