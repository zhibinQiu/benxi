"""自动化调度与 Agent RAG 基础测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.core.agent_loop_session import coerce_user_id
from app.core.routing_catalog_md import RoutingEntry
from app.services.agent_automation_service import compute_next_run_at, execute_automation
from app.services.agent_skill_rag import (
    invalidate_agent_embedding_index,
    rank_agents_by_embedding,
)


def test_compute_next_run_once_and_daily():
    now = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
    once = compute_next_run_at("once", from_dt=now, starts_at=now + timedelta(hours=2))
    assert once == now + timedelta(hours=2)
    assert compute_next_run_at("once", from_dt=now, after_run=True) is None

    nxt = compute_next_run_at("daily", from_dt=now, after_run=True)
    assert nxt == now + timedelta(days=1)

    ended = compute_next_run_at(
        "daily",
        from_dt=now,
        ends_at=now - timedelta(minutes=1),
        after_run=True,
    )
    assert ended is None


def test_rank_agents_by_embedding_prefers_matching_entry(monkeypatch):
    invalidate_agent_embedding_index()
    monkeypatch.setattr(
        "app.services.agent_skill_rag.get_settings",
        lambda: type(
            "S",
            (),
            {
                "agent_skill_rag_enabled": True,
                "agent_skill_rag_min_similarity": 0.1,
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.agent_skill_rag._get_credentials",
        lambda _db: ("https://emb.example/v1", "sk-test", "test-emb"),
    )

    entries = [
        RoutingEntry(
            id="carbon",
            title="双碳",
            use_when="碳价行情 碳配额 碳排放核算",
        ),
        RoutingEntry(
            id="report",
            title="报告",
            use_when="调研报告 可行性研究",
        ),
    ]

    def _fake_index(db):
        from app.services.agent_skill_rag import _EmbeddingIndex, _l2_normalize

        names = [e.id for e in entries]
        # 手工构造：carbon 向量偏「碳」
        mat = np.asarray(
            [
                [1.0, 0.0, 0.2],
                [0.0, 1.0, 0.1],
            ],
            dtype=np.float32,
        )
        idx = _EmbeddingIndex(
            fingerprint="t",
            model="m",
            names=names,
            matrix=_l2_normalize(mat),
            built_at=0.0,
        )
        return idx, entries

    monkeypatch.setattr(
        "app.services.agent_skill_rag._ensure_agent_index",
        _fake_index,
    )

    def _embed(texts, **_kwargs):
        out = []
        for text in texts:
            if "碳" in text:
                out.append(np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
            else:
                out.append(np.asarray([0.0, 1.0, 0.0], dtype=np.float32))
        return out

    monkeypatch.setattr("app.services.agent_skill_rag.embed_texts", _embed)

    ranked = rank_agents_by_embedding(None, "今天碳配额价格", limit=2)
    assert ranked is not None
    assert ranked[0][1].id == "carbon"


def test_coerce_user_id_accepts_detached_expired_user():
    """commit+close 后 ORM User 属性过期；coerce_user_id 仍应能取出 id。"""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.scalars(select(User).limit(1)).first()
        if user is None:
            pytest.skip("no user in db")
        expected = user.id
        db.commit()
        db.close()
    except Exception:
        db.close()
        raise

    assert coerce_user_id(user) == expected
    assert coerce_user_id(expected) == expected


def test_execute_automation_passes_user_id_not_orm(monkeypatch):
    """立即执行不得把 Session 绑定的 User 传入 chat（避免 DetachedInstanceError）。"""
    import asyncio

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.agent_automation import AgentAutomation
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.scalars(select(User).limit(1)).first()
        if user is None:
            pytest.skip("no user in db")
        row = AgentAutomation(
            user_id=user.id,
            name="unit-test-auto",
            prompt="ping",
            frequency="daily",
            enabled=True,
            next_run_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        auto_id = row.id
        uid = user.id
    finally:
        db.close()

    seen: dict = {}

    async def _fake_chat(**kwargs):
        seen["user"] = kwargs.get("user")
        seen["db"] = kwargs.get("db")
        seen["message"] = kwargs.get("message")
        seen["extra"] = kwargs.get("extra_context_instruction")
        seen["persist"] = kwargs.get("persist_conversation")
        return {"reply": "七月 AI 事件摘要：模型发布与开源进展若干条。"}

    monkeypatch.setattr(
        "app.services.ai_chat_service.chat_with_ai_agent",
        _fake_chat,
    )
    monkeypatch.setattr(
        "app.services.notification_service.create_notification",
        lambda *a, **k: None,
    )

    try:
        result = asyncio.run(execute_automation(auto_id, force=True))
        assert result.get("ok") is True
        assert seen["db"] is None
        assert seen["user"] == uid
        assert isinstance(seen["user"], uuid.UUID)
        assert seen["message"] == "ping"
        # 与聊天共用同一入口：不注入定时任务专用提示词
        assert seen["extra"] is None
        assert seen["persist"] is False
    finally:
        db2 = SessionLocal()
        try:
            r = db2.get(AgentAutomation, auto_id)
            if r:
                db2.delete(r)
                db2.commit()
        finally:
            db2.close()
