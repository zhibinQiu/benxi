from __future__ import annotations

from app.integrations.paddleocr_client import is_openai_compatible_ocr_base
from app.schemas.ocr import OcrBlockOut, OcrExportIn, OcrExportItemIn, OcrPageOut
from app.services.ocr_service import blocks_to_markdown, build_export_zip, get_meta


def test_openai_compatible_ocr_base_detection():
    assert is_openai_compatible_ocr_base("https://api.siliconflow.cn/v1")
    assert not is_openai_compatible_ocr_base("http://127.0.0.1:8080/layout-parsing")
    assert not is_openai_compatible_ocr_base("http://127.0.0.1:7071/ocr")


def test_blocks_to_markdown_with_pages():
    pages = [
        OcrPageOut(page=1, text="第一页", blocks=[]),
        OcrPageOut(page=2, text="第二页", blocks=[]),
    ]
    md = blocks_to_markdown("demo.png", pages)
    assert "# demo.png" in md
    assert "## 第 1 页" in md
    assert "第一页" in md
    assert "## 第 2 页" in md


def test_build_export_zip_markdown_and_json():
    item = OcrExportItemIn(
        file_name="sample.png",
        text="hello",
        markdown="# sample.png\n\nhello\n",
        blocks=[OcrBlockOut(text="hello", page=1)],
        pages=[OcrPageOut(page=1, text="hello", blocks=[OcrBlockOut(text="hello", page=1)])],
    )
    md_zip = build_export_zip(OcrExportIn(format="markdown", items=[item]))
    json_zip = build_export_zip(OcrExportIn(format="json", items=[item]))
    assert len(md_zip) > 100
    assert len(json_zip) > 100
    assert md_zip != json_zip


def test_get_meta_unconfigured(monkeypatch):
    from app.services import ocr_service as ocr_service_mod

    monkeypatch.setattr(
        ocr_service_mod,
        "get_paddleocr_credentials",
        lambda db: ("", "", ""),
    )
    meta = get_meta(None)
    assert not meta.configured
    assert meta.service_hint
