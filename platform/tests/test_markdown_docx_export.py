"""Markdown 导出 Word 测试。"""

from __future__ import annotations

from app.integrations.markdown_docx_export import (
    build_docx_download_filename,
    markdown_to_docx_bytes,
)


def test_markdown_to_docx_bytes_basic():
    data = markdown_to_docx_bytes(
        title="测试报告",
        markdown_text="# 摘要\n\n这是**重点**内容。\n\n## 背景\n\n- 条目一\n- 条目二",
    )
    assert isinstance(data, bytes)
    assert len(data) > 800
    assert data[:2] == b"PK"


def test_build_docx_download_filename():
    assert build_docx_download_filename("全国碳市场报告").endswith(".docx")
    assert "/" not in build_docx_download_filename('bad/name')
