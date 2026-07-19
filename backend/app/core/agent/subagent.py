"""独立上下文 Subagent — agentkit-subagent 平台适配。"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from app.core.agent_loop_state import LoopState

from app.agentkit.subagent import (
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
from app.core.agent_tool_args import ALL_TOOLS
from app.core.tool_skill_taxonomy import PARENT_HIDDEN_EXECUTION_ENTRYPOINTS
from app.services.agent_tools import build_agent_tool_specs, execute_agent_tool

_PLATFORM_RUNTIME = SubagentRuntime(
    kinds={
        "use": SubagentKindConfig(
            kind="use",
            allowed_tools=None,  # use 子层：可含 invoke_skill / run_skill_script
            max_rounds=8,
            system_contract=(
                "你是技能执行子 Agent，负责按父智能体指定的技能完成用户任务。\n\n"
                "工作方式：\n"
                "1. 若任务/上下文附带了 SKILL.md，严格按其角色与流程执行。\n"
                "2. 脚本型技能用 run_skill_script；平台绑定技能用 invoke_skill。\n"
                "3. 技能步骤需要检索时，直接调用 web_search / knowledge_retrieve 等原子工具。\n"
                "4. 拿到足够材料后，输出面向用户的完整中文回答（可含要点与来源）。\n\n"
                "约束：禁止空口承诺；禁止编造数据；不要只复述工具状态。"
            ),
        ),
        "search": SubagentKindConfig(
            kind="search",
            allowed_tools=frozenset({"invoke_skill", "web_search", "fetch_url_content", "knowledge_retrieve", "kg_query", "ontology_query", "run_tool_batch"}),
            max_rounds=12,
            system_contract=(
                "你是多源检索子 Agent。你的目标是快速获取真实信息直接回答用户问题。\n\n"
                "你可以调用以下工具：\n"
                "- web_search：联网检索。read_full=0 仅返回摘要片段（秒级返回），\n"
                "  read_full=3（默认）自动读前 3 条全文\n"
                "- fetch_url_content(url)：对特定 URL 获取网页正文（有疑惑时再用）\n"
                "- knowledge_retrieve：检索内部知识库\n"
                "- kg_query：查询知识图谱（结构化实体关系）\n"
                "- ontology_query：查询本体模型\n"
                "- invoke_skill(skill_name, action, params)：调用搜索类技能\n"
                "- run_tool_batch：一批并行执行多个 web_search\n\n"
                "## 工作原则\n"
                "1. **先看概要再决定是否读全文**：先调用 web_search(read_full=0) 获取摘要片段，\n"
                "   如果摘要已能回答问题无需读全文；如需深挖则对具体 URL 调 fetch_url_content。\n"
                "2. **一次搜够**：拆解问题后 2-4 个搜索词一次性用 run_tool_batch 并行发出。\n"
                "3. **快速判断**：搜索超时/无法解析的网站直接忽略，不要重试。\n"
                "4. **直接回答**：获取到足够信息后立即回答，不要等全部 URL 读完。\n"
                "5. **实事求是**：所有结论必须有搜索结果支撑，禁止编造数据。\n"
                "6. **引源注明**：关键事实附上来源链接。\n\n"
                "## 约束\n"
                "- 禁止编造数据，所有量化结论必须来自搜索结果。\n"
                "- 最多 12 轮交互，省着用。\n"
                "- 结果足以回答时立即回复，不要多轮搜索。\n"
                "- 回复使用中文，技术术语保留英文。"
            ),
        ),
        "execute": SubagentKindConfig(
            kind="execute",
            # 运行时由 build_tool_specs 按父挂载集 ∩ steps 收窄；此处 None 表示不预置超集
            allowed_tools=None,
            max_rounds=8,
            system_contract=(
                "你是工具执行子 Agent。按父智能体任务调用真实工具并返回结果。\n\n"
                "工作方式：\n"
                "1. 若任务已给出明确工具名与参数，按指定调用，不得擅自替换。\n"
                "2. 浏览器任务优先 browser_run_task(task, start_url?) 一次完成；"
                "或分步 browser_navigate → browser_type/click → browser_screenshot。\n"
                "3. 需要多步时按依赖顺序调用，拿到真实结果后再结束。\n"
                "4. 工具失败时原样返回错误，禁止编造成功结果。\n\n"
                "约束：禁止空口描述「已截图」；截图必须调用 browser_screenshot 或 browser_run_task。"
            ),
        ),
    },
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


def _human_tool_call_detail(tool_name: str, raw_args: Any) -> str:
    """将工具调用参数转为人类可读的描述，如"搜索关键词：欧盟碳价"。"""
    args = _parse_tool_args_safe(raw_args)
    if not args:
        return ""
    tn = (tool_name or "").strip()

    if tn == "web_search":
        q = str(args.get("query") or "").strip()
        return f"搜索关键词：{q[:120]}" if q else "联网搜索"
    if tn == "fetch_url_content":
        url = str(args.get("url") or "").strip()
        short = url.rstrip("/").rsplit("/", 1)[-1][:60] if "/" in url else url[:60]
        return f"读取网页：{short or url[:80]}" if url else "获取网页内容"
    if tn == "knowledge_retrieve":
        q = str(args.get("query") or "").strip()
        return f"知识库检索：{q[:120]}" if q else "知识库检索"
    if tn == "kg_query":
        q = str(args.get("question") or args.get("query") or "").strip()
        return f"知识图谱查询：{q[:120]}" if q else "知识图谱查询"
    if tn == "knowledge_folder_search":
        q = str(args.get("query") or "").strip()
        return f"文件夹检索：{q[:120]}" if q else "文件夹检索"
    if tn in ("browser_navigate",):
        url = str(args.get("url") or "").strip()
        short = url.rstrip("/").rsplit("/", 1)[-1][:60] if "/" in url else url[:60]
        return f"导航到：{short or url[:80]}" if url else "打开网页"
    if tn == "browser_snapshot":
        return "读取当前页面结构"
    if tn == "browser_screenshot":
        return "截图当前页面"
    if tn == "browser_run_task":
        task = str(args.get("task") or "").strip()
        return f"自动探索：{task[:120]}" if task else "自动探索网页"
    if tn in ("run_tool_batch",):
        steps = args.get("steps") or []
        count = len(steps) if isinstance(steps, list) else 0
        return f"并行执行 {count} 个检索任务"
    if tn in ("invoke_skill",):
        skill = str(args.get("skill_name") or "").strip()
        action = str(args.get("action") or "").strip()
        if skill and action:
            return f"调用技能 {skill} → {action}"
        return f"调用技能：{skill or '?'}"
    for key in ("query", "question", "task", "url", "name", "keyword"):
        val = str(args.get(key) or "").strip()
        if val:
            return f"{val[:160]}"
    return ""


def _parse_tool_args_safe(raw: Any) -> dict[str, Any]:
    """安全解析工具参数（str JSON / dict）。"""
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _push_tool_start(
    state: LoopState | None,
    tool_name: str,
    raw_args: Any,
) -> None:
    """推送工具调用 START 事件。"""
    from app.services.agent_tools import tool_workflow_meta

    meta = tool_workflow_meta(tool_name, raw_args)
    call_detail = _human_tool_call_detail(tool_name, raw_args)
    _push_event(
        state,
        phase="tool_call",
        title=f"正在{meta.get('title', tool_name)}",
        detail=call_detail,
        tool=meta.get("tool") or tool_name,
        tool_name=tool_name,
        extra={"callDetail": call_detail, "status": "running"},
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
        title=meta.get("result_title") or f"{tool_name}",
        detail=summary or "",
        tool="web.search" if tool_name == "web_search" else (meta.get("tool") or tool_name),
        tool_name=tool_name,
        extra={"resultDetail": summary[:400], "status": "done" if ok else "failed"},
    )


def _push_llm_thinking(state: LoopState | None) -> None:
    """推送 LLM 思考中事件（带变化文案，避免前端长时间停在同一句）。"""
    hints = (
        "梳理任务要点…",
        "对照已有结果…",
        "决定下一步动作…",
        "组织回答结构…",
    )
    idx = int(state.get("_llm_think_tick") or 0) if state is not None else 0
    if state is not None:
        state["_llm_think_tick"] = idx + 1
    _push_event(
        state,
        phase="llm_thinking",
        title=hints[idx % len(hints)],
        detail=hints[idx % len(hints)],
        tool="llm.thinking",
    )


def _push_llm_decided(state: LoopState | None, tool_names: list[str] | None, content: str) -> None:
    """推送 LLM 决策事件。"""
    if tool_names:
        names = "、".join(tool_names[:3])
        _push_event(
            state,
            phase="llm_decision",
            title=f"决定调用：{names}",
            detail=f"即将执行 {len(tool_names)} 个工具",
            tool="llm.decision",
        )
    elif content:
        text = _strip_text(content, 100)
        _push_event(
            state,
            phase="llm_decision",
            title=text or "生成回复",
            detail=text,
            tool="llm.decision",
        )



def _strip_text(text: str, max_len: int = 80) -> str:
    return text.strip().replace("\n", " ")[:max_len]


async def execute_context_subagent(
    db: Session,
    user: User,
    *,
    kind: str,
    task: str = "",
    queries: list[str] | None = None,
    steps: list[dict[str, Any]] | None = None,
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

    from app.agentkit.subagent.context import child_state_from_parent

    agent = str((loop_state or {}).get("agent_id") or "")
    sub_kind = (kind or "").strip().lower()
    task_text = (task or "").strip()

    def _execute_parent_tool_pool() -> set[str] | None:
        """execute 子层可用工具 = 父挂载集 − 技能直执入口。

        优先父 loop_state._all_tool_specs；否则按 agent_id 解析挂载表。
        返回 None 表示无法解析（调用方勿当成「全库放行」）。
        """
        names: set[str] = set()
        for spec in list((loop_state or {}).get("_all_tool_specs") or []):
            n = str((spec.get("function") or {}).get("name") or "").strip()
            if n:
                names.add(n)
        if not names:
            aid = (agent or "").strip() or "orchestrator"
            try:
                from app.services.agent_profile_service import (
                    resolve_effective_runtime_tool_names,
                )

                names = {
                    str(n).strip()
                    for n in resolve_effective_runtime_tool_names(db, aid)
                    if str(n).strip()
                }
            except Exception:
                names = set()
        if not names:
            return None
        return names - PARENT_HIDDEN_EXECUTION_ENTRYPOINTS

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
        aid = (agent or "").strip() or None
        if sub_kind == "execute":
            # 无 agent_id 时按 orchestrator 挂载表收窄，禁止回落平台全库
            exec_aid = aid or "orchestrator"
            parent_pool = _execute_parent_tool_pool()
            if allowed is not None and parent_pool is not None:
                effective: set[str] | None = allowed & parent_pool
            elif allowed is not None:
                effective = allowed - PARENT_HIDDEN_EXECUTION_ENTRYPOINTS
            else:
                effective = parent_pool
            return build_agent_tool_specs(
                db, user, allowed_names=effective, agent_id=exec_aid
            )
        return build_agent_tool_specs(
            db, user, allowed_names=allowed, agent_id=aid
        )

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

    # use：父层已匹配的上传技能 → 把 SKILL.md 注入子任务，由子智能体执行
    if sub_kind == "use" and loop_state is not None:
        skill = str(loop_state.get("planned_uploaded_skill") or "").strip()
        if skill and skill.lower() not in task_text.lower():
            task_text = f"使用技能 {skill} 完成：{task_text}" if task_text else f"使用技能 {skill}"
        if skill:
            from app.services.agent_tools import (
                build_skill_md_context_block,
                fetch_uploaded_skill_md,
            )
            from app.services.agent_skill_service import uploaded_skill_has_script

            skill_md = fetch_uploaded_skill_md(db, skill, user=user) or ""
            try:
                has_script = uploaded_skill_has_script(db, skill)
            except Exception:
                has_script = None
            block = build_skill_md_context_block(skill, skill_md, has_script=has_script)
            if block:
                task_text = f"{block}\n\n【用户任务】\n{task_text}"

    def init_child_state() -> dict[str, Any]:
        state = child_state_from_parent(loop_state, kind=sub_kind, agent_id=agent)
        # 传递父 loop_state 的 progress_queue 引用，供 run_tool_batch 等深层使用
        if loop_state and "_progress_queue" in loop_state:
            state["_parent_progress_queue"] = loop_state["_progress_queue"]
        if loop_state and loop_state.get("planned_uploaded_skill"):
            state["planned_uploaded_skill"] = loop_state["planned_uploaded_skill"]
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

    # ── execute 模式 + steps → 直接执行，不经过 LLM ────────────
    if sub_kind == "execute" and steps:
        execute_pool = _execute_parent_tool_pool()
        raw_results: list[dict[str, Any]] = []
        plan_lines: list[str] = []
        for step in steps:
            tn = str(step.get("tool") or "").strip()
            sa = _parse_tool_args_safe(step.get("arguments") or {})
            cd = _human_tool_call_detail(tn, sa)
            plan_lines.append(f"  {len(plan_lines) + 1}. {cd or tn}")
        _push_event(
            loop_state, phase="agent_plan",
            title=f"编排计划（{len(steps)} 步）",
            detail="\n".join(plan_lines),
            tool="agent.planner",
        )
        init_child_state()
        for step in steps:
            tool_name = str(step.get("tool") or "").strip()
            raw_args = step.get("arguments") or {}
            step_id = f"execute-step-{uuid.uuid4().hex[:8]}"
            _push_tool_start(loop_state, tool_name, raw_args)
            if not tool_name:
                result_text = json.dumps(
                    {"ok": False, "summary": "步骤缺少 tool 名"},
                    ensure_ascii=False,
                )
            elif tool_name in PARENT_HIDDEN_EXECUTION_ENTRYPOINTS:
                result_text = json.dumps(
                    {
                        "ok": False,
                        "summary": (
                            f"工具 `{tool_name}` 为技能直执入口，"
                            "execute 子层不可调用；请改用 kind=use"
                        ),
                    },
                    ensure_ascii=False,
                )
            elif execute_pool is not None and tool_name not in execute_pool:
                result_text = json.dumps(
                    {
                        "ok": False,
                        "summary": (
                            f"工具 `{tool_name}` 未挂载到当前智能体，"
                            "execute 子层拒绝执行"
                        ),
                    },
                    ensure_ascii=False,
                )
            else:
                try:
                    result_text = await execute_tool(tool_name, raw_args)
                except Exception as exc:
                    result_text = json.dumps(
                        {"ok": False, "summary": f"执行异常：{exc}"},
                        ensure_ascii=False,
                    )
            ok, summary = parse_tool_summary(result_text)
            record_tool_bound(loop_holder["state"], tool_name, raw_args, result_text,
                              summary or ("完成" if ok else "失败"), step_id)
            raw_results.append({
                "tool": tool_name,
                "tool_call_id": str(step.get("tool_call_id") or ""),
                "ok": ok, "summary": summary or "",
                "raw": result_text,
            })
        if loop_state is not None:
            cs = loop_holder.get("state")
            if cs:
                # 必须把检索正文/引用合并回父状态，否则终稿只能看到工具状态摘要
                from app.agentkit.subagent.context import merge_child_into_parent

                merge_child_into_parent(
                    loop_state,
                    cs,
                    kind=sub_kind,
                    task=task_text or f"execute {len(steps)} steps",
                    summary="; ".join(
                        f"{r['tool']}: {(r['summary'] or '')[:80]}" for r in raw_results
                    )[:2000],
                    append_retrieval=append_retrieval_context,
                )
                ss = list(cs.get("executed_tool_calls") or [])
                if ss:
                    sd, sf = [], set()
                    for s in ss:
                        fp = s.get("fingerprint") or s.get("step_id") or ""
                        if fp not in sf:
                            sf.add(fp)
                            sd.append(s)
                    loop_state["subagent_executed_steps"] = sd[-20:]
        step_msgs = [f"{r['tool']}: {r['summary'][:60]}" for r in raw_results]
        return json.dumps({
            "ok": all(r["ok"] for r in raw_results),
            "summary": f"执行了 {len(raw_results)} 个步骤：" + "；".join(step_msgs),
            "step_results": raw_results,
        }, ensure_ascii=False)

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

    # summary 使用子 Agent 的实际产出内容，而非元数据
    MAX_SUMMARY = 20000
    if raw_text:
        summary = raw_text[:MAX_SUMMARY]
    else:
        query_info = f"。搜索词：{'、'.join(sub_queries[:5])}" if sub_queries else ""
        summary = f"子智能体（{kind}）已完成{query_info}{url_info}"
    truncated = raw_text[:4000] if len(raw_text) > 4000 else raw_text

    return json.dumps(
        {"ok": ok, "summary": summary, "data": {"result": truncated}},
        ensure_ascii=False,
    )
