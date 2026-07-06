"""跨文档 LLM 对比：提取正文后直接由语言模型归纳差异。"""

from __future__ import annotations

import difflib
import logging
import re

from app.config import get_settings
from app.core.llm_parse import parse_llm_json
from app.core.text_utils import truncate_text
from app.integrations.deepseek_client import chat_completion_sync, is_configured
from app.integrations.text_extract import ParsedDocument

logger = logging.getLogger(__name__)

_MAX_DOC_CHARS = 6000
_MAX_DIFF_ITEMS = 30
_MIN_TEXT_SIMILARITY_FOR_NO_DIFF = 0.82

_COMPARE_SYSTEM = (
    "你是跨文档对比专家。用户给出两份**不同文档**的全文，请对比主题、观点、事实、数据与结论的差异。"
    "仅输出 JSON，不要 markdown 代码块，格式："
    '{"summary":"3-6条跨文档差异要点（中文）","differences":[{"diff_type":"add|delete|modify",'
    '"text_left":"参照文档原文片段或空","text_right":"对比文档原文片段或空",'
    '"description":"差异简述"}]}'
    "规则："
    "1) 这是跨文档对比，不是同一文档的版本修订；主题完全不同也必须列出 differences。"
    "2) 仅参照文档有的内容用 delete；仅对比文档有的用 add；同一话题不同表述用 modify。"
    "3) 每侧尽量引用原文短片段（20-120字），并附 description。"
    "4) 至少输出 3 条 differences；仅当两份正文几乎完全一致时才返回空数组。"
    "5) 不要编造文档中不存在的内容。"
)

_RETRY_USER_SUFFIX = (
    "\n\n【重要】上一份结果 differences 为空，但两份文档主题与正文明显不同。"
    "请重新输出 JSON，differences 至少 5 条，分别概括两侧独有或不同的关键信息。"
)


