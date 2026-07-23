"""自动化调度与 Agent RAG 基础测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.routing_catalog_md import RoutingEntry
from app.services.agent_automation_service import compute_next_run_at
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
