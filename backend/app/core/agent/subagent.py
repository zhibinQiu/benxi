"""独立上下文 Subagent — agentkit-subagent 平台适配。"""

from __future__ import annotations

import uuid
from typing import Any

from agentkit_subagent import (
    ExploreSkillStep,
    SubagentConfig,
    SubagentKindConfig,
    SubagentRuntime,
    execute_subagent,
)
from agentkit_subagent.loop import parse_tool_summary
from sqlalchemy.orm import Session

from app.core.agent_message_parse import normalize_llm_assistant_message, strip_dsml_markup
from app.core.agent_tool_context import append_retrieval_context, record_executed_tool_call
from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.models.org import User
from app.services.agent_tools import build_agent_tool_specs, execute_agent_tool

_PLATFORM_RUNTIME = SubagentRuntime(
    kinds={
        "explore": SubagentKindConfig(
            kind="explore",
            allowed_tools=frozenset({"invoke_skill", "run_tool_batch", "search_skills"}),
            system_contract=(
                "检索探索子 Agent（常为 skill-dev 调研）："
                "invoke_skill(web-search, search, {query})、"
                "invoke_skill(knowledge-search, retrieve, {query})、"
                "invoke_skill(kg-palantir, query_entities, {question})；"
                "或 run_tool_batch / search_skills。"
                "输出关键事实与材料局限的结构化摘要，勿写完整终稿。"
            ),
        ),
        "browser_digest": SubagentKindConfig(
            kind="browser_digest",
            allowed_tools=frozenset({"invoke_skill"}),
            system_contract=(
                "浏览器取证子 Agent（常为 skill-dev 页面结构调研）："
                "invoke_skill(browser-automation, call, "
                "{operation: browser_navigate|browser_snapshot|browser_screenshot|..., params})。"
                "摘要 URL、页面标题、关键字段与 DOM 结构线索，勿输出冗长 HTML。"
            ),
        ),
    },
    explore_steps=(
        ExploreSkillStep("web-search", "search", "query"),
        ExploreSkillStep("knowledge-search", "retrieve", "query"),
        ExploreSkillStep("kg-palantir", "query_entities", "question"),
    ),
)


async def execute_context_subagent(
    db: Session,
    user: User,
    *,
    kind: str,
    task: str = "",
    queries: list[str] | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    user_message: str = "",
    loop_state: dict[str, Any] | None = None,
    agent_id: str = "",
) -> str:
    loop_holder: dict[str, Any] = {"state": None}

    async def invoke_skill_step(
        child_state: dict[str, Any],
        skill_name: str,
        action: str,
        param_key: str,
        query: str,
    ) -> str:
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
        return summary if ok else ""

    async def llm_complete(messages, tool_specs):
        return await chat_completion_message_async(
            messages=messages,
            tools=tool_specs or None,
            temperature=0.2,
        )

    def build_tool_specs(allowed: set[str]):
        return build_agent_tool_specs(db, user, allowed_names=allowed)

    async def execute_tool(tool_name: str, raw_args: Any) -> str:
        state = loop_holder["state"]
        assert state is not None
        return await execute_agent_tool(
            db,
            user,
            tool_name=tool_name,
            arguments=raw_args,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            user_message=task or user_message,
            loop_state=state,
        )

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

    from agentkit_subagent.context import child_state_from_parent

    agent = agent_id or str((loop_state or {}).get("agent_id") or "")
    sub_kind = (kind or "").strip().lower()
    task_text = (task or user_message or "").strip()

    if sub_kind == "browser_digest":
        from app.integrations.browser_automation.browser_config import get_browser_rpa_config

        if not get_browser_rpa_config(db).enabled:
            sub_kind = "explore"
            if not queries and task_text:
                queries = [task_text]

    def init_child_state() -> dict[str, Any]:
        state = child_state_from_parent(loop_state, kind=sub_kind, agent_id=agent)
        loop_holder["state"] = state
        return state

    async def execute_tool_bound(tool_name: str, raw_args: Any) -> str:
        if loop_holder["state"] is None:
            init_child_state()
        return await execute_tool(tool_name, raw_args)

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

    return await execute_subagent(
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