def _text_similarity(left: str, right: str) -> float:
    a = (left or "").strip()[:8000]
    b = (right or "").strip()[:8000]
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _build_user_prompt(base: ParsedDocument, other: ParsedDocument) -> str:
    settings = get_settings()
    per_doc = min(_MAX_DOC_CHARS, max(2000, settings.deepseek_max_chars // 3))
    left = truncate_text(base.full_text, per_doc)
    right = truncate_text(other.full_text, per_doc)
    left_title = (base.file_name or "参照文档").rsplit(".", 1)[0]
    right_title = (other.file_name or "对比文档").rsplit(".", 1)[0]
    return (
        f"【参照文档】{left_title}\n{left}\n\n"
        f"【对比文档】{right_title}\n{right}"
    )


def _normalize_diff_items(raw_items: list) -> list[dict]:
    out: list[dict] = []
    for it in raw_items[:_MAX_DIFF_ITEMS]:
        if not isinstance(it, dict):
            continue
        dtype = str(it.get("diff_type") or "modify").lower()
        if dtype not in ("add", "delete", "modify"):
            dtype = "modify"
        text_left = (it.get("text_left") or "").strip() or None
        text_right = (it.get("text_right") or "").strip() or None
        desc = (it.get("description") or "").strip()
        if not text_left and not text_right and not desc:
            continue
        if dtype == "add" and not text_right and desc:
            text_right = desc
        elif dtype == "delete" and not text_left and desc:
            text_left = desc
        elif dtype == "modify" and not text_left and not text_right and desc:
            text_left = desc
            text_right = desc
        out.append(
            {
                "diff_type": dtype,
                "text_left": text_left,
                "text_right": text_right,
                "anchor_json": {
                    "page": 1,
                    "bbox": None,
                    "kind": "llm",
                    "description": desc or None,
                },
            }
        )
    return out


def _split_sections(text: str) -> list[str]:
    parts = re.split(r"\n{2,}|(?=正文\s*\n)", (text or "").strip())
    chunks = [p.strip() for p in parts if len(p.strip()) >= 20]
    if chunks:
        return chunks[:8]
    lines = [ln.strip() for ln in (text or "").splitlines() if len(ln.strip()) >= 20]
    return lines[:8]


def _excerpt_contrast_items(
    base: ParsedDocument,
    other: ParsedDocument,
) -> list[dict]:
    """LLM 未产出结构化差异时，用章节摘录生成最小可展示差异。"""
    left_parts = _split_sections(base.full_text)
    right_parts = _split_sections(other.full_text)
    items: list[dict] = []
    pair_count = max(len(left_parts), len(right_parts), 1)
    for idx in range(min(pair_count, 6)):
        left = truncate_text(left_parts[idx] if idx < len(left_parts) else base.full_text, 360)
        right = truncate_text(
            right_parts[idx] if idx < len(right_parts) else other.full_text,
            360,
        )
        if not left and not right:
            continue
        items.append(
            {
                "diff_type": "modify",
                "text_left": left or None,
                "text_right": right or None,
                "anchor_json": {
                    "page": 1,
                    "bbox": None,
                    "kind": "excerpt",
                    "description": f"段落对比 {idx + 1}",
                },
            }
        )
    if not items:
        items.append(
            {
                "diff_type": "modify",
                "text_left": truncate_text(base.full_text, 360) or None,
                "text_right": truncate_text(other.full_text, 360) or None,
                "anchor_json": {
                    "page": 1,
                    "bbox": None,
                    "kind": "excerpt",
                    "description": "全文摘录对比",
                },
            }
        )
    return items[:_MAX_DIFF_ITEMS]


def _call_compare_llm(*, user_content: str) -> str | None:
    return chat_completion_sync(
        messages=[
            {"role": "system", "content": _COMPARE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        timeout=120.0,
    )


def _looks_like_no_diff_summary(summary: str) -> bool:
    s = (summary or "").strip()
    if not s:
        return False
    markers = ("无实质差异", "未发现差异", "内容一致", "完全相同", "没有差异")
    return any(m in s for m in markers)


def compare_documents_with_llm(
    base: ParsedDocument,
    other: ParsedDocument,
) -> tuple[list[dict], str]:
    """返回 (diff_items, summary)。LLM 不可用时抛出 ValueError。"""
    if not is_configured():
        raise ValueError("语言模型未配置，请在资源管理中配置 LLM")

    left_text = (base.full_text or "").strip()
    right_text = (other.full_text or "").strip()
    if not left_text and not right_text:
        raise ValueError("两份文档均未提取到正文，请先完成解析或索引后再对比")
    if not left_text or not right_text:
        missing = "参照文档" if not left_text else "对比文档"
        raise ValueError(f"{missing}未提取到正文，请先完成解析或索引后再对比")

    similarity = _text_similarity(left_text, right_text)
    prompt = _build_user_prompt(base, other)
    raw = _call_compare_llm(user_content=prompt)
    if not raw:
        raise ValueError("语言模型对比失败，请稍后重试")

    data = parse_llm_json(raw)
    if not data:
        logger.warning("LLM 对比返回非 JSON: %s", (raw or "")[:500])
        raise ValueError("语言模型返回格式异常，请重试")

    summary = (data.get("summary") or "").strip()
    items = _normalize_diff_items(data.get("differences") or [])

    need_retry = (
        not items
        and similarity < _MIN_TEXT_SIMILARITY_FOR_NO_DIFF
    ) or (
        not items
        and _looks_like_no_diff_summary(summary)
        and similarity < 0.95
    )
    if need_retry:
        retry_raw = _call_compare_llm(user_content=prompt + _RETRY_USER_SUFFIX)
        retry_data = parse_llm_json(retry_raw or "")
        if retry_data:
            retry_summary = (retry_data.get("summary") or "").strip()
            retry_items = _normalize_diff_items(retry_data.get("differences") or [])
            if retry_items:
                items = retry_items
                if retry_summary:
                    summary = retry_summary
            elif retry_summary:
                summary = retry_summary

    if not items and similarity < _MIN_TEXT_SIMILARITY_FOR_NO_DIFF:
        items = _excerpt_contrast_items(base, other)
        if not summary or _looks_like_no_diff_summary(summary):
            left_title = (base.file_name or "参照文档").rsplit(".", 1)[0]
            right_title = (other.file_name or "对比文档").rsplit(".", 1)[0]
            summary = (
                f"两份文档主题与内容差异明显（文本相似度约 {int(similarity * 100)}%）。"
                f"参照《{left_title}》与对比《{right_title}》已从正文摘录生成 {len(items)} 处对比项。"
            )
        logger.info(
            "LLM 未返回结构化差异，已回退摘录对比 similarity=%.2f items=%s",
            similarity,
            len(items),
        )
    elif not items and not summary:
        summary = "两份文档正文高度一致，未发现差异。"
    elif not summary and items:
        summary = f"共发现 {len(items)} 处差异。"

    return items, summary
