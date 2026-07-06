"""Checkpoint 模块测试。

需要 Redis 可用时运行（标记为 redis_required）。
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import ANY, MagicMock, patch

import pytest

from app.core.agent_checkpoint import (
    clear_checkpoint,
    generate_checkpoint_id,
    get_pending_checkpoints_for_user,
    load_checkpoint,
    save_checkpoint,
)


def _make_loop_state(**overrides) -> dict:
    return {
        "citations": [],
        "_hitl_confirmed": False,
        "agent_id": "orchestrator",
        "tool_outcome_lines": [],
        **overrides,
    }


def _make_working() -> list[dict]:
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "帮我删除一个文档"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "function": {
                        "name": "delete_document",
                        "arguments": '{"document_id": "doc-001", "confirm": true}',
                    },
                }
            ],
        },
    ]


# ─── 使用 Fake Redis（不依赖外部 Redis 服务） ───


class FakeRedis:
    """模拟 Redis 基本操作。"""

    def __init__(self):
        self._data: dict[str, dict[str, str]] = {}
        self._ttl: dict[str, int] = {}

    def pipeline(self):
        return self

    def hset(self, key, mapping):
        if key not in self._data:
            self._data[key] = {}
        self._data[key].update(mapping)
        return self

    def hget(self, key, field):
        return (self._data.get(key) or {}).get(field)

    def hgetall(self, key):
        raw = self._data.get(key) or {}
        if not raw:
            return {}
        return dict(raw)

    def expire(self, key, ttl):
        self._ttl[key] = ttl
        return True

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                self._ttl.pop(k, None)
                count += 1
        return count

    def scan(self, cursor=0, match="*", count=100):
        import fnmatch

        keys = [k for k in self._data if fnmatch.fnmatch(k, match)]
        return 0, keys

    def execute(self):
        pass


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture(autouse=True)
def mock_redis(fake_redis):
    with patch("app.core.redis_client.get_redis_client", return_value=fake_redis):
        yield


# ─── 基础功能测试 ─────────────────────────────────


class TestSaveLoadCheckpoint:
    def test_save_and_load_confirmation_checkpoint(self):
        cp_id = generate_checkpoint_id()
        user_id = str(uuid.uuid4())

        saved = save_checkpoint(
            cp_id,
            user_id=user_id,
            phase="awaiting_confirmation",
            loop_state=_make_loop_state(),
            working=_make_working(),
            pending_data={
                "confirmation_id": "hitl-abc123",
                "tool_name": "delete_document",
                "params_json": '{"document_id": "doc-001"}',
            },
        )
        assert saved is True

        loaded = load_checkpoint(cp_id)
        assert loaded is not None
        assert loaded["user_id"] == user_id
        assert loaded["phase"] == "awaiting_confirmation"
        assert loaded["loop_state"]["_hitl_confirmed"] is False
        assert loaded["loop_state"]["agent_id"] == "orchestrator"
        assert len(loaded["working"]) == 3
        assert loaded["pending_data"]["confirmation_id"] == "hitl-abc123"

    def test_save_and_load_choice_checkpoint(self):
        cp_id = generate_checkpoint_id()
        user_id = str(uuid.uuid4())

        saved = save_checkpoint(
            cp_id,
            user_id=user_id,
            phase="awaiting_choice",
            loop_state=_make_loop_state(),
            working=_make_working(),
            pending_data={
                "choice_id": "choice-xyz",
                "question": "请选择报告类型",
                "options": '["季报", "年报", "月报"]',
            },
        )
        assert saved is True

        loaded = load_checkpoint(cp_id)
        assert loaded is not None
        assert loaded["phase"] == "awaiting_choice"
        assert loaded["pending_data"]["choice_id"] == "choice-xyz"

    def test_load_nonexistent_checkpoint(self):
        loaded = load_checkpoint("nonexistent-id")
        assert loaded is None

    def test_load_expired_checkpoint(self):
        # 模拟 Redis 返回空（已过期）
        cp_id = generate_checkpoint_id()
        loaded = load_checkpoint(cp_id)
        assert loaded is None


class TestClearCheckpoint:
    def test_clear_existing_checkpoint(self):
        cp_id = generate_checkpoint_id()
        save_checkpoint(
            cp_id,
            user_id=str(uuid.uuid4()),
            phase="awaiting_confirmation",
            loop_state=_make_loop_state(),
            working=_make_working(),
            pending_data={},
        )
        assert load_checkpoint(cp_id) is not None
        cleared = clear_checkpoint(cp_id)
        assert cleared is True
        assert load_checkpoint(cp_id) is None

    def test_clear_nonexistent_checkpoint(self):
        cleared = clear_checkpoint("does-not-exist")
        # Redis delete on missing key returns 0
        assert cleared is False


class TestGenerateCheckpointId:
    def test_generates_unique_ids(self):
        ids = {generate_checkpoint_id() for _ in range(100)}
        assert len(ids) == 100

    def test_id_format(self):
        cp_id = generate_checkpoint_id()
        assert cp_id.startswith("ckpt-")
        assert len(cp_id) > 10


class TestPendingCheckpointsForUser:
    def test_list_user_checkpoints(self):
        user_id = str(uuid.uuid4())
        other_user = str(uuid.uuid4())

        cp_a = generate_checkpoint_id()
        cp_b = generate_checkpoint_id()
        cp_c = generate_checkpoint_id()

        save_checkpoint(
            cp_a,
            user_id=user_id,
            phase="awaiting_confirmation",
            loop_state=_make_loop_state(),
            working=_make_working(),
            pending_data={"tool_name": "delete_document"},
        )
        save_checkpoint(
            cp_b,
            user_id=user_id,
            phase="awaiting_choice",
            loop_state=_make_loop_state(),
            working=_make_working(),
            pending_data={"question": "选择报告类型"},
        )
        save_checkpoint(
            cp_c,
            user_id=other_user,
            phase="awaiting_confirmation",
            loop_state=_make_loop_state(),
            working=_make_working(),
            pending_data={"tool_name": "delete_user"},
        )

        user_cps = get_pending_checkpoints_for_user(user_id)
        assert len(user_cps) == 2

        phases = {cp["phase"] for cp in user_cps}
        assert phases == {"awaiting_confirmation", "awaiting_choice"}

    def test_no_checkpoints(self):
        cps = get_pending_checkpoints_for_user(str(uuid.uuid4()))
        assert cps == []


# ─── 序列化/反序列化鲁棒性 ───────────────────────


class TestCheckpointSerialization:
    def test_loop_state_with_complex_types(self):
        cp_id = generate_checkpoint_id()
        loop_state = _make_loop_state(
            citations=[{"source": "web", "title": "Test"}],
            executed_tools=[
                {"name": "web_search", "args": '{"query": "hello"}', "result": '{"ok": true}'}
            ],
        )

        saved = save_checkpoint(
            cp_id,
            user_id=str(uuid.uuid4()),
            phase="awaiting_confirmation",
            loop_state=loop_state,
            working=_make_working(),
            pending_data={},
        )
        assert saved is True

        loaded = load_checkpoint(cp_id)
        assert loaded is not None
        assert len(loaded["loop_state"]["citations"]) == 1
        assert loaded["loop_state"]["citations"][0]["source"] == "web"
        assert len(loaded["loop_state"]["executed_tools"]) == 1

    def test_working_messages_preserved(self):
        cp_id = generate_checkpoint_id()
        working = _make_working()

        save_checkpoint(
            cp_id,
            user_id=str(uuid.uuid4()),
            phase="awaiting_confirmation",
            loop_state=_make_loop_state(),
            working=working,
            pending_data={},
        )

        loaded = load_checkpoint(cp_id)
        assert loaded is not None
        assert len(loaded["working"]) == 3
        assert loaded["working"][0]["role"] == "system"
        assert loaded["working"][-1]["role"] == "assistant"
        assert "delete_document" in str(loaded["working"][-1])


# ─── 边界情况 ───────────────────────


class TestCheckpointEdgeCases:
    def test_user_id_mismatch_in_list(self):
        """不同用户的 checkpoint 不会互相混淆。"""
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())

        for i in range(3):
            save_checkpoint(
                generate_checkpoint_id(),
                user_id=user_a,
                phase="awaiting_confirmation",
                loop_state=_make_loop_state(),
                working=_make_working(),
                pending_data={"idx": i},
            )

        assert len(get_pending_checkpoints_for_user(user_a)) == 3
        assert len(get_pending_checkpoints_for_user(user_b)) == 0

    def test_idempotent_clear(self):
        """多次清除不报错。"""
        cp_id = generate_checkpoint_id()
        save_checkpoint(
            cp_id,
            user_id=str(uuid.uuid4()),
            phase="awaiting_confirmation",
            loop_state=_make_loop_state(),
            working=_make_working(),
            pending_data={},
        )
        assert clear_checkpoint(cp_id) is True
        assert clear_checkpoint(cp_id) is False  # 第二次清除返回 False
        assert clear_checkpoint(cp_id) is False  # 第三次同
