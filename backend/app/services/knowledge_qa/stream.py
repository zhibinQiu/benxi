"""Knowledge QA — 流式问答编排."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.uuid_utils import parse_uuid_list
from app.domains.knowledge import knowledge
from app.models.org import User
from app.models.rag import RagMessage, RagSession
from app.services.knowledge_qa.answer import (
    _fallback_answer,
    generate_answer,
)
from app.services.knowledge_qa.text import strip_meta_footer
from app.services.knowledge_qa.citations import (
    build_aligned_qa_context_and_citations,
    finalize_qa_answer_and_citations,
)
from app.services.knowledge_qa.constants import NO_HIT_ANSWER
from app.services.knowledge_qa.metadata import _doc_citation_meta, _doc_titles
from app.services.knowledge_qa.prompts import (
    _answer_prefix_blocks,
    _build_qa_llm_messages,
    _resolve_kg_qa_context,
)
from app.services.knowledge_qa.retrieval import (
    retrieve_hits_for_qa,
)

logger = logging.getLogger(__name__)


def _resolve_qa_session(
    db: Session,
    user: User,
    *,
    session_id: str | None,
    document_ids: list[str] | None,
) -> RagSession:
    from app.core.exceptions import bad_request, not_found

    if session_id:
        sid = uuid.UUID(session_id)
        session = db.get(RagSession, sid)
        if not session or session.created_by != user.id:
            raise not_found("会话不存在")
        return session
    if not document_ids:
        raise bad_request("请从左侧选择知识库或文档")
    from app.services import rag_service

    return rag_service.create_session(
        db,
        user,
        document_ids=document_ids,
        title="知识检索",
    )


def _begin_knowledge_qa_stream(
    db: Session,
    user_id: uuid.UUID,
    *,
    question: str,
    session_id: str | None,
    document_ids: list[str] | None,
) -> dict[str, Any]:
    from app.core.async_db import resolve_db_user
    from app.core.user_messages import (
        KNOWLEDGE_SERVICE_UNAVAILABLE,
        http_exception_message,
    )
    from fastapi import HTTPException

    user = resolve_db_user(db, user_id)
    try:
        session = _resolve_qa_session(
            db,
            user,
            session_id=session_id,
            document_ids=document_ids,
        )
    except HTTPException as exc:
        return {
            "error": http_exception_message(exc, fallback=KNOWLEDGE_SERVICE_UNAVAILABLE)
            or "请求失败"
        }
    except Exception:
        logger.exception("knowledge qa session begin failed")
        return {"error": "检索失败，请稍后重试。"}

    db.add(RagMessage(session_id=session.id, role="user", content=question))
    db.flush()
    db.commit()
    return {
        "session_id": session.id,
        "doc_ids": parse_uuid_list(session.document_ids),
    }


def _gather_qa_agentic(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[str],
    question: str,
    *,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    from app.core.async_db import resolve_db_user
    from app.services.knowledge_agentic_service import (
        RESULT_MARKER,
        AgenticQaGatherResult,
        iter_gather_for_knowledge_qa,
    )

    user = resolve_db_user(db, user_id)
    agentic: AgenticQaGatherResult | None = None
    for item in iter_gather_for_knowledge_qa(db, user, doc_ids, question, emit=emit):
        if RESULT_MARKER in item:
            agentic = item[RESULT_MARKER]
    if agentic is None:
        agentic = AgenticQaGatherResult(
            hits=[],
            mode="none",
            kg_ctx=None,
            plan_reasoning="",
            rounds_used=0,
            sub_questions=[question],
        )
    return agentic


def _gather_qa_simple(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[str],
    question: str,
) -> AgenticQaGatherResult:
    from app.core.async_db import resolve_db_user
    from app.services.knowledge_agentic_service import AgenticQaGatherResult

    user = resolve_db_user(db, user_id)
    hits: list[dict] = []
    mode = "none"
    if doc_ids:
        hits, mode = retrieve_hits_for_qa(db, user, doc_ids, question)
    kg_ctx = _resolve_kg_qa_context(db, user, question)
    return AgenticQaGatherResult(
        hits=hits,
        mode=mode,
        kg_ctx=kg_ctx,
        plan_reasoning="",
        rounds_used=1,
        sub_questions=[question],
    )


def _prepare_qa_stream_bundle(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[str],
    question: str,
    agentic: AgenticQaGatherResult,
) -> dict[str, Any]:
    from app.core.async_db import resolve_db_user
    from app.services.kg_service import merge_kg_qa_into_context
    from app.services.knowledge_agent_service import (
        format_changelog_context,
        format_diff_summary_context,
        load_version_changelogs,
        load_version_diff_summaries,
        plan_knowledge_query,
    )

    user = resolve_db_user(db, user_id)
    hits = agentic.hits
    mode = agentic.mode
    kg_ctx = agentic.kg_ctx
    doc_titles = _doc_titles(db, doc_ids)
    doc_meta = _doc_citation_meta(db, doc_ids)
    context, all_citations = build_aligned_qa_context_and_citations(
        hits,
        doc_titles,
        question=question,
        doc_meta=doc_meta,
    )
    context, all_citations = merge_kg_qa_into_context(context, all_citations, kg_ctx)
    include_kg = bool(kg_ctx and kg_ctx.context_text)
    kf = knowledge.client_for_user(db, user)
    plan = plan_knowledge_query(
        question=question,
        document_count=len(doc_ids),
        knowflow_available=bool(kf.enabled()),
    )
    if agentic.plan_reasoning:
        plan = {**plan, "agentic_reasoning": agentic.plan_reasoning}
    changelogs = load_version_changelogs(db, doc_ids)
    diff_summaries = load_version_diff_summaries(db, doc_ids)
    prefix = _answer_prefix_blocks(
        plan=plan,
        changelog_block=format_changelog_context(changelogs, doc_titles),
        diff_summary_block=format_diff_summary_context(diff_summaries, doc_titles),
    )
    return {
        "context": context,
        "all_citations": all_citations,
        "include_kg": include_kg,
        "prefix": prefix,
        "mode": mode,
        "insufficient_note": agentic.insufficient_note,
        "kg_ctx": kg_ctx,
        "hits": hits,
        "doc_titles": doc_titles,
    }


def _persist_qa_assistant_turn(
    db: Session,
    *,
    session_id: uuid.UUID,
    answer: str,
    citations: list[dict],
) -> uuid.UUID:
    msg = RagMessage(
        session_id=session_id,
        role="assistant",
        content=answer,
        citations=citations,
    )
    db.add(msg)
    from datetime import datetime, timezone

    session = db.get(RagSession, session_id)
    if session:
        session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return session_id


async def iter_knowledge_qa_stream(
    *,
    user_id: uuid.UUID,
    question: str,
    session_id: str | None = None,
    document_ids: list[str] | None = None,
    use_agentic: bool = True,
) -> AsyncIterator[str]:
    from app.core.async_db import run_db_task
    from app.services.knowledge_agentic_service import agentic_enabled

    question = question.strip()
    if not question:
        yield json.dumps({"error": "问题不能为空"}, ensure_ascii=False)
        return

    begin = await run_db_task(
        _begin_knowledge_qa_stream,
        user_id,
        question=question,
        session_id=session_id,
        document_ids=document_ids,
    )
    if begin.get("error"):
        yield json.dumps({"error": begin["error"]}, ensure_ascii=False)
        return

    session_id_val = begin["session_id"]
    doc_ids = begin["doc_ids"]

    if use_agentic and agentic_enabled():
        loop = asyncio.get_running_loop()
        event_q: asyncio.Queue[Any] = asyncio.Queue()
        gather_holder: dict[str, Any] = {}

        def emit_workflow(ev: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(event_q.put_nowait, ev)

        async def run_agentic_gather() -> None:
            try:
                gather_holder["agentic"] = await run_db_task(
                    _gather_qa_agentic,
                    user_id,
                    doc_ids,
                    question,
                    emit=emit_workflow,
                )
            finally:
                loop.call_soon_threadsafe(event_q.put_nowait, None)

        gather_task = asyncio.create_task(run_agentic_gather())
        while True:
            item = await event_q.get()
            if item is None:
                break
            yield json.dumps({"workflow": item}, ensure_ascii=False)
            await asyncio.sleep(0)
        await gather_task
        agentic = gather_holder.get("agentic")
        if agentic is None:
            from app.services.knowledge_agentic_service import AgenticQaGatherResult

            agentic = AgenticQaGatherResult(
                hits=[],
                mode="none",
                kg_ctx=None,
                plan_reasoning="",
                rounds_used=0,
                sub_questions=[question],
            )
    else:
        yield json.dumps(
            {"workflow": {"phase": "workflow_started", "title": "开始检索"}},
            ensure_ascii=False,
        )
        await asyncio.sleep(0)
        yield json.dumps(
            {"workflow": {"phase": "node_started", "title": "正在检索相关文档"}},
            ensure_ascii=False,
        )
        await asyncio.sleep(0)
        agentic = await run_db_task(_gather_qa_simple, user_id, doc_ids, question)

    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": "正在整理检索结果"}},
        ensure_ascii=False,
    )
    await asyncio.sleep(0)
    bundle = await run_db_task(
        _prepare_qa_stream_bundle, user_id, doc_ids, question, agentic
    )
    context = bundle["context"]
    all_citations = bundle["all_citations"]
    include_kg = bundle["include_kg"]
    prefix = bundle["prefix"]
    mode = bundle["mode"]
    kg_ctx = bundle["kg_ctx"]

    if kg_ctx and getattr(kg_ctx, "matched_entity_ids", None):
        yield json.dumps(
            {
                "workflow": {
                    "phase": "node_started",
                    "title": "正在解析知识图谱关联",
                }
            },
        ensure_ascii=False,
    )

    answer_think_id = f"answer-{uuid.uuid4().hex[:8]}"
    yield json.dumps(
        {
            "workflow": {
                "phase": "agent_thinking",
                "title": "正在组织回答",
                "detail": "分析检索材料并生成回答…",
                "tool": "llm",
                "step_id": answer_think_id,
            }
        },
        ensure_ascii=False,
    )
    await asyncio.sleep(0)

    answer_parts: list[str] = []
    if prefix:
        answer_parts.append(prefix)
        yield json.dumps({"delta": prefix}, ensure_ascii=False)

    insufficient_note = bundle["insufficient_note"]
    if not (context or "").strip():
        yield json.dumps(
            {
                "workflow": {
                    "phase": "agent_thought",
                    "title": "无需生成回答",
                    "detail": "未检索到可用材料",
                    "tool": "llm",
                    "step_id": answer_think_id,
                    "status": "done",
                }
            },
            ensure_ascii=False,
        )
        if insufficient_note:
            insuff = (
                f"{NO_HIT_ANSWER}\n\n"
                f"如需继续，请补充：{insufficient_note}"
            )
            answer_parts.append(insuff)
            yield json.dumps({"delta": insuff}, ensure_ascii=False)
        else:
            answer_parts.append(NO_HIT_ANSWER)
            yield json.dumps({"delta": NO_HIT_ANSWER}, ensure_ascii=False)
    else:
        from app.services.llm_workflow_stream import iter_llm_answer_events

        streamed = False
        async for ev in iter_llm_answer_events(
            messages=_build_qa_llm_messages(
                question=question,
                context=context,
                include_kg=include_kg,
                insufficient_note=insufficient_note,
            ),
            temperature=0.2,
            think_title="正在组织回答",
            think_detail="分析检索材料并生成回答…",
            step_id=answer_think_id,
            skip_initial_thinking=True,
        ):
            if ev.get("type") == "workflow":
                yield json.dumps({"workflow": ev["data"]}, ensure_ascii=False)
                await asyncio.sleep(0)
            elif ev.get("type") == "delta" and ev.get("text"):
                streamed = True
                answer_parts.append(ev["text"])
                yield json.dumps({"delta": ev["text"]}, ensure_ascii=False)
        if not streamed:
            yield json.dumps(
                {
                    "workflow": {
                        "phase": "agent_thought",
                        "title": "模型未返回内容",
                        "detail": "使用检索摘要回退",
                        "tool": "llm",
                        "step_id": answer_think_id,
                        "status": "done",
                    }
                },
                ensure_ascii=False,
            )
            hits = bundle["hits"]
            doc_titles = bundle["doc_titles"]
            fallback = (
                _fallback_answer(question, hits, doc_titles)
                if hits
                else NO_HIT_ANSWER
            )
            answer_parts.append(fallback)
            yield json.dumps({"delta": fallback}, ensure_ascii=False)

    answer = strip_meta_footer("".join(answer_parts))
    answer, citations = finalize_qa_answer_and_citations(answer, all_citations)

    if citations:
        yield json.dumps({"citations": citations}, ensure_ascii=False)

    await run_db_task(
        _persist_qa_assistant_turn,
        session_id=session_id_val,
        answer=answer,
        citations=citations,
    )

    yield json.dumps(
        {"workflow": {"phase": "workflow_finished", "title": "完成"}},
        ensure_ascii=False,
    )

    yield json.dumps(
        {
            "done": True,
            "reply": answer,
            "citations": citations,
            "conversation_id": str(session_id_val),
        },
        ensure_ascii=False,
    )


def answer_knowledge_question(
    db: Session,
    session: RagSession,
    user: User,
    question: str,
    *,
    use_agentic: bool = True,
) -> RagMessage:
    question = question.strip()
    if not question:
        from app.core.exceptions import bad_request

        raise bad_request("问题不能为空")

    db.add(RagMessage(session_id=session.id, role="user", content=question))
    db.flush()

    doc_ids = parse_uuid_list(session.document_ids)
    from app.services.knowledge_agentic_service import (
        AgenticQaGatherResult,
        agentic_enabled,
        gather_for_knowledge_qa,
    )

    if use_agentic and agentic_enabled():
        agentic = gather_for_knowledge_qa(db, user, doc_ids, question)
    else:
        hits: list[dict] = []
        mode = "none"
        if doc_ids:
            hits, mode = retrieve_hits_for_qa(db, user, doc_ids, question)
        kg_ctx = _resolve_kg_qa_context(db, user, question)
        agentic = AgenticQaGatherResult(
            hits=hits,
            mode=mode,
            kg_ctx=kg_ctx,
            plan_reasoning="",
            rounds_used=1,
            sub_questions=[question],
        )
    hits = agentic.hits
    doc_titles = _doc_titles(db, doc_ids)
    doc_meta = _doc_citation_meta(db, doc_ids)
    kg_ctx = agentic.kg_ctx
    context, all_citations = build_aligned_qa_context_and_citations(
        hits,
        doc_titles,
        question=question,
        doc_meta=doc_meta,
    )
    from app.services.kg_service import merge_kg_qa_into_context

    context, all_citations = merge_kg_qa_into_context(
        context, all_citations, kg_ctx
    )
    include_kg = bool(kg_ctx and kg_ctx.context_text)
    answer = generate_answer(
        question=question,
        hits=hits,
        doc_titles=doc_titles,
        context=context,
        include_kg=include_kg,
        insufficient_note=agentic.insufficient_note,
    )

    from app.services.knowledge_agent_service import (
        enrich_answer_with_plan,
        format_changelog_context,
        format_diff_summary_context,
        load_version_changelogs,
        load_version_diff_summaries,
        plan_knowledge_query,
    )

    kf = knowledge.client_for_user(db, user)
    plan = plan_knowledge_query(
        question=question,
        document_count=len(doc_ids),
        knowflow_available=bool(kf.enabled()),
    )
    changelogs = load_version_changelogs(db, doc_ids)
    diff_summaries = load_version_diff_summaries(db, doc_ids)
    answer = enrich_answer_with_plan(
        answer,
        plan=plan,
        changelog_block=format_changelog_context(changelogs, doc_titles),
        diff_summary_block=format_diff_summary_context(diff_summaries, doc_titles),
    )
    answer = strip_meta_footer(answer)
    answer, citations = finalize_qa_answer_and_citations(answer, all_citations)

    msg = RagMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        citations=citations,
    )
    db.add(msg)
    from datetime import datetime, timezone

    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg
