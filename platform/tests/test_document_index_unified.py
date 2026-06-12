"""统一索引状态读取层。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.services.document_index_service import (
    _apply_db_ready_override,
    apply_index_meta_to_knowledge_row,
    is_index_ready_meta,
)


def test_is_index_ready_meta_requires_synced_and_done_status():
    assert is_index_ready_meta({"knowledge_synced": True, "parse_status": "已索引"})
    assert is_index_ready_meta({"knowledge_synced": True, "parse_status": "已完成"})
    assert not is_index_ready_meta({"knowledge_synced": True, "parse_status": "解析中"})
    assert not is_index_ready_meta({"knowledge_synced": False, "parse_status": "已索引"})


def test_apply_db_ready_override_skips_active_parsing():
    did = str(uuid.uuid4())
    meta_by_doc = {
        did: {
            "knowledge_synced": True,
            "parse_status": "解析中",
        }
    }
    db_only = {
        did: {
            "knowledge_synced": True,
            "parse_status": "已索引",
            "indexed_version_id": "ver-1",
        }
    }
    _apply_db_ready_override(meta_by_doc, db_only)
    assert meta_by_doc[did]["parse_status"] == "解析中"


def test_apply_db_ready_override_wins_over_stale_live():
    did = str(uuid.uuid4())
    meta_by_doc = {
        did: {
            "knowledge_synced": True,
            "parse_status": None,
        }
    }
    db_only = {
        did: {
            "knowledge_synced": True,
            "parse_status": "已索引",
            "indexed_version_id": "ver-1",
        }
    }
    _apply_db_ready_override(meta_by_doc, db_only)
    assert meta_by_doc[did]["parse_status"] == "已索引"
    assert meta_by_doc[did]["indexed_version_id"] == "ver-1"


def test_apply_index_meta_to_knowledge_row_sets_index_ready():
    row: dict = {"document_id": "x", "parse_status": None}
    apply_index_meta_to_knowledge_row(
        row,
        {"knowledge_synced": True, "parse_status": "已索引"},
    )
    assert row["index_ready"] is True
    assert row["parse_status"] == "已索引"
