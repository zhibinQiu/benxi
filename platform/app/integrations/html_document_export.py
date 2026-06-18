"""将 HTML 正文转为 KnowFlow / RAGFlow 可解析、有足够字数的 Markdown 文件。"""

from __future__ import annotations

import logging
import re
import uuid

from app.integrations.html_markdown import _plain_text_to_html, html_to_markdown

logger = logging.getLogger(__name__)

# RAGFlow naive 分块需要足够正文，否则解析后知识库中几乎不可见
MIN_ARTICLE_PLAIN_CHARS = 200

_INDEXABLE_SUFFIXES = (
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
    ".csv",
    ".xlsx",
    ".xls",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
)


def file_supports_knowflow_original_upload(file_name: str, mime_type: str = "") -> bool:
    """KnowFlow 应上传原文件（或由 normalize 转为 PDF），以支持引用溯源页截图。"""
    lower = (file_name or "").lower()
    mime = (mime_type or "").lower()
    if any(lower.endswith(s) for s in _INDEXABLE_SUFFIXES):
        return True
    if mime == "application/pdf":
        return True
    if "word" in mime or "spreadsheet" in mime or "excel" in mime:
        return True
    if "presentation" in mime or "powerpoint" in mime:
        return True
    if mime.startswith("image/"):
        return True
    if mime.startswith("text/"):
        return True
    return False


_OFFICE_SUFFIXES = (".doc", ".docx", ".rtf", ".xlsx", ".xls", ".ppt", ".pptx")


def _is_office_like_file(file_name: str, mime_type: str = "") -> bool:
    lower = (file_name or "").lower()
    mime = (mime_type or "").lower()
    if any(lower.endswith(s) for s in _OFFICE_SUFFIXES):
        return True
    return (
        "word" in mime
        or "spreadsheet" in mime
        or "excel" in mime
        or "presentation" in mime
        or "powerpoint" in mime
    )


def knowflow_copy_lacks_page_snapshots(
    version_file_name: str,
    version_mime: str,
    knowflow_file_name: str,
) -> bool:
    """KnowFlow 副本若来自 Markdown 分块导出，则无页级引用截图，需重新同步原文件。"""
    kf = (knowflow_file_name or "").lower()
    orig = (version_file_name or "").lower()
    if kf.endswith(".md"):
        return True
    if not file_supports_knowflow_original_upload(version_file_name, version_mime):
        return False
    if kf.endswith(".pdf") and not orig.endswith(".pdf") and _is_office_like_file(
        version_file_name, version_mime
    ):
        return True
    return False


def office_bytes_to_markdown_upload(
    file_name: str,
    content: bytes,
    mime_type: str = "",
    *,
    title: str = "",
) -> tuple[str, bytes, str] | None:
    """Office 无法转 PDF 时，提取正文为 Markdown 供 naive + Plain Text 分块。"""
    from app.integrations.text_extract import extract_text_from_bytes

    name = (file_name or "").strip() or "document"
    try:
        parsed = extract_text_from_bytes(
            content,
            document_id=uuid.UUID(int=0),
            file_name=name,
            mime_type=mime_type or "",
        )
    except Exception as exc:
        logger.debug("Office Markdown 回退提取失败 file=%s: %s", name, exc)
        return None
    body = (parsed.full_text or "").strip()
    if not body:
        return None
    doc_title = (title or name.rsplit(".", 1)[0]).strip() or "文档"
    if not body.lstrip().startswith("#"):
        md = f"# {doc_title}\n\n{body}"
    else:
        md = body
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return f"{stem}.md", md.encode("utf-8"), "text/markdown"


