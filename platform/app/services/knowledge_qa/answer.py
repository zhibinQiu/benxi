"""Knowledge QA — 回答生成."""

from __future__ import annotations

import logging
import re

import httpx

from app.services.knowledge_qa.citations import (
    build_aligned_qa_context_and_citations,
)
from app.services.knowledge_qa.constants import MINDMAP_SYSTEM, NO_HIT_ANSWER
from app.services.knowledge_qa.prompts import _build_qa_llm_messages
from app.services.knowledge_qa.text import strip_meta_footer

logger = logging.getLogger(__name__)


def _call_llm_answer(
    *,
    question: str,
    context: str,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> str | None:
    from app.integrations.deepseek_client import chat_completion_sync

    messages = _build_qa_llm_messages(
        question=question,
        context=context,
        include_kg=include_kg,
        insufficient_note=insufficient_note,
    )
    return chat_completion_sync(
        messages=messages,
        temperature=0.2,
    )


def _normalize_mindmap_source(text: str, *, question: str) -> str:
    raw = (text or "").strip()
    fenced = re.match(r"^```(?:mermaid)?\s*\n([\s\S]*?)\n```\s*$", raw, re.I)
    if fenced:
        raw = fenced.group(1).strip()
    if raw.lower().startswith("mindmap"):
        return raw
    root = (question or "检索要点").strip()[:36] or "检索要点"
    lines = [f"mindmap", f"  root(({root}))"]
    for line in raw.splitlines():
        label = line.strip().lstrip("-*# ").strip()
        if label:
            lines.append(f"    {label[:48]}")
    return "\n".join(lines)


def generate_knowledge_mindmap(*, question: str, answer: str) -> str | None:
    """对齐 KnowFlow：将检索回答结构化为 Mermaid 思维导图。"""
    question = (question or "").strip()
    answer = strip_meta_footer(answer or "")
    if not answer:
        return None
    from app.integrations.deepseek_client import is_configured, resolve_credentials

    from app.core.prompt_budget import llm_completion_extras, truncate_to_budget

    if not is_configured():
        return None
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return None
    user_content = (
        f"问题：{question}\n\n"
        f"回答：\n{truncate_to_budget(answer, 6000)}"
    )
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": MINDMAP_SYSTEM},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.1,
                    **llm_completion_extras(),
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
            if not content:
                return None
            return _normalize_mindmap_source(content, question=question)
    except Exception as exc:
        logger.warning("知识检索思维导图生成失败: %s", exc)
        return None


def _fallback_answer(question: str, hits: list[dict], doc_titles: dict[str, str]) -> str:
    lines = [f"根据已选文档，与「{question}」相关的要点如下：", ""]
    for i, h in enumerate(hits, start=1):
        snippet = (h.get("highlight") or h.get("snippet") or "")[:400]
        lines.append(f"- {snippet} [{i}]")
    return "\n".join(lines)


def generate_answer(
    *,
    question: str,
    hits: list[dict],
    doc_titles: dict[str, str],
    context: str | None = None,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> str:
    if context is None:
        context, _ = build_aligned_qa_context_and_citations(
            hits,
            doc_titles,
            question=question,
        )
    if not (context or "").strip():
        if insufficient_note:
            return f"{NO_HIT_ANSWER}\n\n如需继续，请补充：{insufficient_note}"
        return NO_HIT_ANSWER
    llm_answer = _call_llm_answer(
        question=question,
        context=context,
        include_kg=include_kg,
        insufficient_note=insufficient_note,
    )
    if llm_answer:
        return strip_meta_footer(llm_answer)
    if hits:
        return _fallback_answer(question, hits, doc_titles)
    return NO_HIT_ANSWER


