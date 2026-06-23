"""Agent 记忆层 MEMORY.md 读写。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.agent_memory_service import append_user_memory, read_user_memory


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
