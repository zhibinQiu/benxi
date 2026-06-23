"""引用 PDF 页渲染兜底测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes
from app.integrations.citation_pdf_preview import (
    bbox_to_fitz_rect,
    ragflow_bbox_to_fitz_rect,
    render_pdf_page_image,
)


def test_render_pdf_page_image_returns_png():
    pdf = markdown_text_to_pdf_bytes("测试", "## 正文\n\n引用预览兜底。")
    try:
        data, mime = render_pdf_page_image(pdf, page_num=1)
    except RuntimeError as e:
        if "pymupdf" in str(e).lower():
            pytest.skip("pymupdf not installed")
        raise
    assert mime == "image/png"
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_apply_image_highlight_wash_changes_bytes():
    try:
        import fitz
    except ImportError:
        pytest.skip("pymupdf not installed")

    from app.integrations.citation_pdf_preview import apply_image_highlight_wash

    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((20, 50), "highlight wash")
    raw = doc.tobytes("png")
    doc.close()

    washed, mime = apply_image_highlight_wash(raw, "image/png")
    assert mime == "image/png"
    assert washed != raw
    assert len(washed) > 0


def test_render_pdf_page_image_with_highlight_bbox():
    pdf = markdown_text_to_pdf_bytes("测试", "## 正文\n\n高亮区域测试。")
    try:
        plain, _ = render_pdf_page_image(pdf, page_num=1, bbox=None)
        highlighted, _ = render_pdf_page_image(
            pdf,
            page_num=1,
            bbox=[100, 800, 100, 250],
            bbox_format="ragflow_lrtb",
        )
    except RuntimeError as e:
        if "pymupdf" in str(e).lower():
            pytest.skip("pymupdf not installed")
        raise
    assert plain != highlighted


def test_bbox_to_fitz_rect_normalized():
    try:
        import fitz
    except ImportError:
        pytest.skip("pymupdf not installed")
    rect = bbox_to_fitz_rect([0.1, 0.1, 0.5, 0.3], 595.0, 842.0)
    assert rect is not None
    assert isinstance(rect, fitz.Rect)
    assert rect.width > 0 and rect.height > 0


def test_ragflow_lrtb_bbox_on_a4_page():
    try:
        import fitz
    except ImportError:
        pytest.skip("pymupdf not installed")
    rect = ragflow_bbox_to_fitz_rect([100, 800, 100, 250], 595.0, 842.0)
    assert rect is not None
    assert rect.width > 100
    assert rect.height > 50


def test_fetch_citation_pdf_page_fallback_uses_platform_pdf(monkeypatch):
    from app.services.knowledge_qa import preview as svc

    pdf = markdown_text_to_pdf_bytes("体检通知", "公司员工体检安排说明。")
    fake_link = MagicMock(
        platform_document_id="13db152d-201e-4d9a-aec8-e50fb95e3395",
        platform_version_id="00000000-0000-0000-0000-000000000001",
    )
    fake_doc = MagicMock(
        id=fake_link.platform_document_id,
        deleted_at=None,
        title="体检通知",
        description="",
    )
    fake_version = MagicMock(
        file_key="k",
        file_name="通知.md",
        mime_type="text/markdown",
    )
    db = MagicMock()
    user = MagicMock()

    monkeypatch.setattr(svc, "get_document", lambda _db, _id: fake_doc)
    monkeypatch.setattr(
        "app.services.ragflow_version_link_service.get_version_link_by_ragflow_id",
        lambda _db, _rid: fake_link,
    )
    monkeypatch.setattr(
        "app.core.permissions.can_access_document",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(db, "get", lambda _cls, _id: fake_version)
    monkeypatch.setattr(
        "app.storage.object_store.get_object_store",
        lambda: MagicMock(get_object_bytes=lambda _k: "# 正文\n\n内容".encode()),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_chunk_anchor_for_citation",
        lambda *_a, **_k: {"page": 1},
    )

    with patch(
        "app.integrations.citation_pdf_preview.render_pdf_page_image",
        wraps=render_pdf_page_image,
    ) as render:
        try:
            result = svc._fetch_citation_pdf_page_fallback(
                db,
                user,
                chunk_id="abc",
                dataset_id="ds",
                ragflow_document_id="rag",
            )
        except RuntimeError as e:
            if "pymupdf" in str(e).lower():
                pytest.skip("pymupdf not installed")
            raise
    assert result is not None
    data, mime = result
    assert mime == "image/png"
    render.assert_called_once()
