"""Agentic RAG 编排：LLM 规划子问题 / 检索策略，多轮 retrieve 与充足性评估。"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.llm_parse import parse_llm_json
from app.integrations.deepseek_client import chat_completion_sync, is_configured
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.knowledge_agentic_tools import KnowledgeAgenticToolkit, ToolResult

logger = logging.getLogger(__name__)

RESULT_MARKER = "_agentic_result"

_step_seq = 0


def _next_step_id() -> str:
    global _step_seq
    _step_seq += 1
    return f"agent-s{_step_seq}"


def _workflow_event(
    phase: str,
    *,
    title: str,
    detail: str = "",
    tool: str = "",
    status: str = "running",
    step_id: str = "",
) -> dict[str, Any]:
    ev: dict[str, Any] = {"phase": phase, "title": title, "status": status}
    if detail:
        ev["detail"] = detail
    if tool:
        ev["tool"] = tool
    if step_id:
        ev["step_id"] = step_id
    return ev


WorkflowEmit = Callable[[dict[str, Any]], None]


@dataclass
class AgenticQaGatherResult:
    hits: list[dict]
    mode: str
    kg_ctx: Any | None
    plan_reasoning: str
    rounds_used: int
    sub_questions: list[str]
    insufficient_note: str | None = None
    tool_summaries: list[str] = field(default_factory=list)


@dataclass
class AgenticReportGatherResult:
    local_hits: list[dict]
    web_items: list[dict]
    doc_titles: dict[str, str]
    plan_reasoning: str
    rounds_used: int
    local_queries: list[str]
    web_queries: list[str]
    insufficient_note: str | None = None
    tool_summaries: list[str] = field(default_factory=list)
    version_changelog_block: str = ""
    version_diff_block: str = ""


def agentic_enabled() -> bool:
    settings = get_settings()
    return bool(settings.knowledge_agentic_enabled and is_configured())


def _unique_queries(queries: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = (q or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q.strip())
        if len(out) >= limit:
            break
    return out


def _emit_wf(emit: WorkflowEmit | None, event: dict[str, Any]) -> None:
    if emit:
        emit(event)


def _tool_call_event(tool: str, title: str, detail: str) -> tuple[str, dict[str, Any]]:
    sid = _next_step_id()
    return sid, _workflow_event(
        "tool_call",
        title=title,
        detail=detail,
        tool=tool,
        step_id=sid,
    )


def _tool_result_event(
    tool: str,
    title: str,
    detail: str,
    step_id: str,
    *,
    ok: bool,
) -> dict[str, Any]:
    return _workflow_event(
        "tool_result",
        title=title,
        detail=detail,
        tool=tool,
        step_id=step_id,
        status="done" if ok else "failed",
    )


def _plan_qa_sub_questions(
    *,
    question: str,
    document_count: int,
    kg_context: str,
    user_id: uuid.UUID | None = None,
    doc_ids: list[uuid.UUID] | None = None,
) -> tuple[list[str], str]:
    from app.services.agent_plan_cache_service import (
        PLAN_TYPE_KNOWLEDGE_QA,
        knowledge_qa_scope_key,
        lookup_cached_payload,
        store_cached_payload,
    )

    if user_id and doc_ids:
        scope_key = knowledge_qa_scope_key(user_id, doc_ids)
        cached = lookup_cached_payload(
            scope_key,
            question,
            plan_type=PLAN_TYPE_KNOWLEDGE_QA,
        )
        if cached:
            payload = cached.get("payload") or {}
            subs = payload.get("sub_questions") or [question]
            reasoning = str(payload.get("reasoning") or cached.get("intent") or "命中问题缓存")
            if not isinstance(subs, list):
                subs = [question]
            queries = _unique_queries([str(x) for x in subs] + [question], limit=6)
            return queries or [question], reasoning

    settings = get_settings()
    max_q = max(1, min(int(settings.knowledge_agentic_qa_max_sub_questions or 4), 6))
    system = (
        "你是企业知识库检索规划助手。根据用户问题拆解为若干**可独立检索**的子问题，"
        "用于从文档向量库召回片段。仅返回 JSON，格式："
        '{"reasoning":"简要策略","sub_questions":["子问题1","子问题2"]}。'
        f"sub_questions 数量 1～{max_q}，使用简体中文，不要重复原句。"
    )
    user_parts = [
        f"用户问题：{question}",
        f"已选文档数：{document_count}",
    ]
    if kg_context.strip():
        user_parts.append("【本体图谱关联（规划参考，非检索结果）】\n" + kg_context.strip())
    raw = chat_completion_sync(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        temperature=0.2,
        timeout=45.0,
    )
    data = parse_llm_json(raw)
    if not data:
        return [question], "规则回退：单路检索"
    reasoning = str(data.get("reasoning") or "").strip() or "已规划检索子问题"
    subs = data.get("sub_questions") or data.get("queries") or []
    if not isinstance(subs, list):
        subs = [question]
    queries = _unique_queries([str(x) for x in subs] + [question], limit=max_q)

    if user_id and doc_ids and queries:
        store_cached_payload(
            knowledge_qa_scope_key(user_id, doc_ids),
            question,
            plan_type=PLAN_TYPE_KNOWLEDGE_QA,
            intent=reasoning,
            payload={
                "reasoning": reasoning,
                "sub_questions": list(queries),
            },
        )

    return queries or [question], reasoning


def _evaluate_qa_sufficiency(
    *,
    question: str,
    hit_count: int,
    snippet_preview: str,
    kg_context: str,
) -> tuple[bool, str | None, list[str]]:
    """返回 (是否足够, 不足说明, 补充检索词)。"""
    if hit_count == 0:
        return (
            False,
            "在所选文档中未检索到相关内容",
            [question],
        )
    settings = get_settings()
    system = (
        "你是检索质量评估助手。根据用户问题与已召回片段摘要，判断材料是否足以回答。"
        "仅返回 JSON："
        '{"sufficient":true|false,"gaps":"不足时说明缺什么（简短）","extra_queries":["补充检索词"]}。'
        "extra_queries 最多 2 条；sufficient 为 true 时 extra_queries 为空数组。"
    )
    user = (
        f"用户问题：{question}\n"
        f"已召回片段数：{hit_count}\n"
        f"片段摘要（前若干段）：\n{snippet_preview[:3500]}"
    )
    if kg_context.strip():
        user += f"\n\n【图谱上下文】\n{kg_context[:1500]}"
    raw = chat_completion_sync(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        timeout=40.0,
    )
    data = parse_llm_json(raw)
    if not data:
        return hit_count >= 2, None, []
    sufficient = bool(data.get("sufficient"))
    gaps = str(data.get("gaps") or "").strip() or None
    extra = data.get("extra_queries") or []
    if not isinstance(extra, list):
        extra = []
    extra_q = _unique_queries([str(x) for x in extra], limit=2)
    if sufficient:
        return True, None, []
    return False, gaps, extra_q


def _hits_snippet_preview(hits: list[dict], *, max_chars: int = 2400) -> str:
    parts: list[str] = []
    used = 0
    for i, h in enumerate(hits[:12], start=1):
        body = (
            (h.get("highlight") or h.get("snippet") or h.get("content") or "")
            .strip()
        )
        body = re.sub(r"</?(?:em|mark)[^>]*>", "", body, flags=re.I)
        if not body:
            continue
        block = f"[{i}] {body[:280]}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block) + 2
    return "\n".join(parts) if parts else "（无有效片段正文）"


def iter_gather_for_knowledge_qa(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    emit: WorkflowEmit | None = None,
) -> Iterator[dict[str, Any]]:
    """流式 yield workflow 事件；最后一项为 {RESULT_MARKER: AgenticQaGatherResult}。"""
    global _step_seq
    _step_seq = 0
    yield _workflow_event("workflow_started", title="Agent 开始处理")

    toolkit = KnowledgeAgenticToolkit(
        db,
        user,
        doc_ids,
        web_enabled=False,
        include_kg=True,
        retrieve_limit=int(get_settings().knowledge_retrieval_top_k or 5) + 2,
    )
    summaries: list[str] = []

    sid, ev = _tool_call_event("kg_context", "加载本体图谱上下文", question[:80])
    _emit_wf(emit, ev)
    yield ev
    kg_tool = toolkit.kg_planning_context(question)
    kg_detail = kg_tool.summary
    kg_ctx_data = kg_tool.data
    if kg_ctx_data and getattr(kg_ctx_data, "context_text", ""):
        preview = kg_ctx_data.context_text.strip().replace("\n", " ")[:160]
        if preview:
            kg_detail = f"{kg_tool.summary}\n上下文预览：{preview}"
    result_ev = _tool_result_event(
        "kg_context", "本体图谱上下文", kg_detail, sid, ok=kg_tool.ok
    )
    _emit_wf(emit, result_ev)
    yield result_ev

    kg_ctx = kg_tool.data
    kg_plan_text = ""
    if kg_ctx and getattr(kg_ctx, "context_text", ""):
        kg_plan_text = kg_ctx.context_text
        summaries.append(kg_tool.summary)

    settings = get_settings()
    max_rounds = max(1, min(int(settings.knowledge_agentic_max_rounds or 2), 3))

    if not agentic_enabled() or not doc_ids:
        node = _workflow_event("node_started", title="正在检索相关文档")
        _emit_wf(emit, node)
        yield node
        if doc_ids:
            sid, ev = _tool_call_event("retrieve", "知识库检索", question[:96])
            _emit_wf(emit, ev)
            yield ev
            tr = toolkit.retrieve(question)
            summaries.append(tr.summary)
            tre = _tool_result_event(
                "retrieve", "知识库检索", tr.summary, sid, ok=tr.ok
            )
            _emit_wf(emit, tre)
            yield tre
        hits = toolkit.accumulated_local_hits
        mode = "hybrid" if hits else "none"
        yield {
            RESULT_MARKER: AgenticQaGatherResult(
                hits=hits,
                mode=mode,
                kg_ctx=kg_ctx,
                plan_reasoning="单路检索",
                rounds_used=1,
                sub_questions=[question],
                tool_summaries=summaries,
            )
        }
        return

    think_id = _next_step_id()
    think_ev = _workflow_event(
        "agent_thinking",
        title="规划检索策略",
        detail="分析问题并拆解检索子问题…",
        tool="planner",
        step_id=think_id,
    )
    _emit_wf(emit, think_ev)
    yield think_ev
    sub_questions, reasoning = _plan_qa_sub_questions(
        question=question,
        document_count=len(doc_ids),
        kg_context=kg_plan_text,
        user_id=user.id,
        doc_ids=doc_ids,
    )
    plan_detail_parts = [reasoning[:500]] if reasoning else []
    if sub_questions:
        plan_detail_parts.append(
            "检索子问题：" + "；".join(str(q) for q in sub_questions[:4])
        )
    thought_ev = _workflow_event(
        "agent_thought",
        title="规划完成",
        detail="\n".join(plan_detail_parts)[:800],
        tool="planner",
        step_id=think_id,
        status="done",
    )
    _emit_wf(emit, thought_ev)
    yield thought_ev

    rounds = 0
    insufficient_note: str | None = None
    last_mode = "none"

    for round_idx in range(1, max_rounds + 1):
        rounds = round_idx
        queries = sub_questions if round_idx == 1 else []
        if round_idx > 1 and not queries:
            break
        for q in queries:
            sid, ev = _tool_call_event(
                "retrieve",
                f"第 {round_idx} 轮 · 知识库检索",
                q[:120],
            )
            _emit_wf(emit, ev)
            yield ev
            tr = toolkit.retrieve(q)
            summaries.append(tr.summary)
            tre = _tool_result_event(
                "retrieve", "知识库检索", tr.summary, sid, ok=tr.ok
            )
            _emit_wf(emit, tre)
            yield tre
            if tr.ok and tr.data:
                last_mode = str(tr.data.get("mode") or last_mode)

        hits = toolkit.accumulated_local_hits
        eval_id = _next_step_id()
        eval_think = _workflow_event(
            "agent_thinking",
            title="评估材料是否充足",
            detail=f"已召回 {len(hits)} 段片段",
            tool="evaluator",
            step_id=eval_id,
        )
        _emit_wf(emit, eval_think)
        yield eval_think
        sufficient, gaps, extra = _evaluate_qa_sufficiency(
            question=question,
            hit_count=len(hits),
            snippet_preview=_hits_snippet_preview(hits),
            kg_context=kg_plan_text,
        )
        eval_lines = [
            "材料充足，可以生成回答" if sufficient else (gaps or "仍需补充检索")
        ]
        if not sufficient and extra:
            eval_lines.append("建议补充检索：" + "；".join(str(q) for q in extra[:2]))
        eval_done = _workflow_event(
            "agent_thought",
            title="评估完成",
            detail="\n".join(eval_lines)[:600],
            tool="evaluator",
            step_id=eval_id,
            status="done",
        )
        _emit_wf(emit, eval_done)
        yield eval_done

        if sufficient or round_idx >= max_rounds:
            if not sufficient and gaps:
                insufficient_note = gaps
            break
        if extra:
            sub_questions = extra
            sup = _workflow_event(
                "node_started",
                title="材料不足，规划补充检索",
                detail="；".join(extra[:2]),
            )
            _emit_wf(emit, sup)
            yield sup
        else:
            insufficient_note = gaps
            break

    hits = toolkit.accumulated_local_hits
    if len(hits) > 1:
        mode = "mixed" if last_mode != "none" else "hybrid"
    elif hits:
        mode = last_mode if last_mode != "none" else "hybrid"
    else:
        mode = "none"

    yield {
        RESULT_MARKER: AgenticQaGatherResult(
            hits=hits,
            mode=mode,
            kg_ctx=kg_ctx,
            plan_reasoning=reasoning,
            rounds_used=rounds,
            sub_questions=sub_questions,
            insufficient_note=insufficient_note,
            tool_summaries=summaries,
        )
    }


def gather_for_knowledge_qa(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    emit: WorkflowEmit | None = None,
) -> AgenticQaGatherResult:
    result: AgenticQaGatherResult | None = None
    for item in iter_gather_for_knowledge_qa(
        db, user, doc_ids, question, emit=emit
    ):
        if RESULT_MARKER in item:
            result = item[RESULT_MARKER]
    assert result is not None
    return result


def _plan_report_gathering_fallback(
    *,
    message: str,
    topic: str,
    intent: str,
    local_allowed: bool,
    web_allowed: bool,
    history_excerpt: str,
) -> tuple[list[str], list[str], str]:
    """LLM 规划失败时的规则回退；格式调整等场景默认不检索。"""
    from app.services.report_generation_service import (
        build_local_retrieval_queries,
        build_search_queries,
    )

    if intent == "format_adjust" and history_excerpt.strip():
        return [], [], "规则回退：格式调整，沿用对话中的报告正文"
    if not local_allowed and not web_allowed:
        return [], [], "规则回退：未启用本地文档与联网，将依据模型知识与对话历史"
    local: list[str] = []
    web: list[str] = []
    if local_allowed and intent != "format_adjust":
        local = build_local_retrieval_queries(
            message, topic=topic, intent=intent, history=[]
        )
    if web_allowed and intent != "format_adjust":
        web = build_search_queries(message, topic=topic, intent=intent)
    if not local and not web:
        return [], [], "规则回退：判断无需额外检索"
    return local, web, "规则回退：沿用多路召回模板"


def _plan_report_gathering(
    *,
    message: str,
    topic: str,
    intent: str,
    document_count: int,
    web_allowed: bool,
    kg_context: str,
    history_excerpt: str,
) -> tuple[list[str], list[str], str]:
    local_allowed = document_count > 0
    if not local_allowed and not web_allowed:
        return [], [], "未启用本地文档与联网，将依据模型知识与对话历史撰写"

    settings = get_settings()
    max_local = max(2, min(int(settings.knowledge_agentic_report_max_sub_questions or 6), 8))
    system = (
        "你是研究报告材料检索规划助手。"
        "用户可能已允许使用本地知识库和/或联网检索，但**允许不等于必须**——请根据意图与上下文**智能判断**是否需要检索。\n"
        "判断参考：\n"
        "- format_adjust（格式/结构调整）：对话中已有报告正文时，通常**无需**检索；\n"
        "- follow_up（追问补充）：仅当需要**新的事实、数据或案例**时才检索；\n"
        "- initial（新报告）：通常需要检索，但若主题宽泛且无本地文档、模型知识已足够，可跳过。\n"
        "仅返回 JSON："
        '{"reasoning":"策略说明","use_local":true|false,"local_queries":["..."],'
        '"use_web":true|false,"web_queries":["..."]}。\n'
        f"约束：local_queries 0～{max_local} 条，web_queries 0～3 条；"
        "决定不检索时 use_local/use_web 为 false 且对应 queries 为空数组；"
        "use_local 仅当已选本地文档时可 true；use_web 仅当允许联网时可 true。"
    )
    user_parts = [
        f"报告主题：{topic or message[:80]}",
        f"用户输入：{message}",
        f"意图：{intent}",
        f"已选本地文档（允许本地检索）：{'是' if local_allowed else '否'}",
        f"允许联网：{'是' if web_allowed else '否'}",
    ]
    if history_excerpt.strip():
        user_parts.append(f"对话摘要：\n{history_excerpt[:1200]}")
    if kg_context.strip():
        user_parts.append("【本体图谱（规划参考）】\n" + kg_context[:1800])
    raw = chat_completion_sync(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        temperature=0.25,
        timeout=50.0,
    )
    data = parse_llm_json(raw)
    if not data:
        return _plan_report_gathering_fallback(
            message=message,
            topic=topic,
            intent=intent,
            local_allowed=local_allowed,
            web_allowed=web_allowed,
            history_excerpt=history_excerpt,
        )

    reasoning = str(data.get("reasoning") or "").strip() or "已规划报告材料检索"
    local_raw = data.get("local_queries") or data.get("sub_questions") or []
    web_raw = data.get("web_queries") or []
    use_local = bool(data.get("use_local", False)) and local_allowed
    use_web = bool(data.get("use_web", False)) and web_allowed
    if not isinstance(local_raw, list):
        local_raw = []
    if not isinstance(web_raw, list):
        web_raw = []
    local = (
        _unique_queries([str(x) for x in local_raw], limit=max_local) if use_local else []
    )
    web = _unique_queries([str(x) for x in web_raw], limit=3) if use_web else []
    return local, web, reasoning


def _evaluate_report_sufficiency(
    *,
    topic: str,
    message: str,
    local_count: int,
    web_count: int,
    snippet_preview: str,
    local_docs_available: bool = True,
    web_allowed: bool = True,
    intent: str = "initial",
    retrieval_attempted: bool = False,
    history_available: bool = False,
) -> tuple[bool, str | None, list[str], list[str]]:
    if local_count == 0 and web_count == 0:
        if not retrieval_attempted:
            return True, None, [], []
        if not local_docs_available and not web_allowed:
            return True, None, [], []
        if intent == "format_adjust" and history_available:
            return True, None, [], []
        seed = topic or message[:80]
        extra_local = [seed] if local_docs_available else []
        extra_web = [seed] if web_allowed else []
        return False, "未获取到本地或联网材料", extra_local, extra_web
    system = (
        "你是报告材料充足性评估助手。判断现有材料是否足以撰写该主题报告。"
        "仅返回 JSON："
        '{"sufficient":true|false,"gaps":"不足说明","extra_local":["..."],"extra_web":["..."]}。'
        "extra 各最多 2 条。"
    )
    user = (
        f"主题：{topic}\n用户要求：{message}\n"
        f"本地片段数：{local_count}；联网条数：{web_count}\n"
        f"材料摘要：\n{snippet_preview[:3000]}"
    )
    raw = chat_completion_sync(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        timeout=45.0,
    )
    data = parse_llm_json(raw)
    if not data:
        return (local_count + web_count) >= 3, None, [], []
    sufficient = bool(data.get("sufficient"))
    gaps = str(data.get("gaps") or "").strip() or None
    extra_l = data.get("extra_local") or []
    extra_w = data.get("extra_web") or []
    if not isinstance(extra_l, list):
        extra_l = []
    if not isinstance(extra_w, list):
        extra_w = []
    if sufficient:
        return True, None, [], []
    return (
        False,
        gaps,
        _unique_queries([str(x) for x in extra_l], limit=2),
        _unique_queries([str(x) for x in extra_w], limit=2),
    )


def _history_excerpt(history: list[AiChatMessage]) -> str:
    parts: list[str] = []
    for item in history[-4:]:
        role = "用户" if item.role == "user" else "助手"
        text = (item.content or "").strip()
        if not text:
            continue
        if len(text) > 400:
            text = text[:400] + "…"
        parts.append(f"{role}：{text}")
    return "\n".join(parts)


def iter_gather_for_report(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    *,
    message: str,
    topic: str,
    intent: str,
    history: list[AiChatMessage],
    web_enabled: bool,
    emit: WorkflowEmit | None = None,
) -> Iterator[dict[str, Any]]:
    """流式 yield workflow 事件；最后一项为 {RESULT_MARKER: AgenticReportGatherResult}。"""
    global _step_seq
    _step_seq = 0
    yield _workflow_event("workflow_started", title="Agent 开始收集报告材料")

    settings = get_settings()
    toolkit = KnowledgeAgenticToolkit(
        db,
        user,
        doc_ids,
        web_enabled=web_enabled,
        include_kg=True,
        retrieve_limit=15,
        web_max_items=10,
    )
    summaries: list[str] = []

    sid, ev = _tool_call_event("kg_context", "加载本体图谱上下文", f"{topic} {message}"[:80])
    _emit_wf(emit, ev)
    yield ev
    kg_tool = toolkit.kg_planning_context(f"{topic} {message}".strip())
    result_ev = _tool_result_event(
        "kg_context", "本体图谱上下文", kg_tool.summary, sid, ok=kg_tool.ok
    )
    _emit_wf(emit, result_ev)
    yield result_ev
    kg_plan_text = ""
    if kg_tool.data and getattr(kg_tool.data, "context_text", ""):
        kg_plan_text = kg_tool.data.context_text
        summaries.append(kg_tool.summary)

    sid, ev = _tool_call_event("version_metadata", "读取文档版本信息", topic[:80] or message[:80])
    _emit_wf(emit, ev)
    yield ev
    ver_tool = toolkit.version_metadata()
    ver_ev = _tool_result_event(
        "version_metadata", "版本元数据", ver_tool.summary, sid, ok=ver_tool.ok
    )
    _emit_wf(emit, ver_ev)
    yield ver_ev
    changelog_block = ""
    diff_block = ""
    if ver_tool.ok and ver_tool.data:
        changelog_block = ver_tool.data.get("changelog_block") or ""
        diff_block = ver_tool.data.get("diff_block") or ""
        summaries.append(ver_tool.summary)

    max_rounds = max(1, min(int(settings.knowledge_agentic_max_rounds or 2), 3))

    if not agentic_enabled():
        from app.services.report_generation_service import retrieve_local_hits_for_report

        hist = _history_excerpt(history)
        local_queries, web_queries, reasoning = _plan_report_gathering(
            message=message,
            topic=topic,
            intent=intent,
            document_count=len(doc_ids),
            web_allowed=web_enabled,
            kg_context="",
            history_excerpt=hist,
        )
        local_hits: list[dict] = []
        if doc_ids and local_queries:
            node = _workflow_event("node_started", title="深度检索本地资料")
            _emit_wf(emit, node)
            yield node
            for q in local_queries:
                sid, ev = _tool_call_event("retrieve", "知识库检索", q[:120])
                _emit_wf(emit, ev)
                yield ev
                tr = toolkit.retrieve(q, limit=15)
                summaries.append(tr.summary)
                tre = _tool_result_event(
                    "retrieve", "知识库检索", tr.summary, sid, ok=tr.ok
                )
                _emit_wf(emit, tre)
                yield tre
            local_hits = toolkit.accumulated_local_hits or retrieve_local_hits_for_report(
                db, user, doc_ids, local_queries
            )
        web_items: list[dict] = []
        if web_enabled and web_queries:
            web_node = _workflow_event("node_started", title="联网检索相关资料")
            _emit_wf(emit, web_node)
            yield web_node
            for q in web_queries:
                sid, ev = _tool_call_event("web_search", "联网检索", q[:120])
                _emit_wf(emit, ev)
                yield ev
                tr = toolkit.web_search(q)
                summaries.append(tr.summary)
                tre = _tool_result_event(
                    "web_search", "联网检索", tr.summary, sid, ok=tr.ok
                )
                _emit_wf(emit, tre)
                yield tre
            web_items = toolkit.accumulated_web_items
        elif not local_queries and not web_queries:
            skip_ev = _workflow_event(
                "agent_thought",
                title="无需额外检索",
                detail=reasoning[:500],
                tool="planner",
                status="done",
            )
            _emit_wf(emit, skip_ev)
            yield skip_ev
        yield {
            RESULT_MARKER: AgenticReportGatherResult(
                local_hits=local_hits,
                web_items=web_items,
                doc_titles=toolkit.doc_titles(),
                plan_reasoning=reasoning,
                rounds_used=1,
                local_queries=local_queries,
                web_queries=web_queries,
                tool_summaries=summaries,
                version_changelog_block=changelog_block,
                version_diff_block=diff_block,
            )
        }
        return

    think_id = _next_step_id()
    think_ev = _workflow_event(
        "agent_thinking",
        title="规划报告材料检索",
        detail="拆解本地与联网检索策略…",
        tool="planner",
        step_id=think_id,
    )
    _emit_wf(emit, think_ev)
    yield think_ev
    local_queries, web_queries, reasoning = _plan_report_gathering(
        message=message,
        topic=topic,
        intent=intent,
        document_count=len(doc_ids),
        web_allowed=web_enabled,
        kg_context=kg_plan_text,
        history_excerpt=_history_excerpt(history),
    )
    plan_detail_parts = [reasoning[:500]] if reasoning else []
    query_bits: list[str] = []
    if local_queries:
        query_bits.append("本地：" + "；".join(str(q) for q in local_queries[:3]))
    if web_queries:
        query_bits.append("联网：" + "；".join(str(q) for q in web_queries[:3]))
    if query_bits:
        plan_detail_parts.append("\n".join(query_bits))
    thought_ev = _workflow_event(
        "agent_thought",
        title="规划完成",
        detail="\n".join(plan_detail_parts)[:800],
        tool="planner",
        step_id=think_id,
        status="done",
    )
    _emit_wf(emit, thought_ev)
    yield thought_ev

    retrieval_planned = bool(
        (doc_ids and local_queries) or (web_enabled and web_queries)
    )
    insufficient_note: str | None = None
    rounds = 0
    extra_local: list[str] = []
    extra_web: list[str] = []

    if not retrieval_planned:
        skip_ev = _workflow_event(
            "agent_thought",
            title="无需额外检索",
            detail="智能体判断本次可依据对话历史与模型知识撰写",
            tool="planner",
            status="done",
        )
        _emit_wf(emit, skip_ev)
        yield skip_ev
    else:
        for round_idx in range(1, max_rounds + 1):
            rounds = round_idx
            loc_q = local_queries if round_idx == 1 else extra_local
            web_q = web_queries if round_idx == 1 else extra_web

            if round_idx > 1 and not loc_q and not web_q:
                break

            if doc_ids and loc_q:
                for q in loc_q:
                    sid, ev = _tool_call_event(
                        "retrieve",
                        f"第 {round_idx} 轮 · 知识库检索",
                        q[:120],
                    )
                    _emit_wf(emit, ev)
                    yield ev
                    tr = toolkit.retrieve(q, limit=15)
                    summaries.append(tr.summary)
                    tre = _tool_result_event(
                        "retrieve", "知识库检索", tr.summary, sid, ok=tr.ok
                    )
                    _emit_wf(emit, tre)
                    yield tre
            if web_enabled and web_q:
                for q in web_q:
                    sid, ev = _tool_call_event(
                        "web_search",
                        f"第 {round_idx} 轮 · 联网检索",
                        q[:120],
                    )
                    _emit_wf(emit, ev)
                    yield ev
                    tr = toolkit.web_search(q)
                    summaries.append(tr.summary)
                    tre = _tool_result_event(
                        "web_search", "联网检索", tr.summary, sid, ok=tr.ok
                    )
                    _emit_wf(emit, tre)
                    yield tre

            local_hits = toolkit.accumulated_local_hits
            web_items = toolkit.accumulated_web_items
            preview_parts = [_hits_snippet_preview(local_hits)]
            for i, w in enumerate(web_items[:5], start=1):
                preview_parts.append(f"[W{i}] {(w.get('snippet') or '')[:200]}")
            eval_id = _next_step_id()
            eval_think = _workflow_event(
                "agent_thinking",
                title="评估报告材料是否充足",
                detail=f"本地 {len(local_hits)} 段 · 联网 {len(web_items)} 条",
                tool="evaluator",
                step_id=eval_id,
            )
            _emit_wf(emit, eval_think)
            yield eval_think
            sufficient, gaps, extra_local, extra_web = _evaluate_report_sufficiency(
                topic=topic,
                message=message,
                local_count=len(local_hits),
                web_count=len(web_items),
                snippet_preview="\n".join(preview_parts),
                local_docs_available=bool(doc_ids),
                web_allowed=web_enabled,
                intent=intent,
                retrieval_attempted=bool(loc_q or web_q),
                history_available=bool(_history_excerpt(history).strip()),
            )
            eval_lines = [
                "材料充足，可以撰写报告" if sufficient else (gaps or "仍需补充检索")
            ]
            if not sufficient and (extra_local or extra_web):
                extras = extra_local[:2] + extra_web[:2]
                eval_lines.append("建议补充检索：" + "；".join(str(q) for q in extras))
            eval_done = _workflow_event(
                "agent_thought",
                title="评估完成",
                detail="\n".join(eval_lines)[:600],
                tool="evaluator",
                step_id=eval_id,
                status="done",
            )
            _emit_wf(emit, eval_done)
            yield eval_done

            if sufficient or round_idx >= max_rounds:
                if not sufficient and gaps:
                    insufficient_note = gaps
                break
            if extra_local or extra_web:
                local_queries = extra_local
                web_queries = extra_web
                sup = _workflow_event(
                    "node_started",
                    title="材料不足，规划补充检索",
                    detail="；".join((extra_local + extra_web)[:2]),
                )
                _emit_wf(emit, sup)
                yield sup
            else:
                insufficient_note = gaps
                break

    yield {
        RESULT_MARKER: AgenticReportGatherResult(
            local_hits=toolkit.accumulated_local_hits,
            web_items=toolkit.accumulated_web_items,
            doc_titles=toolkit.doc_titles(),
            plan_reasoning=reasoning,
            rounds_used=rounds,
            local_queries=local_queries,
            web_queries=web_queries,
            insufficient_note=insufficient_note,
            tool_summaries=summaries,
            version_changelog_block=changelog_block,
            version_diff_block=diff_block,
        )
    }


def gather_for_report(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    *,
    message: str,
    topic: str,
    intent: str,
    history: list[AiChatMessage],
    web_enabled: bool,
    emit: WorkflowEmit | None = None,
) -> AgenticReportGatherResult:
    result: AgenticReportGatherResult | None = None
    for item in iter_gather_for_report(
        db,
        user,
        doc_ids,
        message=message,
        topic=topic,
        intent=intent,
        history=history,
        web_enabled=web_enabled,
        emit=emit,
    ):
        if RESULT_MARKER in item:
            result = item[RESULT_MARKER]
    assert result is not None
    return result
