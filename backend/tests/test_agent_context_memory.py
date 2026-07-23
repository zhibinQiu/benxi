"""系统层对话摘要记忆写入。"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.services.agent_context_service import maybe_write_user_memory


def test_maybe_write_user_memory_saves_turn_summary():
    uid = uuid.uuid4()
    with patch("app.services.agent_context_service.append_user_memory", return_value=True) as append:
        ok = maybe_write_user_memory(uid, "今天碳价多少", "约 80 元/吨")
    assert ok is True
    note = append.call_args[0][1]
    assert "对话摘要" in note
    assert "碳价" in note


def test_maybe_write_user_memory_prefers_explicit_remember():
    uid = uuid.uuid4()
    with patch("app.services.agent_context_service.append_user_memory", return_value=True) as append:
        ok = maybe_write_user_memory(uid, "请记住我喜欢简洁回答", "好的，已记下")
    assert ok is True
    note = append.call_args[0][1]
    assert note.startswith("用户要求记住：")
    assert "简洁" in note
