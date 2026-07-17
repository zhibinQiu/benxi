"""独立上下文 Subagent — agentkit-subagent 平台适配。"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from app.core.agent_loop_state import LoopState

from app.agentkit.subagent import (
    ExploreSkillStep,
    SubagentConfig,
    SubagentKindConfig,
    SubagentRuntime,
    execute_subagent,
)
from app.agentkit.subagent.loop import parse_tool_summary
from sqlalchemy.orm import Session

from app.core.agent_tool_context import append_retrieval_context, record_executed_tool_call
from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.models.org import User
from app.services.agent_tools import build_agent_tool_specs, execute_agent_tool

_PLATFORM_RUNTIME = SubagentRuntime(
    kinds={
        "use": SubagentKindConfig(
            kind="use",
            allowed_tools=frozenset({"invoke_skill"}),
            max_rounds=5,
            system_contract=(
                "你是技能执行子 Agent。你的职责是：\n"
                "1. 分析用户任务，确定需要调用哪个技能（invoke_skill）。\n"
                "2. 调用 invoke_skill(skill_name, action, params) 执行技能。\n"
                "3. 根据技能返回结果整理回答。\n"
                "注意：一次只调用必要的技能，不要做多余操作。"
            ),
        ),
        "search": SubagentKindConfig(
            kind="search",
            allowed_tools=frozenset({"invoke_skill", "web_search", "knowledge_retrieve", "run_tool_batch"}),
            max_rounds=12,
            system_contract=(
                "你是多源检索子 Agent。你可以调用以下工具获取信息：\n"
                "- web_search：联网检索公开信息\n"
                "- knowledge_retrieve：检索内部知识库\n"
                "- invoke_skill(skill_name, action, params) 调用搜索类技能\n"
                "- run_tool_batch：并行执行多个工具（如多个 web_search 关键词）\n\n"
                "## 简单查询（价格、日期、定义、新闻等事实性问题）\n"
                "1. 直接生成 1-2 个精准搜索词调用 web_search。\n"
                "2. 搜索结果足够回答时直接回复，无需多轮。\n"
                "3. 无需输出结构化的研究报告，简洁回答即可。\n\n"
                "## 复杂研究（需要多角度、多来源综合分析）—— 优先并行\n"
                "1. **分析问题**：理解核心问题，拆解出需要调研的子主题。\n"
                "2. **一次生成全部搜索词**：根据子主题一次性生成 3-5 个精准搜索词，"
                "先宽泛概述性关键词了解全貌，再具体数据关键词深挖细节。\n"
                "3. **并行检索**：使用 run_tool_batch 一次性并行执行所有搜索词"
                "（web_search, read_full=3~5），大幅减少等待时间。\n"
                "4. **多维验证**：不同来源存在矛盾数据时，追加搜索做交叉验证。"
                "也可调用 knowledge_retrieve 检索内部知识库辅助核对。\n"
                "5. **发现归纳**：对已获取的全文内容进行跨源比对，提炼一致结论，标注矛盾点。\n"
                "返回包含 research_summary、key_findings、data_comparison、conflicts、citations 的结构化研究报告。\n\n"
                "## 约束\n"
                "- 禁止凭空编造数据，所有量化结论必须来自搜索结果的全文。\n"
                "- 如果首次 run_tool_batch 结果不足以作答，继续生成新的关键词深挖。\n"
                "- 搜索结果足够回答时，立即回复，不要进行不必要的多轮搜索。\n"
                "- 回复使用中文，技术术语保留英文。"
            ),
        ),
        "auto": SubagentKindConfig(
            kind="auto",
            allowed_tools=None,  # 继承父智能体的完整工具集
            max_rounds=12,
            system_contract=(
                "你是自主编排子 Agent。你继承了父智能体的全部工具，"
                "可以自主决定使用哪些工具完成用户任务。\n\n"
                "你的工作方式：\n"
                "1. **分析任务**：理解用户需求，制定完成策略。\n"
                "2. **自主编排**：根据需要调用任意可用工具，自主决定调用顺序和参数。\n"
                "3. **灵活应变**：工具返回结果后，根据实际情况调整后续步骤。\n"
                "4. **完成任务**：持续执行直至任务完成，然后整理结果回复用户。\n\n"
                "约束：\n"
                "- 不调用不存在的工具。\n"
                "- 如果任务需要你还未掌握的信息，先用检索工具获取。\n"
                "- 每次调用工具前思考是否需要该工具。\n"
                "- 回复使用中文，技术术语保留英文。"
            ),
        ),
    },
    explore_steps=(
        ExploreSkillStep("web-search", "search", "query"),
        ExploreSkillStep("knowledge-search", "retrieve", "query"),
        ExploreSkillStep("kg", "query_entities", "question"),
    ),
)


# ── 子智能体进度事件推送（实时显示搜索进度） ─────────────────────

# 获取任一 loop_state 上的 progress_queue（支持多层嵌套）
def _resolve_progress_queue(state: LoopState | None) -> asyncio.Queue | None:
    """从 loop_state 解析 progress_queue：优先主队列，回退父队列引用。"""
    if state is None:
        return None
    q: asyncio.Queue | None = state.get("_progress_queue")
    if q is not None:
        return q
    q = state.get("_parent_progress_queue")
    return q


def _push_event(
    state: LoopState | None,
    phase: str,
    title: str,
    detail: str = "",
    *,
    tool: str = "",
    tool_name: str = "",
    step_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """通用进度事件推送。"""
    q = _resolve_progress_queue(state)
    if q is None:
        return
    ev: dict[str, Any] = {
        "phase": phase,
        "title": title[:120],
        "detail": detail[:240],
        "tool": tool or tool_name,
        "tool_name": tool_name,
        "step_id": step_id or f"evt-{uuid.uuid4().hex[:8]}",
    }
    if extra:
        ev.update(extra)
    q.put_nowait(ev)


def _push_tool_start(
    state: LoopState | None,
    tool_name: str,
    raw_args: Any,
) -> None:
    """推送工具调用 START 事件。"""
    from app.services.agent_tools import tool_workflow_meta

    meta = tool_workflow_meta(tool_name, raw_args)
    args_preview = _args_to_preview(raw_args)
    _push_event(
        state,
        phase="tool_call",
        title=f"正在{meta.get('title', tool_name)}",
        detail=args_preview,
        tool=meta.get("tool") or tool_name,
        tool_name=tool_name,
        extra={"callDetail": args_preview, "status": "running"},
    )


def _push_tool_result(
    state: LoopState | None,
    tool_name: str,
    raw_args: Any,
    result: str,
) -> None:
    """推送工具调用 RESULT 事件。"""
    from app.services.agent_tools import tool_workflow_meta

    try:
        body = json.loads(result)
        ok = bool(body.get("ok"))
        summary = str(body.get("summary") or "")[:240]
    except (json.JSONDecodeError, TypeError):
        ok = False
        summary = str(result)[:240]
    meta = tool_workflow_meta(tool_name, raw_args)
    _push_event(
        state,
        phase="tool_result",
        title=meta.get("result_title") or (f"{tool_name} 完成" if ok else f"{tool_name} 失败"),
        detail=summary or ("完成" if ok else "失败"),
        tool="web.search" if tool_name == "web_search" else (meta.get("tool") or tool_name),
        tool_name=tool_name,
        extra={"resultDetail": summary[:400], "status": "done" if ok else "failed"},
    )


def _push_llm_thinking(state: LoopState | None) -> None:
    """推送 LLM 思考中事件。"""
    _push_event(state, phase="llm_thinking", title="智能体思考中...", tool="llm.thinking")


def _push_llm_decided(state: LoopState | None, tool_names: list[str] | None, content: str) -> None:
    """推送 LLM 决策事件。"""
    if tool_names:
        names = "、".join(tool_names[:3])
        _push_event(
            state,
            phase="llm_decision",
            title=f"决定调用工具：{names}",
            detail=f"将依次调用 {len(tool_names)} 个工具",
            tool="llm.decision",
        )
    elif content:
        text = _strip_text(content, 80)
        _push_event(
            state,
            phase="llm_decision",
            title="生成回复片段",
            detail=text,
            tool="llm.decision",
        )


def _args_to_preview(raw_args: Any) -> str:
    """将工具参数转为短预览字符串。"""
    if isinstance(raw_args, dict):
        parts = []
        for k, v in raw_args.items():
            vs = str(v)[:120]
            parts.append(f"{k}={vs}")
        return ", ".join(parts)[:200]
    if isinstance(raw_args, str):
        return raw_args[:200]
    return str(raw_args or "")[:200]


def _strip_text(text: str, max_len: int = 80) -> str:
    return text.strip().replace("\n", " ")[:max_len]


async def execute_context_subagent(
    db: Session,
    user: User,
    *,
    kind: str,
    task: str = "",
    queries: list[str] | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    loop_state: LoopState | None = None,
) -> str:
    loop_holder: dict[str, Any] = {"state": None}

    async def invoke_skill_step(
        child_state: dict[str, Any],
        skill_name: str,
        action: str,
        param_key: str,
        query: str,
    ) -> str:
        _push_event(
            loop_state, phase="tool_call",
            title=f"正在检索：{query[:60]}",
            detail=f"skill={skill_name} action={action}",
            tool="knowledge.retrieve",
            tool_name="invoke_skill",
        )
        raw = await execute_agent_tool(
            db,
            user,
            tool_name="invoke_skill",
            arguments={
                "skill_name": skill_name,
                "action": action,
                "params": {param_key: query},
            },
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            user_message=query,
            loop_state=child_state,
        )
        ok, summary = parse_tool_summary(raw)
        record_executed_tool_call(
            child_state,
            tool_name="invoke_skill",
            raw_args={"skill_name": skill_name, "action": action, "params": {param_key: query}},
            result_text=raw,
            summary=summary,
            step_id=f"explore-{skill_name}-{uuid.uuid4().hex[:6]}",
        )
        if ok:
            _push_event(
                loop_state, phase="tool_result",
                title=f"检索完成：{query[:60]}",
                detail=summary[:120] or "完成",
                tool="knowledge.retrieve",
                tool_name="invoke_skill",
            )
        return summary if ok else ""

    async def llm_complete(messages, tool_specs):
        _push_llm_thinking(loop_state)
        choice = await chat_completion_message_async(
            messages=messages,
            tools=tool_specs or None,
            temperature=0.2,
        )
        if choice:
            msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
            tcs = msg.get("tool_calls") or []
            tool_names = []
            if tcs:
                for tc in tcs if isinstance(tcs, list) else []:
                    fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                    n = str(fn.get("name") or "")
                    if n:
                        tool_names.append(n)
            content = str(msg.get("content") or "")
            _push_llm_decided(loop_state, tool_names, content)
        return choice

    def build_tool_specs(allowed: set[str] | None):
        return build_agent_tool_specs(db, user, allowed_names=allowed)

    async def execute_tool(tool_name: str, raw_args: Any) -> str:
        state = loop_holder["state"]
        assert state is not None
        result = await execute_agent_tool(
            db,
            user,
            tool_name=tool_name,
            arguments=raw_args,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            user_message=task,
            loop_state=state,
        )
        _push_tool_result(loop_state, tool_name, raw_args, result)
        return result

    def record_tool(
        state: dict[str, Any],
        tool_name: str,
        raw_args: Any,
        result_text: str,
        summary: str,
        step_id: str,
    ) -> None:
        record_executed_tool_call(
            state,
            tool_name=tool_name,
            raw_args=raw_args,
            result_text=result_text,
            summary=summary,
            step_id=step_id,
        )

    from app.agentkit.subagent.context import child_state_from_parent

    agent = str((loop_state or {}).get("agent_id") or "")
    sub_kind = (kind or "").strip().lower()
    task_text = (task or "").strip()

    def init_child_state() -> dict[str, Any]:
        state = child_state_from_parent(loop_state, kind=sub_kind, agent_id=agent)
        # 传递父 loop_state 的 progress_queue 引用，供 run_tool_batch 等深层使用
        if loop_state and "_progress_queue" in loop_state:
            state["_parent_progress_queue"] = loop_state["_progress_queue"]
        loop_holder["state"] = state
        return state

    async def execute_tool_bound(tool_name: str, raw_args: Any) -> str:
        if loop_holder["state"] is None:
            init_child_state()
        _push_tool_start(loop_state, tool_name, raw_args)
        result = await execute_tool(tool_name, raw_args)
        # RESULT 事件在 execute_agent_tool 中统一推送
        return result

    def record_tool_bound(
        state: dict[str, Any],
        tool_name: str,
        raw_args: Any,
        result_text: str,
        summary: str,
        step_id: str,
    ) -> None:
        loop_holder["state"] = state
        record_tool(state, tool_name, raw_args, result_text, summary, step_id)

    result = await execute_subagent(
        config=SubagentConfig.full(
            runtime=_PLATFORM_RUNTIME,
            llm_complete=llm_complete,
            execute_tool=execute_tool_bound,
            record_tool=record_tool_bound,
            build_tool_specs=build_tool_specs,
            invoke_skill=invoke_skill_step,
            append_retrieval=append_retrieval_context,
        ),
        kind=sub_kind,
        task=task_text,
        queries=queries,
        user_message=user_message,
        loop_state=loop_state,
        agent_id=agent,
        llm_configured=is_configured(),
    )

    # 将子智能体的工具调用步骤（搜索词等）保存到父 loop_state，并提取搜索词
    sub_queries: list[str] = []
    if loop_state is not None:
        child_state = loop_holder.get("state")
        if child_state:
            sub_steps = list(child_state.get("executed_tool_calls") or [])
            if sub_steps:
                seen = set()
                deduped = []
                for s in sub_steps:
                    fp = s.get("fingerprint") or s.get("step_id") or ""
                    if fp not in seen:
                        seen.add(fp)
                        deduped.append(s)
                loop_state["subagent_executed_steps"] = deduped[-20:]
                # 提取 web_search 搜索词
                for s in deduped:
                    tn = (s.get("tool_name") or "").strip()
                    ap = (s.get("args_preview") or "")
                    if tn == "web_search":
                        q = ap[:80]
                        if q and q not in sub_queries:
                            sub_queries.append(q)

    # 统一构造结构化返回：提取 URL → 拼接摘要 → 返回 JSON
    ok = bool(result and result.strip())
    url_info = ""
    raw_text = (result or "").strip()
    if raw_text:
        urls = re.findall(r"https?://[^\s\)\]\>\"\'，。、；：！？）】」』》《]+", raw_text)
        unique_urls: list[str] = []
        if urls:
            seen = set()
            for u in urls:
                u_clean = re.sub(r"[，。、；：！？）】」』》《]+$", "", u)
                if u_clean and u_clean not in seen:
                    seen.add(u_clean)
                    unique_urls.append(u_clean)
        if unique_urls:
            shown = unique_urls[:8]
            url_parts = []
            for u in shown:
                short = u.rstrip("/").rsplit("/", 1)[-1][:40] if "/" in u else u[:40]
                url_parts.append(short)
            url_info = f"，读取了 {len(unique_urls)} 个网页（{'、'.join(url_parts)}）"

    query_info = f"。搜索词：{'、'.join(sub_queries[:5])}" if sub_queries else ""
    summary = f"子智能体（{kind}）已完成{query_info}{url_info}"
    truncated = raw_text[:4000] if len(raw_text) > 4000 else raw_text

    return json.dumps(
        {"ok": ok, "summary": summary[:300], "data": {"result": truncated}},
        ensure_ascii=False,
    )
