"""AI 智能体 tool-calling 多轮循环 — Loop Engineering 主实现。

六相循环：
  1 输入捕获     — user_message / intent_plan / resolve_execution_plan
  2 上下文组装   — inject_retrieval_context_message / build_plan_context_instruction
  3 模型推理     — chat_completion_message_async
  4 动作执行     — execute_agent_tool（含本轮去重缓存）
  5 观测校验     — execution_goal_satisfied / request_fulfilled
  6 记忆更新     — loop_state + resolve_adaptive_replan → 回到 2
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent_loop_session import AgentLoopSession
from app.core.aip.handoff import build_specialist_assist_handoff
from app.agentkit.aip.messaging import attach_handoff_to_complete
from app.integrations.deepseek_client import chat_completion_stream_choice
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_reply_synth import (
    finalize_specialist_handoff,
    iter_synthesize_tool_loop_user_reply_events,
)
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
)
from app.services.agent_intent import AgentToolPlan
from app.services.agent_planner import (
    RETRIEVAL_ATOMIC_TOOLS,
    SKILL_MGMT_INTENT,
    AgentExecutionPlan,
    build_plan_context_instruction,
    execution_plan_summary_for_ui,
    filter_tool_specs_by_plan,
    resolve_execution_plan,
    resolve_kg_planning_context,
)
from app.core.agent_message_parse import (
    assistant_content_is_deliverable,
    normalize_llm_assistant_message,
    strip_dsml_markup,
)
from app.core.agent_tool_context import (
    compress_tool_result_for_loop,
    inject_retrieval_context_message,
    lookup_cached_tool_result,
    record_executed_tool_call,
    trim_agent_loop_messages,
)
from app.services.agent_skill_router import is_skill_management_message
from app.services.agent_tools import (
    build_agent_tool_specs,
    execute_agent_tool,
    maybe_inject_skill_dev_playbook,
    maybe_inject_skill_md,
    record_stream_screenshot_attachment,
    tool_workflow_meta,
)
from app.services.agent_skill_runtime import build_agent_runtime_tool_specs


# ── 父编排（orchestrator）可直调的已挂载原语；其余已挂载原子工具强制子智能体执行 ──
# 可见上界始终是「该 Agent 已挂载集」，不是平台全库。
# 专精 Agent / isolated 子智能体不受此限制，本域可直执。
_PARENT_DIRECT_TOOLS = frozenset({
    "invoke_context_subagent",      # 子智能体委托
    "request_orchestrator_assist",  # 路由协助
    "ask_user_choice",              # 用户交互
    "find_skills",                  # 技能发现（非执行）
    "describe_tool",                # 工具定义查询（非执行）
    "search_tools",                 # 原子工具目录检索（非执行）
})
# 旧名兼容
_PARENT_DELEGATION_TOOLS = _PARENT_DIRECT_TOOLS


def _should_delegate_to_subagent(loop_state: LoopState | None, tool_name: str) -> bool:
    """父编排层非直调工具 → True（须走子智能体）；专精/子 Agent → False。"""
    if tool_name in _PARENT_DIRECT_TOOLS:
        return False
    state = loop_state or {}
    if state.get("isolated_subagent"):
        return False
    aid = str(state.get("agent_id") or "").strip()
    return aid in ("", "orchestrator")

# ── 系统提示词裁剪：通用缩短规则（直接回答场景） ──────────────
_SYSTEM_TRIM_RULES: list[tuple[str, str]] = [
    # 移除运行上下文块
    (r"\n*【运行时】\n(?:.+\n)*", "\n"),
    # 移除技能目录块
    (r"\n*## 可用技能目录\n(?:.+\n)*", "\n"),
    (r"\n*### 本轮相关 Skill[^\n]*\n(?:.+\n)*?", "\n"),
    # 移除用户记忆块
    (r"\n*【用户记忆】\n(?:.+\n)*", "\n"),
    # 移除路由分配原因
    (r"\n*【路由分配原因】\n(?:.+\n)*", "\n"),
    # 移除检索上下文指令
    (r"\n*【任务背景】\n(?:.+\n)*", "\n"),
]


def _trim_system_for_direct_answer(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对于直接回答场景，裁剪系统提示词中工具/技能/记忆等无关上下文，加速 LLM 响应。"""
    out = [dict(m) for m in messages]
    for msg in out:
        if msg.get("role") != "system":
            continue
        content = str(msg.get("content") or "")
        for pattern, replacement in _SYSTEM_TRIM_RULES:
            content = re.sub(pattern, replacement, content)
        # 清理连续空行
        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        msg["content"] = content
    return out


def _build_subagent_task(tool_name: str, raw_args: Any) -> str:
    """将父智能体的工具调用转为子智能体任务描述。"""
    try:
        params = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
    except (json.JSONDecodeError, TypeError):
        params = {}
    args_str = json.dumps(params, ensure_ascii=False)
    return (
        f"请执行父智能体委托的工具调用，返回完整原始结果。\n"
        f"工具：{tool_name}\n"
        f"参数：{args_str}\n"
        f"要求：执行后返回工具的原始 OK/Error 结果（含 data 字段），不添加额外说明。"
    )


async def _run_tool_via_subagent(
    db: Session,
    user: User,
    tool_name: str,
    raw_args: Any,
    *,
    conversation_id: str | None,
    attachment_session_id: str | None,
    user_message: str,
    loop_state: LoopState,
    timeout: int,
) -> str:
    """将父智能体的工具调用委托给子智能体（kind=execute）执行。

    父智能体只能看到工具列表用于规划决策，不得直接执行。
    本函数将所有非委托工具调用透明路由到子智能体执行。
    """
    from app.core.agent.subagent import execute_context_subagent

    task = _build_subagent_task(tool_name, raw_args)
    try:
        return await asyncio.wait_for(
            execute_context_subagent(
                db, user,
                kind="execute",
                task=task,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                loop_state=loop_state,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return json.dumps(
            {"ok": False, "summary": f"子智能体执行超时（{timeout} 秒）"},
            ensure_ascii=False,
        )


def _dedupe_exec_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一轮内相同工具+相同参数只执行一次，避免提醒/写操作被重复提交。

    对 schedule_notification / send_notification：同一 title 只保留首条
    （scheduled_at 差一秒也会被去重）。
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for step in steps:
        tool = str(step.get("tool") or "").strip()
        args = step.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        if tool in ("schedule_notification", "send_notification"):
            title = str(args.get("title") or args.get("body") or "").strip()
            key = f"{tool}#title:{title or json.dumps(args, ensure_ascii=False, sort_keys=True)}"
        else:
            try:
                args_key = json.dumps(args, ensure_ascii=False, sort_keys=True)
            except (TypeError, ValueError):
                args_key = str(args)
            key = f"{tool}#{args_key}"
        if key in seen:
            continue
        seen.add(key)
        out.append(step)
    return out


async def _run_steps_via_subagent(
    db, user, steps, *, conversation_id, attachment_session_id, user_message, loop_state, timeout,
) -> str:
    """批量步骤委托给 execute 子Agent 一次执行。"""
    from app.core.agent.subagent import execute_context_subagent
    try:
        return await asyncio.wait_for(
            execute_context_subagent(db, user, kind="execute", steps=steps,
                conversation_id=conversation_id, attachment_session_id=attachment_session_id,
                loop_state=loop_state),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return json.dumps({"ok": False, "summary": f"子智能体执行超时（{timeout} 秒）", "step_results": []})


def _human_tool_call_detail(tool_name: str, raw_args: dict[str, Any]) -> str:
    tn = (tool_name or "").strip()
    if not raw_args:
        return ""
    if tn == "web_search":
        q = str(raw_args.get("query") or "").strip()
        return f"搜索关键词：{q[:120]}" if q else "联网搜索"
    if tn == "fetch_url_content":
        url = str(raw_args.get("url") or "").strip()
        short = url.rstrip("/").rsplit("/", 1)[-1][:60] if "/" in url else url[:60]
        return f"读取网页：{short or url[:80]}" if url else "获取网页内容"
    if tn == "knowledge_retrieve":
        q = str(raw_args.get("query") or "").strip()
        return f"知识库检索：{q[:120]}" if q else "知识库检索"
    if tn == "kg_query":
        q = str(raw_args.get("question") or raw_args.get("query") or "").strip()
        return f"知识图谱查询：{q[:120]}" if q else "知识图谱查询"
    if tn == "browser_snapshot":
        return "读取当前页面结构"
    if tn == "browser_run_task":
        task = str(raw_args.get("task") or "").strip()
        return f"自动探索：{task[:120]}" if task else "自动探索网页"
    if tn == "browser_navigate":
        url = str(raw_args.get("url") or "").strip()
        short = url.rstrip("/").rsplit("/", 1)[-1][:60] if "/" in url else url[:60]
        return f"导航到：{short or url[:80]}" if url else "打开网页"
    if tn in ("run_tool_batch",):
        steps = raw_args.get("steps") or []
        count = len(steps) if isinstance(steps, list) else 0
        return f"并行执行 {count} 个检索任务"
    if tn in ("invoke_skill",):
        skill = str(raw_args.get("skill_name") or "").strip()
        action = str(raw_args.get("action") or "").strip()
        if skill and action:
            return f"调用技能 {skill} → {action}"
        return f"调用技能：{skill or '?'}"
    if tn == "schedule_notification":
        title = str(raw_args.get("title") or "").strip()
        return f"设置提醒：{title[:120]}" if title else "设置定时提醒"
    if tn == "send_notification":
        title = str(raw_args.get("title") or "").strip()
        return f"发送通知：{title[:120]}" if title else "发送系统通知"
    if tn == "mermaid_diagram":
        desc = str(raw_args.get("description") or "").strip()
        return f"绘制图表：{desc[:120]}" if desc else "生成 Mermaid 图表"
    for key in ("query", "question", "task", "url", "name", "keyword", "description"):
        val = str(raw_args.get(key) or "").strip()
        if val:
            return f"{val[:160]}"
    return ""
from app.services.agent_profile_service import resolve_effective_runtime_tool_names
from app.core.agent_checkpoint import (
    clear_checkpoint,
    generate_checkpoint_id,
    save_checkpoint,
)
from app.core.agent_loop_state import LoopState
from app.core.human_in_the_loop import (
    build_confirmation_summary,
    clear_pending_choice,
    clear_pending_confirmation,
    generate_choice_id,
    generate_confirmation_id,
    get_choice_response,
    get_confirm_response,
    is_confirmation_required,
    set_pending_choice,
    set_pending_confirmation,
)

_logger = logging.getLogger(__name__)


def _default_max_rounds() -> int:
    settings = get_settings()
    return max(1, int(getattr(settings, "agent_max_tool_rounds", 40) or 40))


def _parse_tool_summary(result_text: str) -> tuple[bool, str]:
    try:
        body = json.loads(result_text)
        if isinstance(body, dict):
            return bool(body.get("ok")), str(body.get("summary") or "")
    except json.JSONDecodeError:
        pass
    return False, result_text[:200]


def _tool_timeout() -> int:
    from app.config import get_settings

    return max(10, int(get_settings().agent_tool_timeout_sec or 60))


def _progress_heartbeat_detail(loop_state: LoopState, fallback: str) -> str:
    """心跳文案优先用最近进度 / 网页解析状态，避免固定「请稍候」。"""
    hint = str(loop_state.get("_last_progress_hint") or "").strip()
    if hint:
        return hint[:160]
    state = loop_state.get("_url_parse_state")
    if isinstance(state, dict):
        urls = state.get("urls") or []
        parsing = [
            str(u.get("url") or "")
            for u in urls
            if isinstance(u, dict) and u.get("status") == "parsing"
        ]
        done = int(state.get("done") or 0)
        total = int(state.get("total") or 0)
        if parsing:
            short = parsing[0]
            if len(short) > 64:
                short = short[:61] + "..."
            return f"解析中 {done}/{total}：{short}" if total else f"解析中：{short}"
        if total:
            return f"网页解析 {done}/{total}"
    return (fallback or "执行中")[:160]


async def _iter_execute_with_progress(
    coro,
    loop_state: LoopState,
    *,
    timeout: float,
    heartbeat_title: str = "执行中",
    heartbeat_tool: str = "tool.execute",
):
    """执行工具协程并泵送 progress_queue；yield workflow 事件，最后 yield ("__result__", text)。"""
    progress_queue: asyncio.Queue = asyncio.Queue()
    loop_state["_progress_queue"] = progress_queue
    tool_task = asyncio.ensure_future(coro)
    start_ts = time.monotonic()
    result_text = ""
    try:
        while not tool_task.done():
            elapsed = time.monotonic() - start_ts
            if elapsed > timeout:
                tool_task.cancel()
                try:
                    await tool_task
                except (asyncio.CancelledError, Exception):
                    pass
                result_text = json.dumps(
                    {"ok": False, "summary": f"工具执行超时（{int(timeout)} 秒）"},
                    ensure_ascii=False,
                )
                tool_task = None
                break
            get_task = asyncio.ensure_future(progress_queue.get())
            done, _pending = await asyncio.wait(
                [tool_task, get_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=2.5,
            )
            if tool_task in done:
                get_task.cancel()
                break
            if get_task in done:
                ev = get_task.result()
                if isinstance(ev, dict):
                    yield {"type": "workflow", "data": ev}
                continue
            get_task.cancel()
            detail = _progress_heartbeat_detail(loop_state, heartbeat_title)
            parse_state = loop_state.get("_url_parse_state")
            if isinstance(parse_state, dict) and parse_state.get("urls"):
                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "url_parse_progress",
                        "title": heartbeat_title,
                        "detail": detail,
                        "tool": heartbeat_tool,
                        "tool_name": "web_search",
                        "step_id": f"tool-hb-{uuid.uuid4().hex[:8]}",
                        "urls": parse_state.get("urls"),
                        "done": parse_state.get("done"),
                        "total": parse_state.get("total"),
                        "current_url": parse_state.get("current_url") or "",
                    },
                }
            else:
                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "orchestrator_progress",
                        "title": heartbeat_title,
                        "detail": detail,
                        "tool": heartbeat_tool,
                        "step_id": f"tool-hb-{uuid.uuid4().hex[:8]}",
                    },
                }
        if tool_task is not None:
            try:
                result_text = tool_task.result()
            except Exception as exc:
                result_text = json.dumps(
                    {"ok": False, "summary": f"工具执行异常：{exc}"},
                    ensure_ascii=False,
                )
        while not progress_queue.empty():
            try:
                ev = progress_queue.get_nowait()
                if isinstance(ev, dict):
                    yield {"type": "workflow", "data": ev}
            except asyncio.QueueEmpty:
                break
    finally:
        loop_state.pop("_progress_queue", None)
    yield {"type": "__result__", "text": result_text}


