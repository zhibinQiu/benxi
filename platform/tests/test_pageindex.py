"""PageIndex 实验性集成测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.integrations.pageindex_bridge import (
    count_tree_nodes,
    create_node_mapping,
    remove_fields,
)
from app.services.knowledge_parser_service import list_parser_options, normalize_parser_id
from app.services.knowledge_qa_service import retrieval_workflow_title
from app.services.pageindex_service import resolve_retrieval_engine_for_document


def test_pageindex_supported_formats():
    from app.integrations.pageindex_bridge import (
        PAGEINDEX_SUPPORTED_SUFFIXES,
        is_pageindex_supported_file,
        pageindex_supported_formats,
    )

    assert ".pdf" in PAGEINDEX_SUPPORTED_SUFFIXES
    assert ".docx" in PAGEINDEX_SUPPORTED_SUFFIXES
    assert ".txt" in PAGEINDEX_SUPPORTED_SUFFIXES
    assert is_pageindex_supported_file("报告.pdf")
    assert is_pageindex_supported_file("说明.docx")
    assert is_pageindex_supported_file("notes.txt")
    assert is_pageindex_supported_file("report", "application/pdf")
    assert is_pageindex_supported_file(
        "document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert is_pageindex_supported_file("notes", "text/plain")
    assert not is_pageindex_supported_file("data.xlsx")
    assert "word" in pageindex_supported_formats()
    assert "txt" in pageindex_supported_formats()


def test_prepare_pageindex_index_path_txt_prefers_md():
    from app.integrations.pageindex_bridge import prepare_pageindex_index_path

    path, cleanup = prepare_pageindex_index_path(
        content=b"hello world",
        file_name="notes.txt",
        mime_type="text/plain",
        title="Notes",
    )
    try:
        assert path.suffix.lower() == ".md"
        assert path in cleanup
        assert b"hello world" in path.read_bytes()
    finally:
        for p in cleanup:
            p.unlink(missing_ok=True)


def test_prepare_pageindex_index_path_docx_to_pdf():
    import io

    from docx import Document

    from app.integrations.pageindex_bridge import prepare_pageindex_index_path

    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("PageIndex Word 索引测试正文。" * 8)
    doc.save(buf)
    path, cleanup = prepare_pageindex_index_path(
        content=buf.getvalue(),
        file_name="report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        title="报告",
    )
    try:
        assert path.suffix.lower() == ".md"
        assert path in cleanup
    finally:
        for p in cleanup:
            p.unlink(missing_ok=True)


def test_pageindex_parser_option_listed():
    data = list_parser_options()
    ids = {item["id"] for item in data["chunk_methods"]}
    assert "pageindex" in ids
    assert normalize_parser_id("pageindex") == "pageindex"
    from app.services.knowledge_parser_service import is_pageindex_parser

    assert is_pageindex_parser("pageindex")
    assert not is_pageindex_parser("naive")


def test_pageindex_tree_utils():
    tree = [
        {
            "node_id": "0001",
            "title": "Intro",
            "text": "hello",
            "nodes": [{"node_id": "0002", "title": "Sub", "summary": "world"}],
        }
    ]
    stripped = remove_fields(tree, fields={"text"})
    assert stripped[0].get("text") is None
    mapping = create_node_mapping(tree)
    assert set(mapping) == {"0001", "0002"}
    assert count_tree_nodes(tree) == 2


def test_retrieval_workflow_title_modes():
    assert retrieval_workflow_title("pageindex_tree") == "正在检索相关文档"
    assert retrieval_workflow_title("hybrid") == "正在检索相关文档"
    assert retrieval_workflow_title("mixed") == "正在检索相关文档"
    assert "检索" in retrieval_workflow_title("none")


def test_resolve_retrieval_engine_prefers_newer_pageindex(monkeypatch):
    doc = SimpleNamespace(id=uuid.uuid4(), title="demo")
    pi_time = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rag_time = datetime(2026, 5, 1, tzinfo=timezone.utc)
    pi_link = SimpleNamespace(
        index_completed_at=pi_time,
        pageindex_doc_id="pi-1",
        platform_version_id=uuid.uuid4(),
    )
    rag_ver = SimpleNamespace(id=uuid.uuid4())
    rag_vl = SimpleNamespace(index_completed_at=rag_time)

    monkeypatch.setattr(
        "app.services.pageindex_service.get_ready_link_for_document",
        lambda _db, _doc: pi_link,
    )
    monkeypatch.setattr(
        "app.services.pageindex_service.load_pageindex_doc",
        lambda _ws, _doc_id: {"structure": []},
    )
    monkeypatch.setattr(
        "app.services.pageindex_service.pageindex_workspace_dir",
        lambda: MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.ragflow_version_link_service.resolve_latest_indexed_version",
        lambda _db, _doc: rag_ver,
    )
    monkeypatch.setattr(
        "app.services.ragflow_version_link_service.get_version_link_by_version_id",
        lambda _db, _vid: rag_vl,
    )

    assert resolve_retrieval_engine_for_document(MagicMock(), doc) == "pageindex"
