"""将文章 HTML / Markdown 转为可下载、可入 KnowFlow 的 PDF 文件。"""

from __future__ import annotations

import io
import logging
import os
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

_RESOLVED_FONT: str | None = None
_EMBEDDED_CJK_FONT = "ArticleCJK"
_FALLBACK_CID_FONT = "STSong-Light"
_LINK_MD_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Docker 镜像已装 fonts-wqy-microhei；macOS 开发机可用 PingFang / STHeiti
_CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)


def _ensure_cn_font() -> str:
    """优先嵌入 TTF/TTC，便于 pdf.js 浏览器预览；无系统字体时回退 CID。"""
    global _RESOLVED_FONT
    if _RESOLVED_FONT:
        return _RESOLVED_FONT

    from reportlab.pdfbase.ttfonts import TTFont

    for path in _CJK_FONT_CANDIDATES:
        if not os.path.isfile(path):
            continue
        try:
            kwargs: dict = {}
            if path.lower().endswith(".ttc"):
                kwargs["subfontIndex"] = 0
            pdfmetrics.registerFont(TTFont(_EMBEDDED_CJK_FONT, path, **kwargs))
            _RESOLVED_FONT = _EMBEDDED_CJK_FONT
            logger.debug("article PDF font: %s (%s)", _EMBEDDED_CJK_FONT, path)
            return _RESOLVED_FONT
        except Exception as exc:
            logger.debug("article PDF font skip %s: %s", path, exc)

    pdfmetrics.registerFont(UnicodeCIDFont(_FALLBACK_CID_FONT))
    _RESOLVED_FONT = _FALLBACK_CID_FONT
    logger.warning(
        "article PDF 使用 CID 字体 %s，浏览器内预览可能无法显示中文",
        _FALLBACK_CID_FONT,
    )
    return _RESOLVED_FONT


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