def _is_retryable_error(result_text: str) -> bool:
    """判断工具错误是否可能是临时故障（超时/网络/数据库），值得自动重试一次。"""
    try:
        body = json.loads(result_text)
        summary = str(body.get("summary", "")).lower()
    except (json.JSONDecodeError, TypeError):
        return False
    retryable_keywords = [
        "timeout", "timed out", "超时",
        "connection", "connect", "网络",
        "database error", "数据库",
        "temporary", "temporarily",
        "too many requests", "rate limit",
    ]
    return any(kw in summary for kw in retryable_keywords)


def _workflow_result_title(meta: dict[str, Any], *, ok: bool) -> str:
    if ok:
        return str(meta.get("result_title") or meta.get("title") or "完成")
    return str(meta.get("result_title") or meta.get("title") or "操作完成")


def _finalize_loop_reply(reply: str | None, loop_state: LoopState) -> str | None:
    from app.services.agent_orchestrator import append_screenshot_markdown_to_reply

    attachments = list(loop_state.get("collected_attachments") or [])
    if not attachments:
        return reply
    return append_screenshot_markdown_to_reply(reply, attachments)


def _streamed_attachment_urls(loop_state: LoopState) -> set[str]:
    return {
        str(url).strip()
        for url in (loop_state.get("streamed_attachment_urls") or [])
        if str(url).strip()
    }


def _mark_streamed_attachment(loop_state: LoopState, att: dict[str, Any]) -> None:
    url = str(att.get("url") or "").strip()
    if not url:
        return
    seen = _streamed_attachment_urls(loop_state)
    seen.add(url)
    loop_state["streamed_attachment_urls"] = sorted(seen)


def _pending_screenshot_attachments(loop_state: LoopState) -> list[dict[str, Any]]:
    """尚未通过 SSE attachment 下发的截图。"""
    streamed = _streamed_attachment_urls(loop_state)
    pending: list[dict[str, Any]] = []
    for att in list(loop_state.get("collected_attachments") or []):
        if not isinstance(att, dict):
            continue
        url = str(att.get("url") or "").strip()
        if not url or url in streamed:
            continue
        pending.append(dict(att))
        streamed.add(url)
    loop_state["streamed_attachment_urls"] = sorted(streamed)
    return pending


async def _maybe_auto_browser_screenshot(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    attachment_session_id: str | None,
    loop_state: LoopState,
    user_message: str,
) -> None:
    """用户要求截图且已操作浏览器但未截图时，经 execute 子智能体补拍（父层不直执）。"""
    from app.services.agent_skill_router import user_wants_browser_screenshot

    if not user_wants_browser_screenshot(user_message):
        return
    if not loop_state.get("browser_session_used"):
        return
    if loop_state.get("collected_attachments"):
        return
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config

    if not get_browser_rpa_config(db).enabled:
        return
    try:
        from app.core.agent.subagent import execute_context_subagent

        await execute_context_subagent(
            db,
            user,
            kind="execute",
            task="补拍当前浏览器页面截图",
            steps=[{"tool": "browser_screenshot", "arguments": {}}],
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            loop_state=loop_state,
        )
    except Exception as exc:
        _logger.warning("自动浏览器截图失败: %s", exc)


def _available_atomic_from_specs(specs: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for spec in specs:
        name = str((spec.get("function") or {}).get("name") or "")
        if name in RETRIEVAL_ATOMIC_TOOLS:
            names.add(name)
    return names


def _narrow_execution_plan_for_specialist(
    plan: AgentExecutionPlan,
    *,
    agent_id: str | None,
    allowed_skill_names: set[str] | None,
    user_message: str = "",
) -> AgentExecutionPlan:
    """专精智能体边界收窄：仅做 skill 白名单校验 + 无能力时安全回退。

    planner（_build_specialist_domain_plan）已为各专精构建正确计划；
    本函数仅做两层安全兜底：
      1. 如果 plan 引用了不在 allowed_skill_names 中的 skill → 剥离
      2. 如果专精没有任何可用 skill 却需执行 → 转为直接回答，
         防止 LLM 在无边界约束下调用跨域工具

    例外：规则生成的 plan 已经过 explicit skill 匹配，且 uploaded_skill 由
    _rule_plan_for_uploaded_skill_followup 精确匹配产生，应予以信任，
    不在 allowed_skill_names 中时不剥离。
    """
    if (
        allowed_skill_names is not None
        and plan.uploaded_skill
        and plan.source != "rule"
    ):
        if plan.uploaded_skill not in allowed_skill_names:
            plan = replace(plan, uploaded_skill=None)

    aid = (agent_id or "").strip()
    if (
        aid
        and not plan.direct_answer
        and allowed_skill_names is not None
        and not allowed_skill_names
    ):
        # 当前专精没有任何可用 Skill 时强制直接回答，
        # 避免 LLM 调用不属于本域的全局 Tool
        # 例外：plan 有 uploaded_skill 且由规则生成时信任该计划
        if plan.uploaded_skill and plan.source == "rule":
            return plan
        return replace(
            plan,
            intent=plan.intent or f"{aid} 专精",
            direct_answer=True,
            allowed_tools=(),
            blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            steps=(),
        )
    return plan


def _emit_report_reply_deltas(text: str, *, chunk_size: int = 600) -> list[dict[str, Any]]:
    body = (text or "").strip()
    if not body:
        return []
    return [
        {"type": "delta", "text": body[i : i + chunk_size]}
        for i in range(0, len(body), chunk_size)
    ]


def _messages_have_prefetched_research(messages: list[dict[str, Any]]) -> bool:
    """首页 prefetch 已注入参考材料时，跳过规划前重复的图谱查询。"""
    marker = "预先检索到的参考材料"
    for row in messages:
        if row.get("role") != "system":
            continue
        if marker in str(row.get("content") or ""):
            return True
    return False


# ─── nudge 消息预构建缓存 ────────────────────────────────────


def _build_nudge_cache(
    user_message: str,
    execution_plan: AgentExecutionPlan,
    plan_has_script: bool | None,
) -> dict[str, str]:
    """预构建 nudge 消息缓存（避免热循环中重复字符串构造）。"""
    from app.services.agent_skill_router import is_platform_system_data_message

    nudges: dict[str, str] = {
        "dsml": (
            "【系统】禁止在正文输出 DSML / tool_calls 标记。"
            "必须通过 API tool_calls 调用 knowledge_retrieve、web_search、"
            "load_uploaded_skill；content 留空即可。"
        ),
        "instruction": (
            "【系统】必须通过 tool_calls 执行操作并拿到真实结果后再回答。"
            "如果你写了「我来搜索」「已安排通知」等文字而没有实际调用工具，"
            "请立即调用 web_search 等工具获取真实数据后再回答。"
            "若工具/Skill 调用返回了失败信息，**必须**如实告知用户错误详情，"
            "禁止编造数据来掩盖调用失败。宁可说「无法执行」也不可伪造结果。"
        ),
    }
    if is_platform_system_data_message(user_message):
        nudges["platform"] = (
            "【系统】必须先调用工具获取真实数据（如 search_documents_by_name / list_todos / send_notification 等）；"
            "禁止编造数据或仅用文字描述来假装已完成操作。"
        )
    if execution_plan.uploaded_skill:
        skill = execution_plan.uploaded_skill
        nudges["uploaded_skill"] = (
            f"【系统】必须调用 invoke_context_subagent(kind=use, "
            f"task=使用技能 {skill} 完成用户请求) 委托子智能体执行；"
            "禁止只在正文复述 SKILL.md 或空口作答。"
        )
    if execution_plan.intent == "浏览器操作":
        nudges["browser"] = (
            "【系统】必须调用 invoke_context_subagent(kind=execute, "
            "task=用户浏览器需求) 完成导航/搜索/截图；"
            "优先 browser_run_task 或分步 browser_*。"
        )
    return nudges


# ─── HITL Checkpoint 辅助函数 ─────────────────────────────

_HITL_POLL_TIMEOUT_SEC = 30  # 活跃轮询超时（秒），超时后进入 suspended 状态
_HITL_POLL_INTERVAL = 0.5  # 轮询间隔


async def _hitl_poll(
    get_response: Callable[[], str | None],
    *,
    timeout: int = _HITL_POLL_TIMEOUT_SEC,
) -> str | None:
    """通用 HITL 轮询：持续检查 ``get_response()``，超时返回 None。"""
    import time

    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        response = get_response()
        if response is not None:
            return response
        await asyncio.sleep(_HITL_POLL_INTERVAL)


def _build_checkpoint_pending_tool(
    tool_name: str,
    tool_id: str,
    raw_args: str,
    step_id: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_id": tool_id,
        "raw_args": raw_args,
        "step_id": step_id,
        "meta": meta,
    }


# ─── 异步生成器：各退出路径（以 yield complete 结束） ──────────────


async def _emit_direct_reply_complete(
    loop_id: str,
    deliverable_reply: str,
    working: list[dict[str, Any]],
    loop_state: LoopState,
) -> AsyncIterator[dict[str, Any]]:
    """直接可交付回答：仅 yield complete。"""
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "回答完成",
            "detail": "已按技能说明生成内容",
            "tool": "agent.direct",
            "step_id": loop_id,
            "status": "done",
        },
    }
    yield {
        "type": "complete",
        "messages": working,
        "reply": _finalize_loop_reply(deliverable_reply, loop_state),
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }


