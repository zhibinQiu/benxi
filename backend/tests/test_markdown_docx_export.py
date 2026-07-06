"""Markdown 导出 Word 测试。"""

from __future__ import annotations

import base64
import io
import zipfile

from app.integrations.markdown_docx_export import (
    build_docx_download_filename,
    markdown_to_docx_bytes,
    prepare_report_markdown_for_export,
    strip_export_citation_markers,
    strip_report_generation_preamble,
)

# 2x2 PNG（PIL 生成的有效 PNG）
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
)


def test_markdown_to_docx_bytes_basic():
    data = markdown_to_docx_bytes(
        title="测试报告",
        markdown_text="# 摘要\n\n这是**重点**内容。\n\n## 背景\n\n- 条目一\n- 条目二",
    )
    assert isinstance(data, bytes)
    assert len(data) > 800
    assert data[:2] == b"PK"


def test_markdown_to_docx_embeds_png_image():
    data_uri = f"data:image/png;base64,{base64.b64encode(_TINY_PNG).decode()}"
    md = f"# 章节\n\n![测试图]({data_uri})\n"
    data = markdown_to_docx_bytes(title="图测试", markdown_text=md)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        media = [n for n in zf.namelist() if n.startswith("word/media/")]
    assert media, "docx 应包含嵌入图片"


def test_markdown_to_docx_skips_mermaid_fence_text(monkeypatch):
    captured: dict[str, str] = {}

    def fake_render(source: str) -> bytes | None:
        captured["source"] = source
        return _TINY_PNG

    monkeypatch.setattr(
        "app.integrations.markdown_docx_export._render_mermaid_png",
        fake_render,
    )
    md = "# 概览\n\n```mermaid\nflowchart TD\n  A[\"开始\"] --> B[\"结束\"]\n```\n"
    data = markdown_to_docx_bytes(title="Mermaid", markdown_text=md)
    assert "flowchart TD" in captured.get("source", "")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "flowchart TD" not in xml


def test_build_docx_download_filename():
    assert build_docx_download_filename("全国碳市场报告").endswith(".docx")
    assert "/" not in build_docx_download_filename('bad/name')


def test_strip_report_generation_preamble():
    raw = (
        "好的，遵照您的指示，我将以「小析」的身份，为您撰写一份关于智慧能碳平台的建设方案报告。\n\n"
        "# 烟台城市智慧能碳管理平台建设方案\n\n"
        "正文段落。"
    )
    out = strip_report_generation_preamble(raw)
    assert out.startswith("# 烟台")
    assert "遵照您的指示" not in out


def test_strip_export_citation_markers():
    text = "结论一 [1]。另一事实【2】。"
    assert strip_export_citation_markers(text) == "结论一 。另一事实。"


def test_prepare_report_markdown_for_export():
    raw = (
        "好的，我将为您撰写报告。\n\n"
        "## 摘要\n\n"
        "要点 [1][2]。\n\n"
        "## 参考来源\n- 文档A"
    )
    out = prepare_report_markdown_for_export(raw)
    assert out.startswith("## 摘要")
    assert "[1]" not in out
    assert "参考来源" not in out
    assert "好的" not in out


def test_markdown_to_docx_export_strips_preamble_and_citations():
    md = (
        "好的，遵照指示撰写报告。\n\n"
        "## 章节\n\n"
        "内容 [1]。\n"
    )
    data = markdown_to_docx_bytes(title="导出测试", markdown_text=md, for_export=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "遵照指示" not in xml
    assert "[1]" not in xml
    assert "内容" in xml

