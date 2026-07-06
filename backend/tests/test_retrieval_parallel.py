"""文档检索并行化测试。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.services.knowledge_qa.retrieval import (
    _merge_hits_by_score,
    retrieve_hits_by_queries,
    retrieve_merged_hits_for_queries,
)


def test_merge_hits_by_score_deduplicates():
    hits = [
        {"document_id": "a", "snippet": "same", "score": 0.5},
        {"document_id": "a", "snippet": "same", "score": 0.9},
        {"document_id": "b", "snippet": "other", "score": 0.7},
    ]
    out = _merge_hits_by_score(hits, limit=5)
    assert len(out) == 2
    assert out[0]["score"] == 0.9


@patch("app.services.knowledge_qa.retrieval.retrieve_hits_for_qa")
def test_retrieve_hits_by_queries_single(mock_retrieve):
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    doc_ids = [uuid.uuid4()]
    mock_retrieve.return_value = ([{"snippet": "a", "score": 1.0}], "hybrid")

    out = retrieve_hits_by_queries(db, user, doc_ids, ["碳价", "碳价"])
    assert mock_retrieve.call_count == 1
    assert "碳价" in out
    assert out["碳价"][0][0]["snippet"] == "a"


@patch("app.services.knowledge_qa.retrieval._retrieve_hits_worker")
def test_retrieve_merged_hits_for_queries_parallel(mock_worker):
    db = MagicMock()
    user = MagicMock()
    user.id = uuid.uuid4()
    doc_ids = [uuid.uuid4()]

    def _side_effect(user_id, ids, q, *, limit, merge_nearby):
        return ([{"snippet": q, "score": 1.0, "document_id": "d1"}], "hybrid")

    mock_worker.side_effect = _side_effect

    hits = retrieve_merged_hits_for_queries(
        db,
        user,
        doc_ids,
        ["查询A", "查询B"],
        limit_per_query=5,
    )
    assert mock_worker.call_count == 2
    assert len(hits) == 2