async def _emit_task_handoff_complete(
    sess: AgentLoopSession,
    db: Session,
    user: User,
    loop_id: str,
    loop_state: LoopState,
    working: list[dict[str, Any]],
    *,
    user_message: str,
    conversation_id: str | None,
    task_id: str | None,
    agent_id: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """子任务调度（handoff/assist）完成路径。"""
    assist_req = loop_state.get("orchestrator_assist_request")
    if isinstance(assist_req, dict) and assist_req.get("reason"):
        handoff = build_specialist_assist_handoff(
            loop_state,
            agent_id=(agent_id or "").strip(),
            session_id=(conversation_id or "").strip() or f"session-{loop_id}",
            task_id=(task_id or "").strip() or f"task-{loop_id}",
            assist=assist_req,
            citations=list(loop_state.get("citations") or []),
            kg_context=loop_state.get("kg_context"),
        )
    else:
        sess.release_before_io()
        handoff = await finalize_specialist_handoff(
            loop_state,
            user_message,
            agent_id=(agent_id or "").strip(),
            session_id=(conversation_id or "").strip() or f"session-{loop_id}",
            task_id=(task_id or "").strip() or f"task-{loop_id}",
            citations=list(loop_state.get("citations") or []),
            kg_context=loop_state.get("kg_context"),
        )
        db, user = sess.open()
        loop_state["task_deliverable"] = (
            handoff.text if handoff.ok else loop_state.get("task_deliverable")
        )
    final_reply = handoff.text if handoff.ok else None
    is_assist = isinstance(assist_req, dict) and bool(assist_req.get("reason"))
    if final_reply:
        working.append({"role": "assistant", "content": final_reply})
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": (
                "已请求调度协助"
                if is_assist
                else ("子任务完成" if handoff.ok else "子任务未完成")
            ),
            "detail": (assist_req or {}).get("reason", "")[:120] if is_assist else "",
            "tool": "agent.orchestrator.assist" if is_assist else "agent.handoff",
            "step_id": loop_id,
            "status": "done" if handoff.ok else "failed",
        },
    }
    complete_payload: dict[str, Any] = {
        "type": "complete",
        "messages": working,
        "reply": _finalize_loop_reply(final_reply, loop_state),
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }
    yield attach_handoff_to_complete(complete_payload, handoff.message)


async def emit_final_user_reply(
    sess: AgentLoopSession,
    uid: uuid.UUID,
    loop_id: str,
    user_message: str,
    working: list[dict[str, Any]],
    loop_state: LoopState,
    *,
    chat_history: list[AiChatMessage] | None,
) -> AsyncIterator[dict[str, Any]]:
    """综合工具结果生成最终用户回答（六相循环退出 / 专精 hop 父层终稿）。"""
    synth_id = f"agent-synth-{uuid.uuid4().hex[:8]}"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "根据工具执行结果汇总回答",
            "detail": "",
            "tool": "agent.synthesize",
            "step_id": synth_id,
        },
    }
    from app.services.agent_memory_service import build_memory_prompt_context

    sess.release_before_io()
    _synth_t0 = time.monotonic()
    synth_reply_parts: list[str] = []
    synth_failed = False
    async for ev in iter_synthesize_tool_loop_user_reply_events(
        user_message=user_message,
        loop_state=loop_state,
        memory_context=build_memory_prompt_context(uid),
        chat_history=chat_history,
        step_id=synth_id,
    ):
        if ev.get("type") == "workflow":
            yield {"type": "workflow", "data": ev["data"]}
        elif ev.get("type") == "delta" and ev.get("text"):
            synth_reply_parts.append(str(ev["text"]))
            yield {"type": "delta", "text": ev["text"]}
        elif ev.get("type") == "complete_text":
            text = str(ev.get("text") or "").strip()
            if text:
                for chunk in _emit_report_reply_deltas(text):
                    synth_reply_parts.append(str(chunk["text"]))
                    yield chunk
        elif ev.get("type") == "error":
            synth_failed = True
            yield {"type": "error", "message": ev.get("message", "回答合成失败")}
    if synth_failed:
        _logger.warning("synthesis LLM failed after %.1fs", time.monotonic() - _synth_t0)
        # 合成失败时用 fallback 回复兜底
        from app.services.agent_reply_synth import fallback_tool_loop_reply

        fallback = fallback_tool_loop_reply(user_message, loop_state)
        if fallback:
            yield {"type": "delta", "text": fallback}
            synth_reply_parts.append(fallback)
    _synth_elapsed = time.monotonic() - _synth_t0
    _logger.info("synthesis LLM done in %.1fs", _synth_elapsed)
    final_reply = "".join(synth_reply_parts).strip() or None
    if final_reply:
        working.append({"role": "assistant", "content": final_reply})
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": "执行完成",
            "detail": "已根据工具结果生成结论",
            "tool": "agent.execute",
            "step_id": loop_id,
            "status": "done",
        },
    }
    yield {
        "type": "complete",
        "messages": working,
        "reply": _finalize_loop_reply(final_reply or None, loop_state),
        "citations": list(loop_state.get("citations") or []),
        "kg_context": loop_state.get("kg_context"),
    }


# ─── 入口 ─────────────────────────────────────────────