def convert_file_bytes_to_pdf_for_citation(
    file_name: str,
    content: bytes,
    mime_type: str,
    *,
    title: str = "",
) -> tuple[str, bytes, str] | None:
    """将 Office / 文本等转为 PDF，供引用截图兜底渲染。"""
    name = (file_name or "").strip() or "document"
    lower = name.lower()
    mime = (mime_type or "").lower()
    doc_title = title or name.rsplit(".", 1)[0]

    if lower.endswith(".pdf") or mime == "application/pdf":
        if content.startswith(b"%PDF"):
            return name, content, mime_type or "application/pdf"
        return None

    text: str | None = None
    if _is_office_like_file(name, mime) or any(
        lower.endswith(s) for s in (".txt", ".csv", ".log", ".json", ".xml", ".yaml", ".yml")
    ) or (mime.startswith("text/") and "html" not in mime and "markdown" not in mime):
        from app.integrations.text_extract import extract_text_from_bytes

        try:
            parsed = extract_text_from_bytes(
                content,
                document_id=uuid.UUID(int=0),
                file_name=name,
                mime_type=mime_type or "",
            )
            text = (parsed.full_text or "").strip()
            if not text and parsed.warning:
                logger.debug(
                    "引用预览提取文本为空 file=%s warning=%s",
                    name,
                    parsed.warning,
                )
        except Exception as exc:
            logger.debug("引用预览提取文本失败 file=%s: %s", name, exc)
            text = None

    if not text:
        return None

    from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes

    pdf = markdown_text_to_pdf_bytes(doc_title, text)
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return f"{stem}.pdf", pdf, "application/pdf"


_LINK_IN_DESC_RE = re.compile(
    r"(?:链接|原文)[：:]\s*(https?://\S+)",
    re.IGNORECASE,
)


def _safe_base_name(title: str, fallback: str = "article") -> str:
    safe = "".join(c for c in (title or "") if c.isalnum() or c in "._- ")[:80].strip()
    return safe or fallback


def plain_text_char_count(*parts: str) -> int:
    """统计若干片段合并后的非空白字符数。"""
    combined = "\n".join((p or "").strip() for p in parts if (p or "").strip())
    if not combined:
        return 0
    if "<" in combined and ">" in combined:
        md = html_to_markdown(combined)
        if md.strip():
            combined = md
        else:
            combined = re.sub(r"<[^>]+>", " ", combined)
    combined = re.sub(r"^#{1,6}\s+", "", combined, flags=re.M)
    combined = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", combined)
    combined = re.sub(r"[*_>`|~-]", "", combined)
    return len(re.sub(r"\s+", "", combined))


def is_thin_article_content(*parts: str) -> bool:
    return plain_text_char_count(*parts) < MIN_ARTICLE_PLAIN_CHARS


