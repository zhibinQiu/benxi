"""将文章 HTML / Markdown 转为可下载、可入 KnowFlow 的 PDF 文件。"""

from __future__ import annotations

import io
import logging
import re
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

logger = logging.getLogger(__name__)

_FONT_REGISTERED = False
_CN_FONT = "STSong-Light"
_LINK_MD_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _ensure_cn_font() -> str:
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont(_CN_FONT))
        _FONT_REGISTERED = True
    return _CN_FONT


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    safe = escape((text or "").strip()).replace("\n", "<br/>")
    return Paragraph(safe or " ", style)


def markdown_text_to_pdf_bytes(title: str, markdown_text: str) -> bytes:
    """把结构化 Markdown 文本渲染为 PDF（内置中文字体，无需系统字体包）。"""
    font = _ensure_cn_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=(title or "article")[:120],
    )
    title_style = ParagraphStyle(
        "ArticleTitle",
        fontName=font,
        fontSize=16,
        leading=22,
        spaceAfter=10,
    )
    h2_style = ParagraphStyle(
        "ArticleH2",
        fontName=font,
        fontSize=13,
        leading=18,
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ArticleBody",
        fontName=font,
        fontSize=11,
        leading=16,
        spaceAfter=5,
        alignment=TA_JUSTIFY,
    )
    quote_style = ParagraphStyle(
        "ArticleQuote",
        fontName=font,
        fontSize=10,
        leading=14,
        spaceAfter=5,
        leftIndent=8 * mm,
    )
    ParagraphStyle(
        "ArticleMeta",
        fontName=font,
        fontSize=9,
        leading=12,
        spaceAfter=4,
        textColor="#555555",
    )

    story: list = []
    for raw in (markdown_text or "").splitlines():
        line = raw.rstrip()
        if not line:
            story.append(Spacer(1, 5))
            continue
        if line.startswith("# "):
            story.append(_paragraph(line[2:].strip(), title_style))
        elif line.startswith("## "):
            story.append(_paragraph(line[3:].strip(), h2_style))
        elif line.startswith("> "):
            story.append(_paragraph(line[2:].strip(), quote_style))
        elif line.startswith("- "):
            plain = _LINK_MD_RE.sub(r"\1 (\2)", line[2:].strip())
            story.append(_paragraph(f"• {plain}", body_style))
        elif line.strip() == "---":
            story.append(Spacer(1, 8))
        else:
            plain = _LINK_MD_RE.sub(r"\1 (\2)", line)
            story.append(_paragraph(plain, body_style))

    if not story:
        story.append(_paragraph(title or "（无正文）", body_style))

    try:
        doc.build(story)
    except Exception as e:
        logger.exception("PDF build failed: %s", e)
        raise

    data = buf.getvalue()
    if not data.startswith(b"%PDF"):
        raise ValueError("生成的 PDF 无效")
    return data
