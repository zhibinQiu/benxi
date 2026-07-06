"""知识库切片 / OCR 选项。"""

from unittest.mock import patch

from app.services.knowledge_parser_service import (
    PARSER_PAGEINDEX,
    build_parser_config,
    coerce_parser_layout,
    index_stack_block_reason,
    list_parser_options,
)


def test_index_stack_block_reason_pageindex_when_package_missing(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.pageindex_bridge.pageindex_package_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.integrations.pageindex_bridge._PAGEINDEX_IMPORT_ERROR",
        "No module named 'pageindex'",
    )
    reason = index_stack_block_reason(PARSER_PAGEINDEX, reindex=True)
    assert reason
    assert "PageIndex" in reason
    assert "pip install" in reason


def test_list_parser_options_reports_pageindex_status(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.pageindex_bridge.pageindex_package_available",
        lambda: False,
    )
    data = list_parser_options()
    assert data["pageindex"]["available"] is False
    assert data["pageindex"]["block_reason"]
    assert data["defaults"]["parser_id"] != PARSER_PAGEINDEX


def test_list_parser_options_includes_modern_ocr():
    data = list_parser_options()
    layout_ids = {x["id"] for x in data["layout_recognizers"]}
    assert "MinerU" in layout_ids
    assert "PaddleOCR" in layout_ids
    chunk_ids = {x["id"] for x in data["chunk_methods"]}
    assert "smart" in chunk_ids


def test_coerce_parser_layout_for_mineru():
    parser, layout = coerce_parser_layout("naive", "MinerU")
    assert parser == "smart"
    assert layout == "MinerU"


def test_build_parser_config_merges_layout():
    parser, cfg = build_parser_config("smart", "PaddleOCR")
    assert parser == "smart"
    assert cfg["layout_recognize"] == "PaddleOCR"
    assert cfg["chunk_token_num"] >= 128


def test_list_parser_options_default_layout_is_deepdoc():
    defaults = list_parser_options()["defaults"]
    assert defaults["layout_recognize"] == "DeepDOC"


def test_list_parser_options_default_parser_is_naive():
    defaults = list_parser_options()["defaults"]
    assert defaults["parser_id"] == "naive"