def _normalize_html_fragment(html: str) -> str:
    text = (html or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if "<html" in lower or "<!doctype" in lower:
        from app.integrations.web_article_fetcher import _extract_article_html

        chunk = _extract_article_html(text)
        if chunk:
            return chunk
        body_m = re.search(r"<body[^>]*>([\s\S]*?)</body>", text, re.I)
        if body_m:
            return body_m.group(1).strip()
    return text


def _html_to_plain_fallback(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(?:p|div|h[1-6]|li|tr)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r" +", " ", text).strip()


def refetch_article_html(url: str) -> tuple[str, str]:
    """按链接重新抓取正文 HTML 与摘要（微信 / 通用网页）。"""
    link = (url or "").strip()
    if not link.startswith(("http://", "https://")):
        return "", ""

    from app.integrations.web_article_fetcher import (
        WebArticleFetchError,
        fetch_web_article,
        is_wechat_article_url,
    )

    if is_wechat_article_url(link):
        from app.integrations.wechat_mp_fetcher import WechatMpFetchError, fetch_article

        try:
            article = fetch_article(link)
            return article.content_html or "", article.summary or ""
        except WechatMpFetchError as e:
            logger.info("refetch wechat article failed %s: %s", link, e)
            return "", ""

    try:
        parsed = fetch_web_article(link)
        return parsed.content_html or "", parsed.summary or ""
    except WebArticleFetchError as e:
        logger.info("refetch web article failed %s: %s", link, e)
        return "", ""


def link_from_document_description(description: str) -> str:
    m = _LINK_IN_DESC_RE.search(description or "")
    return m.group(1).rstrip(").,;") if m else ""


def resolve_article_html_body(
    html_body: str,
    *,
    summary: str = "",
    link: str = "",
    allow_refetch: bool = True,
) -> tuple[str, str]:
    """在导入/同步前尽量拿到足够长的 HTML 正文。"""
    html = _normalize_html_fragment(html_body)
    summary_text = (summary or "").strip()

    if not is_thin_article_content(html, summary_text):
        return html, summary_text

    if allow_refetch and link:
        ref_html, ref_summary = refetch_article_html(link)
        ref_html = _normalize_html_fragment(ref_html)
        if ref_html and plain_text_char_count(ref_html, ref_summary) > plain_text_char_count(
            html, summary_text
        ):
            html = ref_html
            summary_text = ref_summary or summary_text

    if is_thin_article_content(html, summary_text) and summary_text:
        plain_in_html = re.sub(r"\s+", "", _html_to_plain_fallback(html))
        plain_summary = re.sub(r"\s+", "", summary_text)
        if plain_summary and plain_summary not in plain_in_html:
            extra = _plain_text_to_html(summary_text)
            html = f"{html or ''}{extra}".strip()

    return html, summary_text


def build_substantive_article_markdown(
    title: str,
    html_body: str,
    *,
    summary: str = "",
    link: str = "",
    source_label: str = "",
) -> str:
    """组装含标题、摘要、正文与来源信息的 Markdown。"""
    title_text = (title or "").strip()
    summary_text = (summary or "").strip()
    html = _normalize_html_fragment(html_body)

    body_md = html_to_markdown(html)
    if plain_text_char_count(body_md) < 80 and html.strip():
        body_md = _html_to_plain_fallback(html)

    parts: list[str] = []
    if title_text:
        parts.append(f"# {title_text}")

    summary_plain = re.sub(r"\s+", "", summary_text)
    body_plain = re.sub(r"\s+", "", body_md)
    if summary_text and summary_plain and summary_plain not in body_plain[: max(len(summary_plain) + 80, 200)]:
        parts.append(f"> **摘要**：{summary_text}")

    if body_md.strip():
        if not title_text and body_md.lstrip().startswith("#"):
            parts.append(body_md.strip())
        else:
            parts.append(f"## 正文\n\n{body_md.strip()}")
    elif summary_text:
        parts.append(f"## 正文\n\n{summary_text}")
    else:
        parts.append("## 正文\n\n（未能提取到正文，请通过下方原文链接查看完整内容。）")

    meta: list[str] = []
    if source_label:
        meta.append(f"- **来源**：{source_label}")
    link_text = (link or "").strip()
    if link_text:
        meta.append(f"- **原文**：[{link_text}]({link_text})")
    if meta:
        parts.append("---\n\n" + "\n".join(meta))

    md = "\n\n".join(parts).strip()
    if is_thin_article_content(md) and link_text:
        md += (
            f"\n\n> 说明：平台已保存该文章索引，但在线抓取的正文较短。"
            f"若知识库中未显示，请打开原文确认内容是否需登录后可见：{link_text}"
        )
    return md


def html_body_to_indexable_bytes(
    title: str,
    html_body: str,
    *,
    summary: str = "",
    link: str = "",
    source_label: str = "",
    fallback_stem: str = "article",
    allow_refetch: bool = True,
) -> tuple[str, bytes, str]:
    """生成可供知识库索引的文件名、内容与 MIME（Markdown，仅测试/兼容，生产入库请用 PDF）。"""
    html, summary_text = resolve_article_html_body(
        html_body,
        summary=summary,
        link=link,
        allow_refetch=allow_refetch,
    )
    md = build_substantive_article_markdown(
        title,
        html,
        summary=summary_text,
        link=link,
        source_label=source_label,
    )
    file_name = f"{_safe_base_name(title, fallback_stem)}.md"
    return file_name, md.encode("utf-8"), "text/markdown; charset=utf-8"


def html_body_to_pdf_bytes(
    title: str,
    html_body: str,
    *,
    summary: str = "",
    link: str = "",
    source_label: str = "",
    fallback_stem: str = "article",
    allow_refetch: bool = True,
) -> tuple[str, bytes, str]:
    """生成 PDF 文件名、二进制内容与 MIME（订阅/资讯导入文档库、KnowFlow 同步）。"""
    from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes

    html, summary_text = resolve_article_html_body(
        html_body,
        summary=summary,
        link=link,
        allow_refetch=allow_refetch,
    )
    md = build_substantive_article_markdown(
        title,
        html,
        summary=summary_text,
        link=link,
        source_label=source_label,
    )
    pdf = markdown_text_to_pdf_bytes(title, md)
    file_name = f"{_safe_base_name(title, fallback_stem)}.pdf"
    return file_name, pdf, "application/pdf"


def normalize_file_for_knowflow_upload(
    file_name: str,
    content: bytes,
    mime_type: str,
    *,
    title: str = "",
    description: str = "",
    allow_refetch: bool = True,
) -> tuple[str, bytes, str]:
    """上传 KnowFlow 前：HTML/Markdown 转为 PDF；已是 PDF 则原样上传。"""
    name = (file_name or "").strip() or "document"
    lower = name.lower()
    mime = (mime_type or "").lower()
    doc_title = title or name.rsplit(".", 1)[0]
    link = link_from_document_description(description)

    if lower.endswith(".pdf") or mime == "application/pdf":
        if content.startswith(b"%PDF"):
            return name, content, mime_type or "application/pdf"
        if link:
            return html_body_to_pdf_bytes(
                doc_title,
                "",
                link=link,
                allow_refetch=allow_refetch,
                fallback_stem="article",
            )

    if lower.endswith(".html") or lower.endswith(".htm") or "html" in mime:
        try:
            html_text = content.decode("utf-8", errors="replace")
        except Exception:
            html_text = ""
        return html_body_to_pdf_bytes(
            doc_title,
            html_text,
            link=link,
            allow_refetch=allow_refetch,
            fallback_stem="article",
        )

    if lower.endswith(".md") or "markdown" in mime:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        if is_thin_article_content(text) and link:
            return html_body_to_pdf_bytes(
                doc_title,
                "",
                link=link,
                allow_refetch=allow_refetch,
                fallback_stem="article",
            )
        from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes

        pdf = markdown_text_to_pdf_bytes(doc_title, text)
        pdf_name = name if lower.endswith(".pdf") else f"{name.rsplit('.', 1)[0]}.pdf"
        return pdf_name, pdf, "application/pdf"

    text_like_suffixes = (".txt", ".csv", ".log", ".json", ".xml", ".yaml", ".yml")
    if any(lower.endswith(s) for s in text_like_suffixes) or (
        mime.startswith("text/")
        and "html" not in mime
        and "markdown" not in mime
    ):
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        if text.strip():
            from app.integrations.article_pdf_export import markdown_text_to_pdf_bytes

            pdf = markdown_text_to_pdf_bytes(doc_title, text)
            stem = name.rsplit(".", 1)[0] if "." in name else name
            return f"{stem}.pdf", pdf, "application/pdf"

    if _is_office_like_file(name, mime):
        converted = convert_file_bytes_to_pdf_for_citation(
            name,
            content,
            mime_type,
            title=doc_title,
        )
        if converted:
            logger.info(
                "KnowFlow 上传：Office 转为 PDF 以生成引用页截图 file=%s",
                name,
            )
            return converted
        md_upload = office_bytes_to_markdown_upload(
            name,
            content,
            mime_type,
            title=doc_title,
        )
        if md_upload:
            logger.info(
                "KnowFlow 上传：Office 转 PDF 失败，改上传 Markdown file=%s",
                name,
            )
            return md_upload

    if any(lower.endswith(s) for s in _INDEXABLE_SUFFIXES):
        return name, content, mime_type or "application/octet-stream"

    return name, content, mime_type or "application/octet-stream"
