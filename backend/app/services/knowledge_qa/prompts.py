"""Knowledge QA — 提示词与 KG 上下文."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.org import User
from app.services.knowledge_qa.constants import (
    KG_QA_SYSTEM_APPENDIX,
    KNOWLEDGE_QA_SYSTEM,
)


def _resolve_kg_qa_context(db: Session, user: User, question: str):
    from app.core.permissions import user_has_permission
    from app.services.kg_service import retrieve_kg_context_for_question

    if not user_has_permission(db, user, "feature.kg"):
        return None
    return retrieve_kg_context_for_question(db, user, question)


def _qa_system_prompt(*, include_kg: bool) -> str:
    if include_kg:
        return KNOWLEDGE_QA_SYSTEM + KG_QA_SYSTEM_APPENDIX
    return KNOWLEDGE_QA_SYSTEM


def _answer_prefix_blocks(
    *,
    plan: dict[str, Any],
    changelog_block: str,
    diff_summary_block: str,
) -> str:
    parts: list[str] = []
    if diff_summary_block and "version_compare" in plan.get("intents", []):
        parts.append(diff_summary_block)
    if changelog_block and "version_compare" in plan.get("intents", []):
        parts.append(changelog_block)
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def _build_qa_llm_messages(
    *,
    question: str,
    context: str,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> list[dict[str, str]]:
    from app.core.prompt_budget import build_bounded_qa_messages

    system = _qa_system_prompt(include_kg=include_kg)
    if insufficient_note:
        system += (
            "\n\n【材料不足】当前检索材料可能不足以完整回答。"
            f"不足方面：{insufficient_note}。"
            "请基于已有片段尽力回答；并在回答**末尾**用一小段明确、友好地提示用户可补充哪些具体信息"
            "（如时间范围、指标、文档范围），不要编造缺失数据。"
        )
    return build_bounded_qa_messages(system=system, question=question, context=context)


