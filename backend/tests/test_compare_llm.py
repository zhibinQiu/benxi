"""LLM-based cross-document compare."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.llm_parse import parse_llm_json
from app.integrations.text_extract import ParsedDocument
from app.services.compare_llm_service import (
    _excerpt_contrast_items,
    _normalize_diff_items,
    _text_similarity,
    compare_documents_with_llm,
)


def test_parse_llm_json_from_markdown_fence():
    raw = '```json\n{"summary":"有差异","differences":[]}\n```'
    data = parse_llm_json(raw)
    assert data == {"summary": "有差异", "differences": []}


def test_normalize_diff_items_maps_description():
    items = _normalize_diff_items(
        [
            {
                "diff_type": "add",
                "description": "新增违约责任条款",
            }
        ]
    )
    assert len(items) == 1
    assert items[0]["diff_type"] == "add"
    assert items[0]["text_right"] == "新增违约责任条款"


def test_compare_documents_with_llm_success():
    base = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="a.pdf",
        full_text="甲方：A公司",
        pages=[],
    )
    other = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="b.pdf",
        full_text="甲方：B公司",
        pages=[],
    )
    llm_raw = (
        '{"summary":"公司名称变更","differences":'
        '[{"diff_type":"modify","text_left":"A公司","text_right":"B公司",'
        '"description":"甲方名称不同"}]}'
    )

    with (
        patch("app.services.compare_llm_service.is_configured", return_value=True),
        patch(
            "app.services.compare_llm_service.chat_completion_sync",
            return_value=llm_raw,
        ),
    ):
        items, summary = compare_documents_with_llm(base, other)

    assert summary == "公司名称变更"
    assert len(items) == 1
    assert items[0]["diff_type"] == "modify"


def test_compare_documents_with_llm_requires_config():
    base = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="a.pdf",
        full_text="x",
        pages=[],
    )
    other = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="b.pdf",
        full_text="y",
        pages=[],
    )

    with patch("app.services.compare_llm_service.is_configured", return_value=False):
        with pytest.raises(ValueError, match="语言模型未配置"):
            compare_documents_with_llm(base, other)


def test_compare_documents_fallback_when_llm_returns_empty_differences():
    base = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="双碳赛道.pdf",
        full_text="零碳工厂申报门槛抬高，碳足迹核算成为新赛道。" * 20,
        pages=[],
    )
    other = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="烟台规划.pdf",
        full_text="烟台市发布五年规划，蓬莱定位为文旅融合发展示范区。" * 20,
        pages=[],
    )
    llm_raw = (
        '{"summary":"两份文档主题完全不同，无实质差异。",'
        '"differences":[]}'
    )

    with (
        patch("app.services.compare_llm_service.is_configured", return_value=True),
        patch(
            "app.services.compare_llm_service._call_compare_llm",
            side_effect=[llm_raw, llm_raw],
        ),
    ):
        items, summary = compare_documents_with_llm(base, other)

    assert len(items) >= 1
    assert "无实质差异" not in summary
    assert "差异" in summary


def test_excerpt_contrast_items_produces_pairs():
    base = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="a.pdf",
        full_text="主题A\n\n正文\n第一段A内容。",
        pages=[],
    )
    other = ParsedDocument(
        document_id=uuid.uuid4(),
        file_name="b.pdf",
        full_text="主题B\n\n正文\n第一段B内容。",
        pages=[],
    )
    items = _excerpt_contrast_items(base, other)
    assert items
    assert items[0]["diff_type"] == "modify"
    assert items[0].get("text_left")
    assert items[0].get("text_right")


def test_text_similarity_differs_for_unrelated_docs():
    sim = _text_similarity("双碳零碳工厂", "烟台房地产板块规划")
    assert sim < 0.5
