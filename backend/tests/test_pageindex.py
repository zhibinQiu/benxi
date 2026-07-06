"""PageIndex 实验性集成测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.integrations.pageindex_bridge import (
    count_tree_nodes,
    create_node_mapping,
    flatten_pageindex_structure_text,
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


def test_pdf_pageindex_fallback_error_markers():
    from app.integrations.pageindex_bridge import _pdf_pageindex_should_fallback_to_markdown

    assert _pdf_pageindex_should_fallback_to_markdown(Exception("Processing failed"))
    assert _pdf_pageindex_should_fallback_to_markdown(
        Exception("Failed to complete toc transformation after maximum retries")
    )
    assert not _pdf_pageindex_should_fallback_to_markdown(
        FileNotFoundError("config.yaml")
    )


def test_pageindex_package_requires_config_yaml(monkeypatch):
    from app.integrations import pageindex_bridge

    monkeypatch.setattr(pageindex_bridge, "_refresh_pageindex_state", lambda: None)
    monkeypatch.setattr(pageindex_bridge, "_PAGEINDEX_AVAILABLE", False)
    monkeypatch.setattr(
        pageindex_bridge,
        "_PAGEINDEX_IMPORT_ERROR",
        "PageIndex 自托管包未完整安装（缺少 config.yaml）。",
    )
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: type("S", (), {"pageindex_enabled": True})(),
    )
    monkeypatch.setattr("app.integrations.deepseek_client.is_configured", lambda: True)
    reason = pageindex_bridge.pageindex_stack_block_reason()
    assert reason
    assert "配置文件" in reason
    assert "# 在 platform" not in reason


def test_bootstrap_pageindex_config_from_vendor(tmp_path, monkeypatch):
    from app.integrations import pageindex_bridge

    mod_dir = tmp_path / "pageindex_pkg"
    mod_dir.mkdir()
    vendor_root = tmp_path / "platform"
    vendor_cfg = vendor_root / "third_party/pageindex-upstream/pageindex/config.yaml"
    vendor_cfg.parent.mkdir(parents=True)
    vendor_cfg.write_text("model: test-model\n", encoding="utf-8")
    monkeypatch.setattr(
        pageindex_bridge,
        "_vendored_pageindex_config_sources",
        lambda: [vendor_cfg],
    )
    assert pageindex_bridge._bootstrap_pageindex_config(mod_dir)
    assert (mod_dir / "config.yaml").read_text(encoding="utf-8").startswith("model:")


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


def test_retrieve_pageindex_hits_runs_tree_search_in_parallel(monkeypatch):
    from unittest.mock import patch

    from app.services.pageindex_service import retrieve_pageindex_hits_for_qa

    docs = [SimpleNamespace(id=uuid.uuid4()) for _ in range(3)]
    jobs = [
        SimpleNamespace(
            doc=doc,
            structure=[
                {
                    "node_id": "0001",
                    "title": "Section",
                    "text": f"content-{idx}",
                }
            ],
        )
        for idx, doc in enumerate(docs)
    ]
    call_count = {"n": 0}

    def fake_tree_search(job, question):
        call_count["n"] += 1
        return str(job.doc.id), ["0001"]

    monkeypatch.setattr(
        "app.services.pageindex_service.pageindex_retrieval_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.pageindex_service._collect_pageindex_tree_search_jobs",
        lambda _db, _docs: jobs,
    )
    with patch(
        "app.services.pageindex_service.ThreadPoolExecutor"
    ) as mock_pool_cls, patch(
        "app.services.pageindex_service.as_completed",
        side_effect=lambda futures: list(futures),
    ):
        mock_pool = MagicMock()
        mock_pool.__enter__.return_value = mock_pool
        mock_pool.__exit__.return_value = False

        def submit(_fn, job, question):
            fut = MagicMock()
            fut.result.return_value = fake_tree_search(job, question)
            return fut

        mock_pool.submit.side_effect = submit
        mock_pool_cls.return_value = mock_pool

        hits = retrieve_pageindex_hits_for_qa(
            MagicMock(),
            MagicMock(),
            docs,
            "测试问题",
            limit=5,
        )

    assert len(hits) == 3
    assert call_count["n"] == 3
    mock_pool_cls.assert_called_once()
    assert mock_pool_cls.call_args.kwargs["max_workers"] == 3


def test_flatten_pageindex_structure_text():
    structure = [
        {
            "node_id": "1",
            "title": "第一章",
            "text": "总则内容",
            "nodes": [
                {"node_id": "1.1", "title": "第一节", "text": "细则 A"},
            ],
        },
        {"node_id": "2", "title": "第二章", "text": "附则"},
    ]
    text = flatten_pageindex_structure_text(structure)
    assert "总则内容" in text
    assert "细则 A" in text
    assert "附则" in text
    assert text.index("总则内容") < text.index("细则 A") < text.index("附则")


def test_load_qa_parsed_documents_prefers_pageindex():
    from unittest.mock import patch

    from app.services.pageindex_service import load_qa_parsed_documents

    doc = SimpleNamespace(id=uuid.uuid4(), title="报告")
    parsed = SimpleNamespace(
        document_id=doc.id,
        file_name="报告.pdf",
        full_text="PageIndex 正文",
        pages=[],
        parse_quality="pageindex",
        warning=None,
    )
    db = MagicMock()
    with patch(
        "app.services.pageindex_service.parsed_document_from_pageindex",
        return_value=parsed,
    ) as mock_pi:
        out = load_qa_parsed_documents(db, [doc])
    assert len(out) == 1
    assert out[0].full_text == "PageIndex 正文"
    mock_pi.assert_called_once_with(db, doc)
