"""知识 Agent 规划层：在检索/生成前梳理意图与数据来源。

RAG 负责「从哪段切片找答案」；本模块负责「先想清楚要什么、从哪些源取数」。
后续可接入 LLM 规划器，当前以规则 + 平台元数据为主。
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVersion

_VERSION_COMPARE_HINTS = (
    "对比",
    "比较",
    "差异",
    "区别",
    "变化",
    "改了",
    "更新了什么",
    "changelog",
    "版本",
    "v1",
    "v2",
    "v3",
)

_DATA_SOURCE_LABELS = {
    "knowflow_chunks": "知识库向量切片（RAG）",
    "local_fulltext": "文档本地全文检索",
    "version_changelogs": "版本变更说明",
    "document_metadata": "文档标题与分级元数据",
}


def _detect_intents(question: str) -> list[str]:
    q = (question or "").strip().lower()
    intents: list[str] = []
    if any(h in q for h in _VERSION_COMPARE_HINTS):
        intents.append("version_compare")
    if re.search(r"\bv\d+\b", q):
        intents.append("version_compare")
    if not intents:
        intents.append("document_qa")
    return intents


def _choose_data_sources(intents: list[str], *, knowflow_available: bool) -> list[str]:
    sources: list[str] = ["document_metadata"]
    if "version_compare" in intents:
        sources.append("version_changelogs")
    if knowflow_available:
        sources.append("knowflow_chunks")
    else:
        sources.append("local_fulltext")
    # 去重且保持顺序
    seen: set[str] = set()
    ordered: list[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def load_version_changelogs(
    db: Session, document_ids: list[uuid.UUID]
) -> dict[str, list[dict[str, Any]]]:
    """按文档返回各版本变更说明（含未填写的空串）。"""
    if not document_ids:
        return {}
    rows = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id.in_(document_ids))
        .order_by(DocumentVersion.document_id, DocumentVersion.version_no.asc())
    ).all()
    out: dict[str, list[dict[str, Any]]] = {}
    for ver in rows:
        key = str(ver.document_id)
        out.setdefault(key, []).append(
            {
                "version_id": str(ver.id),
                "version_no": ver.version_no,
                "change_description": (ver.change_description or "").strip(),
                "is_current": False,
            }
        )
    docs = db.scalars(select(Document).where(Document.id.in_(document_ids))).all()
    current_map = {str(d.id): str(d.current_version_id) for d in docs if d.current_version_id}
    for key, items in out.items():
        cur = current_map.get(key)
        for item in items:
            item["is_current"] = item["version_id"] == cur
    return out


def plan_knowledge_query(
    *,
    question: str,
    document_count: int,
    knowflow_available: bool,
) -> dict[str, Any]:
    intents = _detect_intents(question)
    primary = intents[0]
    sources = _choose_data_sources(intents, knowflow_available=knowflow_available)
    reasoning_parts = [
        f"识别意图：{primary}",
        f"已选 {document_count} 份文档作为检索范围",
    ]
    if "version_compare" in intents:
        reasoning_parts.append("将结合版本变更说明与切片内容辅助对比")
    if knowflow_available:
        reasoning_parts.append("使用知识库混合检索（语义 + 关键词）并由 LLM 组织回答")
    else:
        reasoning_parts.append("知识服务未就绪，回退本地全文检索")
    return {
        "intent": primary,
        "intents": intents,
        "data_sources": sources,
        "data_source_labels": [_DATA_SOURCE_LABELS.get(s, s) for s in sources],
        "reasoning": "；".join(reasoning_parts),
    }


def format_changelog_context(
    changelogs: dict[str, list[dict[str, Any]]],
    doc_titles: dict[str, str],
) -> str:
    if not changelogs:
        return ""
    lines = ["【版本变更说明】"]
    for did, versions in changelogs.items():
        title = doc_titles.get(did, did)
        for v in versions:
            note = v.get("change_description") or "（未填写变更说明）"
            cur = "，当前版本" if v.get("is_current") else ""
            lines.append(f"- {title} v{v.get('version_no')}{cur}：{note}")
    return "\n".join(lines)


def load_version_diff_summaries(
    db: Session, document_ids: list[uuid.UUID]
) -> dict[str, list[dict[str, Any]]]:
    """按文档返回已入库的相邻版本 diff 摘要（含 LLM 总结）。"""
    if not document_ids:
        return {}
    from app.models.document_version_compare import DocumentVersionCompareRelation

    rows = db.scalars(
        select(DocumentVersionCompareRelation)
        .where(
            DocumentVersionCompareRelation.document_id.in_(document_ids),
            DocumentVersionCompareRelation.status == "done",
        )
        .order_by(
            DocumentVersionCompareRelation.document_id,
            DocumentVersionCompareRelation.created_at.asc(),
        )
    ).all()
    out: dict[str, list[dict[str, Any]]] = {}
    for rel in rows:
        key = str(rel.document_id)
        payload = rel.payload or {}
        out.setdefault(key, []).append(
            {
                "from_version_no": payload.get("from_version_no"),
                "to_version_no": payload.get("to_version_no"),
                "diff_count": rel.diff_count,
                "llm_summary": (rel.llm_summary or "").strip(),
                "relation_type": rel.relation_type,
            }
        )
    return out


def format_diff_summary_context(
    summaries: dict[str, list[dict[str, Any]]],
    doc_titles: dict[str, str],
) -> str:
    if not summaries:
        return ""
    lines = ["【版本差异摘要（Git diff 入库）】"]
    for did, rows in summaries.items():
        title = doc_titles.get(did, did)
        for row in rows:
            fno = row.get("from_version_no")
            tno = row.get("to_version_no")
            summary = row.get("llm_summary") or f"共 {row.get('diff_count', 0)} 处差异"
            lines.append(f"- {title} v{fno}→v{tno}：{summary}")
    return "\n".join(lines)


def enrich_answer_with_plan(
    answer: str,
    *,
    plan: dict[str, Any],
    changelog_block: str,
    diff_summary_block: str = "",
) -> str:
    parts: list[str] = []
    if diff_summary_block and "version_compare" in plan.get("intents", []):
        parts.append(diff_summary_block)
        parts.append("")
    if changelog_block and "version_compare" in plan.get("intents", []):
        parts.append(changelog_block)
        parts.append("")
    parts.append(answer)
    return "\n".join(parts)