async def iter_agent_tool_loop(
    user: User | uuid.UUID,
    messages: list[dict[str, Any]],
    *,
    conversation_id: str | None = None,
    max_rounds: int | None = None,
    user_message: str = "",
    attachment_session_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    intent_plan: AgentToolPlan | None = None,
    chat_history: list[AiChatMessage] | None = None,
    agent_id: str | None = None,
    allowed_tool_names: set[str] | None = None,
    allowed_skill_names: set[str] | None = None,
    scoped_doc_ids: list[str] | None = None,
    local_kb_disabled: bool = False,
    task_mode: bool = False,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出 workflow 事件；结束时 yield type=complete。内部按轮次管理 DB 会话。"""
    from app.core.agent_loop_session import coerce_user_id

    user_id = coerce_user_id(user)
    sess = AgentLoopSession(user_id)
    try:
        db, user = sess.open()
        async for event in _iter_agent_tool_loop_body(
            sess,
            db,
            user,
            messages,
            conversation_id=conversation_id,
            max_rounds=max_rounds,
            user_message=user_message,
            attachment_session_id=attachment_session_id,
            tools=tools,
            intent_plan=intent_plan,
            chat_history=chat_history,
            agent_id=agent_id,
            allowed_tool_names=allowed_tool_names,
            allowed_skill_names=allowed_skill_names,
            scoped_doc_ids=scoped_doc_ids,
            local_kb_disabled=local_kb_disabled,
            task_mode=task_mode,
            task_id=task_id,
        ):
            yield event
    finally:
        sess.close()


async def _iter_agent_tool_loop_body(
    sess: AgentLoopSession,
    db: Session,
    user: User,
    messages: list[dict[str, Any]],
    *,
    conversation_id: str | None,
    max_rounds: int | None,
    user_message: str,
    attachment_session_id: str | None,
    tools: list[dict[str, Any]] | None,
    intent_plan: AgentToolPlan | None,
    chat_history: list[AiChatMessage] | None,
    agent_id: str | None,
    allowed_tool_names: set[str] | None,
    allowed_skill_names: set[str] | None,
    scoped_doc_ids: list[str] | None,
    local_kb_disabled: bool,
    task_mode: bool,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    uid = user.id
    working: list[dict[str, Any]] = [dict(m) for m in messages]
    loop_id = f"agent-tools-{uuid.uuid4().hex[:8]}"
    # 工具可见上界 = 该 Agent 已挂载集（binding / whitelist），非平台全库。
    # 技能：find_skills 按 binding 过滤；allowed_skill_names 仍用于专精域限制
    # （父编排保持 None，以免误剥上传型 Skill 的 use 计划）。
    aid = (agent_id or "").strip() or "orchestrator"
    if tools is not None:
        all_tool_specs = tools
    elif allowed_tool_names is not None:
        all_tool_specs = build_agent_tool_specs(
            db, user, allowed_names=allowed_tool_names, agent_id=aid
        )
    elif aid != "orchestrator":
        tool_names = resolve_effective_runtime_tool_names(db, aid)
        all_tool_specs = build_agent_runtime_tool_specs(
            db,
            user,
            agent_id=aid,
            allowed_skill_names=list(allowed_skill_names) if allowed_skill_names else None,
            runtime_tool_names=tool_names,
        )
    else:
        # 父编排：已挂载工具 − 技能直执入口（build_agent_tool_specs 内处理）
        all_tool_specs = build_agent_tool_specs(db, user, agent_id=aid)
    # Agent 有知识库挂载且未显式传入 scoped_doc_ids 时自动注入
    if scoped_doc_ids is None and agent_id:
        try:
            from app.services.agent_knowledge_mount_service import (
                list_mounts,
                resolve_mounts_to_doc_ids,
            )
            mounts = list_mounts(db, agent_id)
            if mounts:
                resolved = resolve_mounts_to_doc_ids(db, user, mounts)
                if resolved:
                    scoped_doc_ids = resolved
        except Exception:
            pass  # 静默失败，不阻塞工具循环
    rounds = max_rounds if max_rounds is not None else _default_max_rounds()
    loop_state: LoopState = {
        "conversation_id": conversation_id,
        "attachment_session_id": attachment_session_id,
        "citations": [],
        "kg_context": None,
        "allowed_skill_names": allowed_skill_names,
        "_all_tool_specs": all_tool_specs,
        "scoped_doc_ids": list(scoped_doc_ids) if scoped_doc_ids is not None else None,
        "local_kb_disabled": local_kb_disabled,
        "task_mode": task_mode,
        "agent_id": (agent_id or "").strip() or None,
        "auto_skill_creation": user_message.startswith("【调度自动补能力】"),
        "_tool_failure_counts": {},
    }

    from app.services.kg_service import try_department_members_deterministic_reply

    dept_reply = try_department_members_deterministic_reply(db, user, user_message)
    if dept_reply:
        loop_state["deterministic_reply"] = dept_reply
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "已从知识图谱读取部门成员",
                "detail": "",
                "tool": "kg.org_members",
                "step_id": loop_id,
                "status": "done",
            },
        }
        yield {
            "type": "complete",
            "messages": working,
            "reply": dept_reply,
            "citations": [],
            "kg_context": loop_state.get("kg_context"),
        }
        return

    kg_plan_text = ""
    from app.services.agent_intent import is_chitchat_message
    from app.services.agent_skill_router import is_trivial_direct_question

    skip_kg_plan = is_chitchat_message(user_message, chat_history) or is_trivial_direct_question(
        user_message
    )
    if not skip_kg_plan and not _messages_have_prefetched_research(working):
        kg_plan_text = await resolve_kg_planning_context(
            db, user, user_message, history=chat_history
        )

    plan_step_id = f"agent-plan-{uuid.uuid4().hex[:8]}"
    plan_detail = "分析意图，拆解执行计划…"
    # 如果已有 KG 规划上下文则附带提示
    if kg_plan_text and len(kg_plan_text) > 10:
        plan_detail = f"参考知识图谱上下文进行规划…"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": "正在规划执行步骤",
            "detail": plan_detail,
            "tool": "planner",
            "step_id": plan_step_id,
        },
    }
    _plan_t0 = time.monotonic()
    execution_plan = await resolve_execution_plan(
        db,
        user,
        message=user_message,
        history=chat_history,
        intent_plan=intent_plan,
        available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
        kg_planning_context=kg_plan_text or None,
        agent_id=agent_id,
    )
    _plan_elapsed = time.monotonic() - _plan_t0
    _logger.info(
        "execution_plan resolved in %.1fs agent=%s source=%s intent=%s",
        _plan_elapsed, agent_id, execution_plan.source, execution_plan.intent,
    )
    loop_state["_execution_plan"] = execution_plan
    plan_summary = execution_plan_summary_for_ui(execution_plan)
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thought",
            "title": f"规划方案：{execution_plan.intent or '执行步骤'}",
            "detail": plan_summary,
            "tool": "planner",
            "step_id": plan_step_id,
            "status": "done",
        },
    }

    execution_plan = _narrow_execution_plan_for_specialist(
        execution_plan,
        agent_id=agent_id,
        allowed_skill_names=allowed_skill_names,
        user_message=user_message,
    )

    if (
        allowed_tool_names is not None
        and not allowed_tool_names
        and not execution_plan.direct_answer
        and (
            execution_plan.allowed_tools
            or any(
                token in " ".join(execution_plan.steps).lower()
                for token in ("web_search", "knowledge_retrieve", "kg_query", "invoke_skill")
            )
        )
    ):
        execution_plan = replace(
            execution_plan,
            direct_answer=True,
            reasoning=(execution_plan.reasoning or "") + "（当前智能体无检索工具，改为直接作答）",
            allowed_tools=(),
            blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            steps=(),
        )

    if execution_plan.uploaded_skill:
        loop_state["planned_uploaded_skill"] = execution_plan.uploaded_skill

    plan_has_script = None
    if execution_plan.uploaded_skill:
        from app.services.agent_skill_service import uploaded_skill_has_script

        try:
            plan_has_script = uploaded_skill_has_script(db, execution_plan.uploaded_skill)
        except Exception:
            plan_has_script = None

    from app.services.agent_execution_closure import execution_plan_needs_skill_data

    if execution_plan_needs_skill_data(
        execution_plan, user_message, plan_has_script=plan_has_script
    ):
        loop_state["expects_skill_data"] = True

    # 执行阶段的标题根据执行计划调整，包含更具体的意图
    exec_title = execution_plan.intent[:60] if (execution_plan.intent or "").strip() else "正在执行任务"
    if execution_plan.uploaded_skill:
        exec_title = f"按「{execution_plan.uploaded_skill}」技能执行"
    yield {
        "type": "workflow",
        "data": {
            "phase": "agent_thinking",
            "title": exec_title,
            "detail": execution_plan_summary_for_ui(execution_plan),
            "tool": "agent.execute",
            "step_id": loop_id,
        },
    }

    # direct_answer 捷径仅用于闲聊/纯知识/指令型 Skill；
    # 平台操作、检索、提醒等必须进 tool loop，禁止规划器误标后跳过工具。
    from app.services.agent_intent import is_chitchat_message
    from app.services.agent_skill_router import (
        is_platform_operation_message,
        is_trivial_direct_question,
        matches_platform_ops_extra,
        matches_research_signal,
        matches_scheduler_intent,
    )

    _needs_tools = (
        matches_platform_ops_extra(user_message)
        or is_platform_operation_message(user_message)
        or matches_scheduler_intent(user_message)
        or matches_research_signal(user_message)
    )
    _direct_ok = bool(execution_plan.direct_answer) and (
        bool(execution_plan.uploaded_skill)
        or (
            not _needs_tools
            and (
                is_chitchat_message(user_message, chat_history)
                or is_trivial_direct_question(user_message)
            )
        )
    )
    if execution_plan.direct_answer and not _direct_ok:
        from dataclasses import replace as _dc_replace

        execution_plan = _dc_replace(execution_plan, direct_answer=False)
        loop_state["_execution_plan"] = execution_plan

    if _direct_ok:
        from app.services.llm_workflow_stream import iter_llm_answer_events

        direct_reply_parts: list[str] = []

        # 注入 uploaded_skill 的 SKILL.md（如 mermaid-diagram）
        _skill_for_md = str(execution_plan.uploaded_skill or "").strip() or str(
            loop_state.get("planned_uploaded_skill") or ""
        ).strip()
        if _skill_for_md:
            working = maybe_inject_skill_md(
                db, user, loop_state, working, _skill_for_md
            )

        # 直接回答场景：裁剪系统提示词中的工具/技能/记忆等无关上下文，加速 LLM 响应
        working = _trim_system_for_direct_answer(working)

        sess.release_before_io()
        async for ev in iter_llm_answer_events(
            messages=working,
            temperature=0.5,
            think_title="生成回答",
            think_detail=execution_plan.intent or "直接作答",
            step_id=loop_id,
        ):
            if ev.get("type") == "workflow":
                yield {"type": "workflow", "data": ev["data"]}
            elif ev.get("type") == "delta" and ev.get("text"):
                direct_reply_parts.append(ev["text"])
                yield {"type": "delta", "text": ev["text"]}
        final_reply = "".join(direct_reply_parts).strip() or None
        if final_reply:
            working.append({"role": "assistant", "content": final_reply})
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "执行完成",
                "detail": execution_plan.intent or "已生成回复",
                "tool": "agent.execute",
                "step_id": loop_id,
                "status": "done",
            },
        }
        yield {
            "type": "complete",
            "messages": working,
            "reply": final_reply,
            "citations": list(loop_state.get("citations") or []),
            "kg_context": loop_state.get("kg_context"),
        }
        return

    plan_instruction = build_plan_context_instruction(
        execution_plan,
        uploaded_skill_has_script=plan_has_script,
    )
    if plan_instruction:
        working = [dict(m) for m in working]
        working.append({"role": "system", "content": plan_instruction})
    working = maybe_inject_skill_dev_playbook(
        loop_state,
        working,
        agent_id=agent_id,
        skill_mgmt=execution_plan.intent == SKILL_MGMT_INTENT,
    )
    initial_skill = (
        str(execution_plan.uploaded_skill or "").strip()
        or str(loop_state.get("planned_uploaded_skill") or "").strip()
    )
    allowed_skills = loop_state.get("allowed_skill_names")
    # 规则生成的 plan 已通过 explicit skill 匹配，trust it
    is_rule_plan = execution_plan.source == "rule" and bool(execution_plan.uploaded_skill)
    if (
        initial_skill
        and allowed_skills is not None
        and initial_skill not in allowed_skills
        and not is_rule_plan
    ):
        initial_skill = ""
    if initial_skill:
        working = maybe_inject_skill_md(db, user, loop_state, working, initial_skill)

    from app.services.agent_execution_closure import (
        apply_execution_plan_context,
        auto_execute_mermaid_diagram,
        auto_execute_uploaded_skill,
        build_skill_management_continue_nudge,
        execution_goal_satisfied,
        execution_plan_needs_skill_data,
        max_adaptive_execution_passes,
        resolve_adaptive_replan,
        resolve_target_uploaded_skill,
        tool_rounds_for_adaptive_pass,
    )
    from app.services.agent_planner import _plannable_skill_names

    all_skill_names = _plannable_skill_names(db, user, agent_id=agent_id)
    max_adaptive = max_adaptive_execution_passes()
    deliverable_reply: str | None = None
    instruction_only_skill = plan_has_script is False and bool(
        execution_plan.uploaded_skill or loop_state.get("planned_uploaded_skill")
    )

    for adaptive_pass in range(max_adaptive):
        if adaptive_pass > 0:
            if execution_goal_satisfied(
                execution_plan,
                loop_state,
                user_message,
                plan_has_script=plan_has_script,
            ):
                break
            prior_plan = execution_plan
            sess.release_before_io()
            _replan_t0 = time.monotonic()
            execution_plan = await resolve_adaptive_replan(
                db,
                user,
                message=user_message,
                history=chat_history,
                intent_plan=intent_plan,
                available_atomic_tools=_available_atomic_from_specs(all_tool_specs),
                kg_planning_context=kg_plan_text or None,
                prior_plan=prior_plan,
                loop_state=loop_state,
                uploaded_names=all_skill_names,
            )
            _replan_elapsed = time.monotonic() - _replan_t0
            _logger.info(
                "adaptive replan in %.1fs pass=%d agent=%s", _replan_elapsed, adaptive_pass, agent_id,
            )
            loop_state["_execution_plan"] = execution_plan
            execution_plan = _narrow_execution_plan_for_specialist(
                execution_plan,
                agent_id=agent_id,
                allowed_skill_names=allowed_skill_names,
                user_message=user_message,
            )
            db, user = sess.open()
            if execution_plan.uploaded_skill:
                from app.services.agent_skill_service import uploaded_skill_has_script

                try:
                    plan_has_script = uploaded_skill_has_script(
                        db, execution_plan.uploaded_skill
                    )
                except Exception:
                    plan_has_script = None
            apply_execution_plan_context(execution_plan, loop_state)
            if execution_plan_needs_skill_data(
                execution_plan, user_message, plan_has_script=plan_has_script
            ):
                loop_state["expects_skill_data"] = True
            replan_instruction = build_plan_context_instruction(
                execution_plan,
                uploaded_skill_has_script=plan_has_script,
            )
            if replan_instruction:
                working = [dict(m) for m in working]
                working.append({"role": "system", "content": replan_instruction})
            skill_for_md = str(execution_plan.uploaded_skill or "").strip()
            if skill_for_md:
                working = maybe_inject_skill_md(
                    db, user, loop_state, working, skill_for_md
                )
            instruction_only_skill = plan_has_script is False and bool(skill_for_md)
            loop_state["content_only_nudges"] = 0

        nudge_cache = _build_nudge_cache(user_message, execution_plan, plan_has_script)
        rounds_this_pass = tool_rounds_for_adaptive_pass(rounds, adaptive_pass)
        for _ in range(max(1, rounds_this_pass)):
            pending_skill = str(loop_state.get("pending_skill_md_inject") or "").strip()
            allowed_skills = loop_state.get("allowed_skill_names")
            if pending_skill and allowed_skills is not None and pending_skill not in allowed_skills:
                loop_state.pop("pending_skill_md_inject", None)
                pending_skill = ""
            if pending_skill:
                working = maybe_inject_skill_md(db, user, loop_state, working, pending_skill)
                loop_state.pop("pending_skill_md_inject", None)

            planned_specs = filter_tool_specs_by_plan(all_tool_specs, execution_plan)
            if allowed_tool_names is None:
                from app.services.agent_tool_search import select_visible_tool_specs

                agent_id = str(loop_state.get("agent_id") or "").strip() or None
                tool_specs = select_visible_tool_specs(
                    planned_specs, agent_id=agent_id
                )
            else:
                tool_specs = planned_specs
            llm_messages = trim_agent_loop_messages(
                inject_retrieval_context_message(working, loop_state),
                keep_full_tool_results=(
                    2 if is_skill_management_message(user_message) else 1
                ),
            )
            # 有工具可见时注入通用兜底指引：无合适工具时如实告知，勿乱调用
            if tool_specs:
                llm_messages.append({
                    "role": "system",
                    "content": (
                        "【系统提示】优先使用可用的工具和技能来满足用户请求。"
                        "如果确实没有任何可用的工具或技能能完成用户的请求，"
                        "直接告知用户你暂时无法完成，不要调用不相关的工具。"
                    ),
                })
            sess.release_before_io()
            choice = None
            _llm_t0 = time.monotonic()
            async for ev in chat_completion_stream_choice(
                messages=llm_messages,
                tools=tool_specs or None,
                temperature=0.3,
            ):
                if ev["type"] == "delta":
                    yield {
                        "type": "workflow",
                        "data": {"phase": "thinking_delta", "delta": ev["text"]},
                    }
                elif ev["type"] == "choice":
                    choice = ev
            _llm_elapsed = time.monotonic() - _llm_t0
            db, user = sess.open()
            if not choice:
                _logger.info("LLM call empty choice in %.1fs agent=%s", _llm_elapsed, agent_id)
                break
            message = normalize_llm_assistant_message(choice.get("message") or {})
            tool_calls = message.get("tool_calls") or []
            content = strip_dsml_markup(str(message.get("content") or "")).strip()

            if tool_calls:
                working.append(message)

                # ── 批量执行编排步骤（模式 B，路线 A） ──
                exec_steps: list[dict[str, Any]] = []
                for tc in tool_calls:
                    fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                    tn = str(fn.get("name") or "")
                    if _should_delegate_to_subagent(loop_state, tn):
                        raw_args = fn.get("arguments") or "{}"
                        try:
                            parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                        except (json.JSONDecodeError, TypeError):
                            parsed = {}
                        exec_steps.append({
                            "tool": tn, "arguments": parsed,
                            "tool_call_id": str(tc.get("id") or uuid.uuid4()),
                        })
                _batch_results: dict[str, dict[str, Any]] = {}
                _batch_streamed_tool_ids: set[str] = set()
                if exec_steps:
                    exec_steps = _dedupe_exec_steps(exec_steps)
                    plan_lines: list[str] = []
                    for s in exec_steps:
                        cd = _human_tool_call_detail(s["tool"], s["arguments"])
                        plan_lines.append(f"  {len(plan_lines) + 1}. {cd or s['tool']}")
                    _plan_summary = "；".join(
                        (cd or s["tool"])
                        for s in exec_steps
                        for cd in [_human_tool_call_detail(s["tool"], s["arguments"])]
                    )
                    yield {
                        "type": "workflow",
                        "data": {
                            "phase": "agent_plan",
                            "title": f"执行计划（{len(exec_steps)} 步）",
                            "detail": "\n".join(plan_lines),
                            "tool": "agent.planner",
                            "step_id": f"agent-plan-{uuid.uuid4().hex[:8]}",
                        },
                    }
                    # -- batch with realtime progress queue pumping --
                    _batch_timeout = _tool_timeout()
                    _progress_queue: asyncio.Queue = asyncio.Queue()
                    loop_state["_progress_queue"] = _progress_queue
                    _batch_task = asyncio.ensure_future(
                        _run_steps_via_subagent(
                            db, user, exec_steps,
                            conversation_id=conversation_id,
                            attachment_session_id=attachment_session_id,
                            user_message=user_message,
                            loop_state=loop_state,
                            timeout=_batch_timeout,
                        )
                    )
                    _start_ts = time.monotonic()
                    while not _batch_task.done():
                        _elapsed = time.monotonic() - _start_ts
                        if _elapsed > _batch_timeout:
                            _batch_task.cancel()
                            batch_text = json.dumps({
                                "ok": False, "summary": f"批量执行超时（{_batch_timeout} 秒）",
                                "step_results": [],
                            }, ensure_ascii=False)
                            _batch_task = None
                            break
                        _get_task = asyncio.ensure_future(_progress_queue.get())
                        _done, _pending = await asyncio.wait(
                            [_batch_task, _get_task],
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=5.0,
                        )
                        if _batch_task in _done:
                            _get_task.cancel()
                            break
                        if _get_task in _done:
                            _ev = _get_task.result()
                            if isinstance(_ev, dict) and _ev.get("phase") in (
                                "tool_call", "tool_result",
                            ):
                                tid = str(_ev.get("tool_call_id") or _ev.get("step_id") or "")
                                if tid:
                                    _batch_streamed_tool_ids.add(tid)
                                tname = str(_ev.get("tool_name") or "")
                                if tname:
                                    _batch_streamed_tool_ids.add(f"name:{tname}")
                            yield {"type": "workflow", "data": _ev}
                            continue
                        _get_task.cancel()
                        _hb_detail = _progress_heartbeat_detail(
                            loop_state,
                            _plan_summary or f"执行 {len(exec_steps)} 个步骤",
                        )
                        _parse = loop_state.get("_url_parse_state")
                        if isinstance(_parse, dict) and _parse.get("urls"):
                            yield {"type": "workflow", "data": {
                                "phase": "url_parse_progress",
                                "title": "执行中",
                                "detail": _hb_detail,
                                "tool": "subagent.batch",
                                "tool_name": "web_search",
                                "step_id": f"batch-hb-{uuid.uuid4().hex[:8]}",
                                "urls": _parse.get("urls"),
                                "done": _parse.get("done"),
                                "total": _parse.get("total"),
                                "current_url": _parse.get("current_url") or "",
                            }}
                        else:
                            yield {"type": "workflow", "data": {
                                "phase": "orchestrator_progress",
                                "title": "执行中",
                                "detail": _hb_detail,
                                "tool": "subagent.batch",
                                "step_id": f"batch-hb-{uuid.uuid4().hex[:8]}",
                            }}
                    if _batch_task is not None:
                        batch_text = _batch_task.result()
                    while not _progress_queue.empty():
                        try:
                            _ev = _progress_queue.get_nowait()
                            if isinstance(_ev, dict) and _ev.get("phase") in (
                                "tool_call", "tool_result",
                            ):
                                tname = str(_ev.get("tool_name") or "")
                                if tname:
                                    _batch_streamed_tool_ids.add(f"name:{tname}")
                            yield {"type": "workflow", "data": _ev}
                        except asyncio.QueueEmpty:
                            break
                    loop_state.pop("_progress_queue", None)
                    try:
                        body = json.loads(batch_text)
                        for sr in body.get("step_results") or []:
                            _batch_results[str(sr.get("tool_call_id") or "")] = sr
                    except (json.JSONDecodeError, TypeError):
                        pass
                    loop_state["_batch_streamed_tool_ids"] = _batch_streamed_tool_ids

                for tc in tool_calls:
                    fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                    tool_name = str(fn.get("name") or "")
                    tool_id = str(tc.get("id") or uuid.uuid4())
                    raw_args = fn.get("arguments") or "{}"
                    step_id = f"agent-tool-{uuid.uuid4().hex[:8]}"
                    try:
                        meta = tool_workflow_meta(tool_name, raw_args)
                    except Exception:
                        meta = {
                            "title": tool_name, "result_title": tool_name,
                            "failure_title": f"{tool_name}（失败）",
                            "detail": "", "tool": tool_name,
                        }

                    # ── Human-in-the-Loop: 用户确认检查 ──
                    if is_confirmation_required(tool_name) and not loop_state.get("_hitl_confirmed"):
                        confirmation_id = generate_confirmation_id()
                        raw_params = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip().startswith("{") else (raw_args or {})
                        checkpoint_id = generate_checkpoint_id()

                        # 保存完整 checkpoint 到 Redis（24h TTL）
                        ckpt_saved = save_checkpoint(
                            checkpoint_id,
                            user_id=str(user.id),
                            phase="awaiting_confirmation",
                            loop_state=loop_state,
                            working=working,
                            pending_data={
                                "confirmation_id": confirmation_id,
                                "tool_name": tool_name,
                                "params_json": json.dumps(raw_params, ensure_ascii=False) if raw_params else "{}",
                                "title": meta.get("title") or tool_name,
                            },
                            tool_call=_build_checkpoint_pending_tool(tool_name, tool_id, raw_args, step_id, meta),
                        )
                        stored = set_pending_confirmation(confirmation_id, {
                            "user_id": str(user.id),
                            "tool_name": tool_name,
                            "params_json": json.dumps(raw_params, ensure_ascii=False) if raw_params else "{}",
                            "checkpoint_id": checkpoint_id,
                        })
                        if stored and ckpt_saved:
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "confirmation_required",
                                    "confirmation_id": confirmation_id,
                                    "checkpoint_id": checkpoint_id,
                                    "tool": meta.get("tool") or tool_name,
                                    "tool_name": tool_name,
                                    "title": meta.get("title") or tool_name,
                                    "detail": build_confirmation_summary(tool_name, raw_params),
                                    "step_id": step_id,
                                },
                            }
                            sess.release_before_io()
                            accepted_resp = await _hitl_poll(lambda: get_confirm_response(confirmation_id))

                            if accepted_resp is None:
                                # 超时 → 进入 suspended 状态，checkpoint 保留在 Redis
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "workflow_finished",
                                        "status": "suspended",
                                        "checkpoint_id": checkpoint_id,
                                        "title": "等待用户确认",
                                    },
                                }
                                loop_state["_checkpoint_suspended"] = checkpoint_id
                                return  # 退出生成器，SSE 流正常结束

                            clear_pending_confirmation(confirmation_id)
                            clear_checkpoint(checkpoint_id)

                            accepted = accepted_resp == "accepted"
                            if not accepted:
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "tool_result",
                                        "title": f"已取消：{meta.get('title') or tool_name}",
                                        "detail": "用户已拒绝此操作",
                                        "tool": meta.get("tool") or tool_name,
                                        "tool_name": tool_name,
                                        "step_id": step_id,
                                        "status": "rejected",
                                    },
                                }
                                continue
                            loop_state["_hitl_confirmed"] = True

                    # ── Human-in-the-Loop: 方案选择 ──
                    if tool_name == "ask_user_choice":
                        raw_params = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip().startswith("{") else (raw_args or {})
                        question = str(raw_params.get("question") or "")
                        options = raw_params.get("options") or []
                        choice_id = generate_choice_id()
                        checkpoint_id = generate_checkpoint_id()

                        ckpt_saved = save_checkpoint(
                            checkpoint_id,
                            user_id=str(user.id),
                            phase="awaiting_choice",
                            loop_state=loop_state,
                            working=working,
                            pending_data={
                                "choice_id": choice_id,
                                "question": question,
                                "options": json.dumps(options, ensure_ascii=False),
                                "title": meta.get("title") or tool_name,
                            },
                            tool_call=_build_checkpoint_pending_tool(tool_name, tool_id, raw_args, step_id, meta),
                        )
                        stored = set_pending_choice(choice_id, {
                            "user_id": str(user.id),
                            "question": question,
                            "options": json.dumps(options, ensure_ascii=False),
                            "checkpoint_id": checkpoint_id,
                        })
                        if stored and ckpt_saved:
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "choice_required",
                                    "choice_id": choice_id,
                                    "checkpoint_id": checkpoint_id,
                                    "tool": meta.get("tool") or tool_name,
                                    "tool_name": tool_name,
                                    "title": meta.get("title") or tool_name,
                                    "question": question,
                                    "options": options,
                                    "step_id": step_id,
                                },
                            }
                            sess.release_before_io()
                            chosen_option = await _hitl_poll(lambda: get_choice_response(choice_id))

                            if chosen_option is None:
                                # 超时 → 进入 suspended 状态
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "workflow_finished",
                                        "status": "suspended",
                                        "checkpoint_id": checkpoint_id,
                                        "title": "等待用户选择",
                                    },
                                }
                                loop_state["_checkpoint_suspended"] = checkpoint_id
                                return

                            clear_pending_choice(choice_id)
                            clear_checkpoint(checkpoint_id)

                            result_text = json.dumps({
                                "ok": True,
                                "summary": f"用户选择了：{chosen_option}",
                                "data": {"choice": chosen_option},
                            }, ensure_ascii=False)
                            ok = True
                            summary = f"用户选择了：{chosen_option}"
                        else:
                            result_text = json.dumps({
                                "ok": False,
                                "summary": "方案选择服务不可用",
                            }, ensure_ascii=False)
                            ok = False
                            summary = "方案选择服务不可用"
                        record_executed_tool_call(
                            loop_state,
                            tool_name=tool_name,
                            raw_args=raw_args,
                            result_text=result_text,
                            summary=summary or ("完成" if ok else "失败"),
                            step_id=step_id,
                        )
                        yield {
                            "type": "workflow",
                            "data": {
                                "phase": "tool_result",
                                "title": _workflow_result_title(meta, ok=ok),
                                "detail": summary or "",
                                "tool": meta.get("tool") or tool_name,
                                "tool_name": tool_name,
                                "step_id": step_id,
                                "status": "done" if ok else "failed",
                            },
                        }
                        working.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": compress_tool_result_for_loop(result_text),
                            }
                        )
                        continue

                    cached_result = lookup_cached_tool_result(loop_state, tool_name, raw_args)
                    # 解析参数用于 callDetail 展示（人类可读）
                    try:
                        parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                        call_detail_str = _human_tool_call_detail(tool_name, parsed_args)
                    except Exception:
                        call_detail_str = ""

                    # 批量子智能体进度流已推送过同名工具事件时，不再重复展示 tool_call
                    _already_streamed = (
                        f"name:{tool_name}" in (loop_state.get("_batch_streamed_tool_ids") or set())
                        or tool_id in (loop_state.get("_batch_streamed_tool_ids") or set())
                    )

                    if cached_result is not None:
                        result_text = cached_result
                        ok, summary = _parse_tool_summary(result_text)
                        summary = summary or "复用本轮已执行结果"
                        original_detail = meta.get("detail") or ""
                        cached_detail = f"{original_detail}（使用缓存结果）" if original_detail else "复用本轮对话已有结果"
                        if not _already_streamed:
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "tool_call",
                                    "title": meta["title"],
                                    "detail": cached_detail,
                                    "callDetail": call_detail_str,
                                    "tool": meta.get("tool") or tool_name,
                                    "tool_name": tool_name,
                                    "step_id": step_id,
                                },
                            }
                    else:
                        if not _already_streamed:
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "tool_call",
                                    "title": meta["title"],
                                    "detail": meta.get("detail") or "",
                                    "callDetail": call_detail_str,
                                    "tool": meta.get("tool") or tool_name,
                                    "tool_name": tool_name,
                                    "step_id": step_id,
                                },
                            }
                        # ── 断路器：同一工具连续失败 N 次后在本轮对话中禁用 ──
                        tool_fails: dict[str, int] = loop_state.get("_tool_failure_counts") or {}
                        if tool_fails.get(tool_name, 0) >= 3:
                            result_text = json.dumps({
                                "ok": False,
                                "summary": f"工具 {tool_name} 连续失败 3 次，"
                                           "本次对话中已禁用。请尝试换用其他工具或直接回答。",
                            }, ensure_ascii=False)
                        else:
                            timeout = _tool_timeout()
                            try:
                                # ── 工具执行拦截 ──────────────────────────────────
                                # 父编排：非直调工具透明路由到子智能体（kind=execute）
                                # 专精 / 子 Agent：本域直执
                                if _should_delegate_to_subagent(loop_state, tool_name):
                                    sr = _batch_results.get(tool_id, {})
                                    result_text = sr.get("raw") or json.dumps(
                                        {"ok": False, "summary": "批量执行未返回该步骤结果"},
                                        ensure_ascii=False,
                                    )
                                else:
                                    # 直执工具（含 invoke_context_subagent / web_search 等）统一泵送进度
                                    hb_title = (
                                        "子任务执行中"
                                        if tool_name == "invoke_context_subagent"
                                        else (meta.get("title") or tool_name or "执行中")
                                    )
                                    result_text = ""
                                    async for _pev in _iter_execute_with_progress(
                                        execute_agent_tool(
                                            db,
                                            user,
                                            tool_name=tool_name,
                                            arguments=raw_args,
                                            conversation_id=conversation_id,
                                            attachment_session_id=attachment_session_id,
                                            user_message=user_message,
                                            loop_state=loop_state,
                                        ),
                                        loop_state,
                                        timeout=float(timeout),
                                        heartbeat_title=str(hb_title)[:80],
                                        heartbeat_tool=(
                                            "subagent.execute"
                                            if tool_name == "invoke_context_subagent"
                                            else (meta.get("tool") or tool_name)
                                        ),
                                    ):
                                        if _pev.get("type") == "__result__":
                                            result_text = str(_pev.get("text") or "")
                                        else:
                                            yield _pev
                            except asyncio.TimeoutError:
                                _logger.warning(
                                    "工具执行超时 tool=%s timeout=%ss",
                                    tool_name, timeout,
                                )
                                result_text = json.dumps(
                                    {"ok": False, "summary": f"工具执行超时（{timeout} 秒）"},
                                    ensure_ascii=False,
                                )
                            except Exception as exc:
                                _logger.exception("工具执行异常 tool=%s", tool_name)
                                result_text = json.dumps(
                                    {"ok": False, "summary": f"工具执行异常：{exc}"},
                                    ensure_ascii=False,
                                )
                            ok, summary = _parse_tool_summary(result_text)
                            # ── 自动重试：临时故障（超时/网络/数据库）立即重试一次 ──
                            if not ok and _is_retryable_error(result_text):
                                yield {
                                    "type": "workflow",
                                    "data": {
                                        "phase": "tool_call",
                                        "title": f"{meta['title']}（重试）",
                                        "detail": "临时故障，自动重试一次",
                                        "tool": meta.get("tool") or tool_name,
                                        "tool_name": tool_name,
                                        "step_id": f"{step_id}-retry",
                                    },
                                }
                                try:
                                    if _should_delegate_to_subagent(loop_state, tool_name):
                                        # 重试时直接用子Agent重新执行（batch 结果是已缓存失败的）
                                        result_text = await _run_tool_via_subagent(
                                            db, user, tool_name, raw_args,
                                            conversation_id=conversation_id,
                                            attachment_session_id=attachment_session_id,
                                            user_message=user_message,
                                            loop_state=loop_state,
                                            timeout=timeout,
                                        )
                                    else:
                                        result_text = await asyncio.wait_for(
                                            execute_agent_tool(
                                                db,
                                                user,
                                                tool_name=tool_name,
                                                arguments=raw_args,
                                                conversation_id=conversation_id,
                                                attachment_session_id=attachment_session_id,
                                                user_message=user_message,
                                                loop_state=loop_state,
                                            ),
                                            timeout=timeout,
                                        )
                                except asyncio.TimeoutError:
                                    result_text = json.dumps(
                                        {"ok": False, "summary": f"工具执行超时（{timeout} 秒）"},
                                        ensure_ascii=False,
                                    )
                                except Exception as exc:
                                    result_text = json.dumps(
                                        {"ok": False, "summary": f"工具执行异常：{exc}"},
                                        ensure_ascii=False,
                                    )
                            # ── 追踪失败计数（仅对本次实际执行计数） ──
                            ok2, _ = _parse_tool_summary(result_text)
                            if not ok2:
                                tool_fails[tool_name] = tool_fails.get(tool_name, 0) + 1
                                loop_state["_tool_failure_counts"] = tool_fails
                            else:
                                # 成功后重置计数，允许工具继续使用
                                tool_fails.pop(tool_name, None)
                        ok, summary = _parse_tool_summary(result_text)
                        record_executed_tool_call(
                            loop_state,
                            tool_name=tool_name,
                            raw_args=raw_args,
                            result_text=result_text,
                            summary=summary or ("完成" if ok else "失败"),
                            step_id=step_id,
                        )
                    from app.services.agent_admin_reply import (
                        capture_admin_list_deterministic_reply,
                    )

                    capture_admin_list_deterministic_reply(
                        db,
                        tool_name=tool_name,
                        result_text=result_text,
                        loop_state=loop_state,
                    )
                    if (
                        ok
                        and tool_name == ATOMIC_TOOL_KG_QUERY
                        and loop_state.get("kg_context")
                    ):
                        from app.services.kg_service import (
                            try_department_members_deterministic_reply,
                        )

                        if not loop_state.get("deterministic_reply"):
                            dept_reply = try_department_members_deterministic_reply(
                                db, user, user_message
                            )
                            if dept_reply:
                                loop_state["deterministic_reply"] = dept_reply
                            else:
                                kg_ctx = loop_state["kg_context"]
                                ctx_text = str(
                                    getattr(kg_ctx, "context_text", None)
                                    or (
                                        kg_ctx.get("context_text")
                                        if isinstance(kg_ctx, dict)
                                        else ""
                                    )
                                    or ""
                                ).strip()
                                if ctx_text:
                                    loop_state["deterministic_reply"] = ctx_text
                    outcome_lines = list(loop_state.get("tool_outcome_lines") or [])
                    if cached_result is None:
                        outcome_lines.append(
                            f"{meta.get('title') or tool_name}：{summary or ('完成' if ok else '失败')}"
                        )
                        loop_state["tool_outcome_lines"] = outcome_lines[-12:]
                    try:
                        result_text_parsed = json.loads(result_text) if isinstance(result_text, str) else {}
                        result_detail_str = str(result_text_parsed.get("summary") or "")[:400]
                    except Exception:
                        result_detail_str = str(result_text or "")[:400]
                    result_data = {
                        "phase": "tool_result",
                        "title": _workflow_result_title(meta, ok=ok),
                        "detail": summary or "",
                        "resultDetail": result_detail_str,
                        "tool": meta.get("tool") or tool_name,
                        "tool_name": tool_name,
                        "step_id": step_id,
                        "status": "done" if ok else "failed",
                    }
                    boost_seconds = meta.get("boost_seconds")
                    if boost_seconds is None and ok and result_text:
                        try:
                            body = json.loads(result_text)
                            if isinstance(body, dict):
                                outer = body.get("data")
                                if isinstance(outer, dict):
                                    inner = outer.get("data") if isinstance(outer.get("data"), dict) else outer
                                    bs = inner.get("boost_seconds")
                                    if bs is not None:
                                        boost_seconds = str(int(bs))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass
                    if boost_seconds is not None:
                        result_data["boost_seconds"] = str(int(boost_seconds))
                    # 批量子智能体进度流已推送过同工具事件时，不再重复推送（含 boost），避免前端双提醒
                    if not _already_streamed:
                        yield {
                            "type": "workflow",
                            "data": result_data,
                        }

                    # 发射子智能体内部工具调用步骤事件（工具输入参数 + 输出结果）
                    # 使子智能体（search/use/execute 等）的每一步在前台可见
                    _child_steps = loop_state.pop("subagent_executed_steps", None)
                    if _child_steps and tool_name in (
                        "invoke_context_subagent", "invoke_skill",
                    ):
                        for _cs in _child_steps:
                            _cs_tool = _cs.get("tool_name", "")
                            _cs_args_raw = _cs.get("args_preview", "")
                            _cs_summary = _cs.get("summary", "")
                            _cs_id = _cs.get("step_id", "") or uuid.uuid4().hex[:8]
                            # 将存储的 JSON args 转为人类可读文本
                            try:
                                _cs_parsed = json.loads(_cs_args_raw) if isinstance(_cs_args_raw, str) else {}
                            except (json.JSONDecodeError, TypeError):
                                _cs_parsed = {}
                            _cs_detail = _human_tool_call_detail(_cs_tool, _cs_parsed)
                            # web_search 显示为"搜索"而非技术名
                            if _cs_tool == "web_search":
                                _call_title = _cs_detail or "搜索"
                                _call_tool_key = "web.search"
                            else:
                                _call_title = f"子智能体 · {(_cs_detail or _cs_tool)}"
                                _call_tool_key = _cs_tool
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "tool_call",
                                    "title": _call_title,
                                    "detail": _cs_detail,
                                    "callDetail": _cs_detail,
                                    "tool": _call_tool_key,
                                    "tool_name": _cs_tool,
                                    "step_id": f"sub-{_cs_id}",
                                },
                            }
                            yield {
                                "type": "workflow",
                                "data": {
                                    "phase": "tool_result",
                                    "title": f"{_call_title} 完成",
                                    "detail": _cs_summary[:200] or "完成",
                                    "resultDetail": (_cs_summary or "")[:400],
                                    "tool": _call_tool_key,
                                    "tool_name": _cs_tool,
                                    "step_id": f"sub-{_cs_id}",
                                    "status": "done" if _cs_summary else "failed",
                                },
                            }

                    working.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": compress_tool_result_for_loop(result_text),
                        }
                    )
                    for att in list(loop_state.get("stream_attachments") or []):
                        _mark_streamed_attachment(loop_state, att)
                        yield {"type": "attachment", "data": att}
                    loop_state["stream_attachments"] = []
                if loop_state.get("orchestrator_assist_request"):
                    break
                if not execution_goal_satisfied(
                    execution_plan,
                    loop_state,
                    user_message,
                    plan_has_script=plan_has_script,
                ):
                    working.append(
                        {
                            "role": "system",
                            "content": build_skill_management_continue_nudge(
                                user_message, loop_state
                            ),
                        }
                    )
                    continue
                break

            if content:
                working.append({"role": "assistant", "content": content})

            has_outcomes = bool(
                loop_state.get("tool_outcome_lines")
                or loop_state.get("last_skill_conclusion")
            )
            # 已有工具结果 → 结束本轮工具循环，交给终稿综合（禁止把正文/工具清单当答案）
            if has_outcomes and not tool_calls:
                break

            # 无工具结果时：仅指令型技能 / 无可调用工具的 direct_answer 可直接交付
            if (
                content
                and not tool_calls
                and not has_outcomes
                and execution_plan.direct_answer
                and (instruction_only_skill or not tool_specs)
                and assistant_content_is_deliverable(
                    content, instruction_only_skill=instruction_only_skill
                )
            ):
                deliverable_reply = content.strip()
                for ev in _emit_report_reply_deltas(deliverable_reply):
                    yield ev
                delivered = list(loop_state.get("delivered_parts") or [])
                delivered.append(deliverable_reply)
                loop_state["delivered_parts"] = delivered
                break

            # 有可用工具但未调用 → nudge，禁止空口承诺结束
            _raw_content = str((choice.get("message") or {}).get("content") or "")
            if not _raw_content:
                break
            if not tool_specs:
                break
            current_nudges = int(loop_state.get("content_only_nudges") or 0)
            max_nudges = 5
            if current_nudges >= max_nudges:
                # 催促耗尽：不接受未经验证的正文，进入综合/兜底
                break
            loop_state["content_only_nudges"] = current_nudges + 1
            if current_nudges >= max_nudges - 2:
                nudge = (
                    "【系统警告】你已多次未调用工具。再次警告：必须通过 tool_calls "
                    "执行操作并拿到真实结果后再回答。如再次输出文字而不调用工具，"
                    "系统将强制标记本次执行为失败。"
                )
            elif "uploaded_skill" in nudge_cache:
                nudge = nudge_cache["uploaded_skill"]
            elif "browser" in nudge_cache:
                nudge = nudge_cache["browser"]
            elif "platform" in nudge_cache:
                nudge = nudge_cache["platform"]
            else:
                nudge = nudge_cache["instruction"]
            working.append({"role": "system", "content": nudge})
            continue

        if deliverable_reply:
            if instruction_only_skill:
                # 指令型技能（如 mermaid-diagram）的正文输出即为完整交付
                break
            # LLM 在本次推理中选择了输出正文而不调用任何工具，
            # 这意味着 LLM 认为答复已完整。无需自适应重规划。
            break

        if execution_goal_satisfied(
            execution_plan,
            loop_state,
            user_message,
            plan_has_script=plan_has_script,
        ):
            break

        from app.services.agent_skill_router import (
            MERMAID_DIAGRAM_SKILL,
            is_diagram_generation_message,
        )

        # 绘图：统一闭包补调 mermaid_diagram（不依赖模型是否主动点名）
        if (
            execution_plan.intent == "生成图表"
            or is_diagram_generation_message(user_message)
            or str(execution_plan.uploaded_skill or "") == MERMAID_DIAGRAM_SKILL
        ):
            closure_step = f"agent-closure-mermaid-{uuid.uuid4().hex[:8]}"
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thinking",
                    "title": "生成图表",
                    "detail": "mermaid_diagram",
                    "tool": "agent.closure",
                    "step_id": closure_step,
                },
            }
            sess.release_before_io()
            _ok, _summary = await auto_execute_mermaid_diagram(
                db,
                user,
                user_message=user_message,
                loop_state=loop_state,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
            )
            db, user = sess.open()
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "图表已生成" if _ok else "图表生成失败",
                    "detail": _summary[:200] if _summary else "",
                    "tool": "agent.closure",
                    "step_id": closure_step,
                    "status": "done" if _ok else "failed",
                },
            }
            if execution_goal_satisfied(
                execution_plan,
                loop_state,
                user_message,
                plan_has_script=plan_has_script,
            ):
                break

        skill = resolve_target_uploaded_skill(
            execution_plan=execution_plan,
            loop_state=loop_state,
            user_message=user_message,
            chat_history=chat_history,
            uploaded_names=all_skill_names,
        )
        if skill == MERMAID_DIAGRAM_SKILL:
            # 已由上方 mermaid 闭包处理
            pass
        elif skill and plan_has_script is not False:
            closure_step = f"agent-closure-{uuid.uuid4().hex[:8]}"
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thinking",
                    "title": "自动执行技能",
                    "detail": skill,
                    "tool": "agent.closure",
                    "step_id": closure_step,
                },
            }
            sess.release_before_io()
            _ok, _summary = await auto_execute_uploaded_skill(
                db,
                user,
                skill_name=skill,
                user_message=user_message,
                chat_history=chat_history,
                loop_state=loop_state,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
            )
            db, user = sess.open()
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "技能执行完成" if _ok else "技能执行未获有效数据",
                    "detail": _summary[:200] if _summary else "",
                    "tool": "agent.closure",
                    "step_id": closure_step,
                    "status": "done" if _ok else "failed",
                },
            }
            if execution_goal_satisfied(
                execution_plan,
                loop_state,
                user_message,
                plan_has_script=plan_has_script,
            ):
                break

    sess.release_before_io()
    db, user = sess.open()
    await _maybe_auto_browser_screenshot(
        db,
        user,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        loop_state=loop_state,
        user_message=user_message,
    )
    for att in _pending_screenshot_attachments(loop_state):
        yield {"type": "attachment", "data": att}

    if deliverable_reply or loop_state.get("delivered_parts"):
        parts = list(loop_state.get("delivered_parts") or [])
        if deliverable_reply and (
            not parts or parts[-1] != deliverable_reply
        ):
            parts.append(deliverable_reply)
        combined = "\n\n".join(p.strip() for p in parts if p.strip())
        if combined:
            async for ev in _emit_direct_reply_complete(
                loop_id, combined, working, loop_state,
            ):
                yield ev
            return

    if task_mode:
        async for ev in _emit_task_handoff_complete(
            sess, db, user, loop_id, loop_state, working,
            user_message=user_message, conversation_id=conversation_id,
            task_id=task_id, agent_id=agent_id,
        ):
            yield ev
        return

    # 六相循环 — 阶段 2→6：记忆更新 + 最终回复综合
    async for ev in emit_final_user_reply(
        sess, uid, loop_id, user_message, working, loop_state,
        chat_history=chat_history,
    ):
        yield ev


# ═══════════════════════════════════════════════════════════════
# 子智能体单步执行 — 由父智能体（Supervisor）循环驱动
# ═══════════════════════════════════════════════════════════════

_CONTENT_ONLY_MAX_NUDGES = 3


def _build_content_only_nudge(
    user_message: str,
    loop_state: dict,
    tool_names: list[str] | None = None,
) -> str:
    """构建内容输出提醒：LLM 只输出了文字但没有调用任何工具。"""
    current = int(loop_state.get("content_only_nudges") or 0)
    remaining = _CONTENT_ONLY_MAX_NUDGES - current
    if remaining <= 1:
        return (
            "【系统警告】你已连续多次只输出文字而未调用任何工具。"
            "最后一次机会：必须通过 tool_calls 执行操作获取真实数据后再回答。"
            "禁止先承诺再去做——如果真的需要工具，现在就调用。"
        )
    parts = ["【系统提示】你必须通过 tool_calls 执行操作并拿到真实结果后再回答。"]
    if tool_names:
        tool_hint = "、".join(tool_names[:6])
        parts.append(f"可用工具包括 {tool_hint} 等。")
    parts.append("不要只输出文字承诺或解释——请直接调用工具，或者直接回答。")
    return "".join(parts)


def _exec_has_outcomes(loop_state: dict) -> bool:
    """检测本轮是否有工具执行结果。"""
    return bool(
        loop_state.get("tool_outcome_lines")
        or loop_state.get("last_skill_conclusion")
    )


def _step_complete_payload(
    working: list[dict],
    loop_state: dict,
    *,
    has_tool_calls: bool,
    needs_more_rounds: bool,
    reply: str | None,
    orchestrator_assist_request: Any = None,
    _all_tool_specs: list[dict] | None = None,
    _execution_plan: Any = None,
    _plan_has_script: bool | None = None,
) -> dict:
    """构造 step_complete 事件负载，供 supervisor 判断下一轮。"""
    payload: dict = {
        "type": "step_complete",
        "working": working,
        "loop_state": loop_state,
        "has_tool_calls": has_tool_calls,
        "needs_more_rounds": needs_more_rounds,
        "reply": reply,
        "orchestrator_assist_request": orchestrator_assist_request,
    }
    if _all_tool_specs is not None:
        payload["_all_tool_specs"] = _all_tool_specs
    if _execution_plan is not None:
        payload["_execution_plan"] = _execution_plan
    if _plan_has_script is not None:
        payload["_plan_has_script"] = _plan_has_script
    return payload


async def _exec_one_tool_round(
    sess: AgentLoopSession,
    db: Session,
    user: User,
    working: list[dict],
    loop_state: dict,
    all_tool_specs: list[dict],
    execution_plan: AgentExecutionPlan,
    user_message: str,
    conversation_id: str | None,
    attachment_session_id: str | None,
    agent_id: str | None,
    plan_has_script: bool | None,
) -> AsyncIterator[dict]:
    """子智能体单轮：LLM 调用 + 工具执行 + 事件产出。

    产出 workflow/delta 事件流，最后 yield 一个 type=step_complete 标记
    供父智能体（Supervisor）判断是否需要继续下一轮。
    """
    from app.services.agent_tool_search import select_visible_tool_specs

    # ── 1. 构建 LLM messages ──
    planned_specs = filter_tool_specs_by_plan(all_tool_specs, execution_plan)
    aid = str(loop_state.get("agent_id") or "").strip() or None
    tool_specs = select_visible_tool_specs(planned_specs, agent_id=aid)

    llm_messages = trim_agent_loop_messages(
        inject_retrieval_context_message(working, loop_state),
        keep_full_tool_results=1,
    )
    if tool_specs:
        llm_messages.append({
            "role": "system",
            "content": (
                "【系统提示】优先使用可用的工具和技能来满足用户请求。"
                "如果确实没有任何可用的工具或技能能完成用户的请求，"
                "直接告知用户你暂时无法完成，不要调用不相关的工具。"
            ),
        })

    # ── 2. LLM 调用 ──
    sess.release_before_io()
    choice = None
    _llm_t0 = time.monotonic()
    async for ev in chat_completion_stream_choice(
        messages=llm_messages,
        tools=tool_specs or None,
        temperature=0.3,
    ):
        if ev["type"] == "delta":
            yield {
                "type": "workflow",
                "data": {"phase": "thinking_delta", "delta": ev["text"]},
            }
        elif ev["type"] == "choice":
            choice = ev
    _llm_elapsed = time.monotonic() - _llm_t0
    db, user = sess.open()
    if not choice:
        _logger.info("LLM call empty choice in %.1fs agent=%s", _llm_elapsed, agent_id)
        yield _step_complete_payload(working, loop_state, has_tool_calls=False,
                                      needs_more_rounds=False, reply=None,
                                      _all_tool_specs=all_tool_specs,
                                      _execution_plan=execution_plan,
                                      _plan_has_script=plan_has_script)
        return

    message = normalize_llm_assistant_message(choice.get("message") or {})
    tool_calls = message.get("tool_calls") or []
    content = strip_dsml_markup(str(message.get("content") or "")).strip()

    # ── 3. 无 tool_calls → 由父层决定是否继续 / 综合 ──
    if not tool_calls:
        if content:
            working.append({"role": "assistant", "content": content})

        # 3a. 已有工具结果 → 本步结束，父智能体负责综合终稿（子智能体不写用户答案）
        if _exec_has_outcomes(loop_state):
            yield _step_complete_payload(working, loop_state, has_tool_calls=False,
                                          needs_more_rounds=False, reply=None,
                                          _all_tool_specs=all_tool_specs,
                                          _execution_plan=execution_plan,
                                          _plan_has_script=plan_has_script)
            return

        # 3b. 有可用工具但未调用 → 继续催促 tool_calls（禁止空口承诺当完成）
        if tool_specs:
            current_nudges = int(loop_state.get("content_only_nudges") or 0)
            if current_nudges < _CONTENT_ONLY_MAX_NUDGES:
                loop_state["content_only_nudges"] = current_nudges + 1
                tool_names = sorted(set(
                    (s.get("function") or {}).get("name", "")
                    for s in tool_specs if isinstance(s, dict)
                ))
                nudge = _build_content_only_nudge(
                    user_message, loop_state, tool_names=tool_names
                )
                working.append({"role": "system", "content": nudge})
                yield _step_complete_payload(working, loop_state, has_tool_calls=False,
                                              needs_more_rounds=True, reply=None,
                                              _all_tool_specs=all_tool_specs,
                                              _execution_plan=execution_plan,
                                              _plan_has_script=plan_has_script)
                return
            # 催促耗尽仍未调工具：不得把 LLM 正文当完成态（可能编造成功）
            yield _step_complete_payload(working, loop_state, has_tool_calls=False,
                                          needs_more_rounds=False, reply=None,
                                          _all_tool_specs=all_tool_specs,
                                          _execution_plan=execution_plan,
                                          _plan_has_script=plan_has_script)
            return

        # 3c. 无可用工具 → 纯文本可直接作为回答
        yield _step_complete_payload(working, loop_state, has_tool_calls=False,
                                      needs_more_rounds=False, reply=content or None,
                                      _all_tool_specs=all_tool_specs,
                                      _execution_plan=execution_plan,
                                      _plan_has_script=plan_has_script)
        return

    # ── 4. 有 tool_calls → 执行工具 ──
    working.append(message)

    # 4a. 父编排非直调工具：批量交给子智能体；专精本域工具走 4b 直执
    exec_steps: list[dict] = []
    for tc in tool_calls:
        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
        tn = str(fn.get("name") or "")
        if _should_delegate_to_subagent(loop_state, tn):
            raw_args = fn.get("arguments") or "{}"
            try:
                parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except (json.JSONDecodeError, TypeError):
                parsed = {}
            exec_steps.append({
                "tool": tn, "arguments": parsed,
                "tool_call_id": str(tc.get("id") or uuid.uuid4()),
            })

    assist_request = loop_state.get("orchestrator_assist_request") or None

    if exec_steps:
        plan_lines: list[str] = []
        for s in exec_steps:
            cd = _human_tool_call_detail(s["tool"], s["arguments"])
            plan_lines.append(f"  {len(plan_lines) + 1}. {cd or s['tool']}")
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_plan",
                "title": f"执行计划（{len(exec_steps)} 步）",
                "detail": "\n".join(plan_lines),
                "tool": "agent.planner",
                "step_id": f"agent-plan-{uuid.uuid4().hex[:8]}",
            },
        }
        _batch_timeout = _tool_timeout()
        _batch_task = asyncio.ensure_future(
            _run_steps_via_subagent(
                db, user, exec_steps,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                user_message=user_message,
                loop_state=loop_state,
                timeout=_batch_timeout,
            )
        )
        while not _batch_task.done():
            if time.monotonic() - _llm_t0 > _batch_timeout + 5:
                _batch_task.cancel()
                break
            await asyncio.sleep(0.1)

        if _batch_task.done() and not _batch_task.cancelled():
            batch_text = _batch_task.result()
        else:
            batch_text = json.dumps({
                "ok": False, "summary": f"批量执行超时（{_batch_timeout} 秒）",
                "step_results": [],
            }, ensure_ascii=False)

        try:
            body = json.loads(batch_text)
            outcome_lines = list(loop_state.get("tool_outcome_lines") or [])
            for sr in body.get("step_results") or []:
                summary = str(sr.get("summary", ""))[:200]
                if summary:
                    outcome_lines.append(summary)
                working.append({
                    "role": "tool",
                    "tool_call_id": str(sr.get("tool_call_id", "")),
                    "content": compress_tool_result_for_loop(sr.get("raw", batch_text)),
                })
            loop_state["tool_outcome_lines"] = outcome_lines[-12:]
        except (json.JSONDecodeError, TypeError):
            pass

    # 4b. 直执工具（父编排原语，或专精本域原子工具）
    for tc in tool_calls:
        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
        tool_name = str(fn.get("name") or "")
        if _should_delegate_to_subagent(loop_state, tool_name):
            continue
        tool_id = str(tc.get("id") or uuid.uuid4())
        raw_args = fn.get("arguments") or "{}"
        try:
            raw_params = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip().startswith("{") else (raw_args or {})
        except (json.JSONDecodeError, TypeError):
            raw_params = {}
        result_text = await execute_agent_tool(
            db, user,
            tool_name=tool_name,
            arguments=raw_params,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            user_message=user_message,
            loop_state=loop_state,
        )
        working.append({
            "role": "tool",
            "tool_call_id": tool_id,
            "content": compress_tool_result_for_loop(result_text),
        })
        if tool_name == "request_orchestrator_assist":
            assist_request = loop_state.get("orchestrator_assist_request") or True

    yield _step_complete_payload(working, loop_state, has_tool_calls=True,
                                  needs_more_rounds=True, reply=None,
                                  orchestrator_assist_request=assist_request,
                                  _all_tool_specs=all_tool_specs,
                                  _execution_plan=execution_plan,
                                  _plan_has_script=plan_has_script)
