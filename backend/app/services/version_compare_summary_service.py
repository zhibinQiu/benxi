"""版本对比 LLM 总结与问答（基于入库 diff）。"""

from __future__ import annotations

import logging
import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.document import DocumentVersion
from app.models.document_version_compare import (
    DocumentVersionCompareRelation,
    DocumentVersionDiffItem,
    VersionCompareStatus,
)

logger = logging.getLogger(__name__)

_MAX_DIFF_FOR_LLM = 40
_MAX_CHARS_PER_DIFF = 600


def _rule_based_summary(
    from_no: int | None,
    to_no: int | None,
    items: list[DocumentVersionDiffItem],
    *,
    change_description: str = "",
) -> str:
    if not items:
        base = f"v{from_no} → v{to_no}：两版本正文一致，未发现差异。"
        if change_description:
            return f"{base}\n版本说明：{change_description}"
        return base
    counts = {"add": 0, "delete": 0, "modify": 0}
    for it in items:
        counts[it.diff_type] = counts.get(it.diff_type, 0) + 1
    parts: list[str] = []
    if change_description:
        parts.append(f"版本说明：{change_description}")
    parts.extend(
        [
            f"v{from_no} → v{to_no} 共 {len(items)} 处差异",
            f"新增 {counts.get('add', 0)}、删除 {counts.get('delete', 0)}、修改 {counts.get('modify', 0)}。",
        ]
    )
    samples: list[str] = []
    for it in items[:5]:
        text = (it.text_right or it.text_left or "").strip().replace("\n", " ")
        if text:
            samples.append(f"- [{it.diff_type}] {text[:120]}")
    if samples:
        parts.append("主要变化：")
        parts.extend(samples)
    return "\n".join(parts)


def _build_llm_prompt(
    from_no: int | None,
    to_no: int | None,
    items: list[DocumentVersionDiffItem],
    *,
    change_description: str = "",
) -> str:
    lines = [f"文档版本 v{from_no} → v{to_no} 的差异片段：", ""]
    if change_description:
        lines.append(f"上传者填写的版本说明：{change_description}")
        lines.append("")
    for i, it in enumerate(items[:_MAX_DIFF_FOR_LLM], start=1):
        left = (it.text_left or "").strip()[:_MAX_CHARS_PER_DIFF]
        right = (it.text_right or "").strip()[:_MAX_CHARS_PER_DIFF]
        if it.diff_type == "add":
            lines.append(f"{i}. [新增] {right}")
        elif it.diff_type == "delete":
            lines.append(f"{i}. [删除] {left}")
        else:
            lines.append(f"{i}. [修改] 旧：{left} / 新：{right}")
    return "\n".join(lines)


_SUMMARY_SYSTEM = (
    "你是文档版本对比助手。根据 diff 片段用中文写 3–6 条要点，"
    "概括相对旧版的主要变化，不要编造未出现的内容。"
)
_ASK_SYSTEM = (
    "你是文档版本对比问答助手。仅根据提供的差异摘要与片段回答用户问题，"
    "中文简洁条目化，不要编造未出现的内容。"
)


def _call_llm_chat(*, system: str, user_content: str) -> str | None:
    if not is_configured():
        return None
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return None
    settings = get_settings()
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": user_content[: settings.deepseek_max_chars],
                        },
                    ],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return content or None
    except Exception as exc:
        logger.warning("版本对比 LLM 总结失败: %s", exc)
        return None


def generate_relation_summary(db: Session, relation_id: uuid.UUID) -> None:
    rel = db.get(DocumentVersionCompareRelation, relation_id)
    if not rel or rel.status != VersionCompareStatus.done.value:
        return
    items = list(
        db.scalars(
            select(DocumentVersionDiffItem)
            .where(DocumentVersionDiffItem.relation_id == relation_id)
            .order_by(DocumentVersionDiffItem.id.asc())
        ).all()
    )
    from_no = (rel.payload or {}).get("from_version_no")
    to_no = (rel.payload or {}).get("to_version_no")
    to_ver = db.get(DocumentVersion, rel.to_version_id) if rel.to_version_id else None
    change_description = (to_ver.change_description or "").strip() if to_ver else ""

    prompt = _build_llm_prompt(
        from_no, to_no, items, change_description=change_description
    )
    summary = (
        _call_llm_chat(system=_SUMMARY_SYSTEM, user_content=prompt) if items else None
    )
    if not summary:
        summary = _rule_based_summary(
            from_no,
            to_no,
            items,
            change_description=change_description,
        )

    rel.llm_summary = summary
    rel.llm_summary_status = "done"
    db.commit()


def answer_version_compare_question(
    db: Session,
    rel: DocumentVersionCompareRelation,
    question: str,
) -> str:
    """基于入库 diff + 总结回答版本差异问题（规则检索 + 可选 LLM）。"""
    q = (question or "").strip()
    if not q:
        from app.core.exceptions import bad_request

        raise bad_request("请输入问题")

    items = list(
        db.scalars(
            select(DocumentVersionDiffItem)
            .where(DocumentVersionDiffItem.relation_id == rel.id)
            .order_by(DocumentVersionDiffItem.id.asc())
        ).all()
    )
    if rel.status != VersionCompareStatus.done.value:
        return "版本对比尚未完成，请稍后再试。"

    summary = (rel.llm_summary or "").strip()
    to_ver = db.get(DocumentVersion, rel.to_version_id) if rel.to_version_id else None
    change_description = (to_ver.change_description or "").strip() if to_ver else ""
    if not items:
        if change_description:
            return summary or f"两版本内容一致。版本说明：{change_description}"
        return summary or "两版本内容一致，未发现差异。"

    terms = [t for t in re.split(r"\s+", q) if len(t) >= 2]
    matched: list[DocumentVersionDiffItem] = []
    for it in items:
        blob = f"{it.text_left or ''} {it.text_right or ''}"
        if not terms or any(t in blob for t in terms):
            matched.append(it)
    picked = matched[:8] if matched else items[:8]

    lines = []
    if change_description:
        lines.append("【上传者版本说明】")
        lines.append(change_description)
        lines.append("")
    if summary:
        lines.append("【版本变化摘要】")
        lines.append(summary)
        lines.append("")
    lines.append("【相关差异片段】")
    for i, it in enumerate(picked, start=1):
        text = (it.text_right or it.text_left or "").strip().replace("\n", " ")
        lines.append(f"{i}. [{it.diff_type}] {text[:280]}")

    llm_answer = None
    if is_configured():
        ctx = "\n".join(lines)
        user_msg = f"用户问题：{q}\n\n{ctx}"
        llm_answer = _call_llm_chat(system=_ASK_SYSTEM, user_content=user_msg)
    if llm_answer:
        return llm_answer
    return "\n".join(lines)
