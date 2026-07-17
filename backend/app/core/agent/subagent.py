"""独立上下文 Subagent — agentkit-subagent 平台适配。"""

from __future__ import annotations

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
        "explore": SubagentKindConfig(
            kind="explore",
            allowed_tools=frozenset({"invoke_skill", "run_tool_batch", "search_skills"}),
            system_contract=(
                "检索探索子 Agent（常为 skill-dev 调研）："
                "invoke_skill(web-search, search, {query})、"
                "invoke_skill(knowledge-search, retrieve, {query})、"
                "invoke_skill(kg, query_entities, {question})；"
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
        "deep_research": SubagentKindConfig(
            kind="deep_research",
            allowed_tools=frozenset({"web_search", "knowledge_retrieve"}),
            max_rounds=12,
            system_contract=(
                "你是一个深度研究子 Agent。你的任务是针对用户的问题进行多轮、多角度的互联网调研，"
                "生成结构化、有引用的研究报告。\n\n"
                "## 研究流程\n"
                "1. **分析问题**：理解用户问题的核心，拆解出需要调研的子主题。\n"
                "2. **生成搜索关键词**：根据子主题生成 2-4 个精准搜索词，依次调用 web_search 进行检索。"
                "先搜索宽泛的概述性关键词了解全貌，再根据结果深挖具体数据。\n"
                "3. **阅读全文**：调用 web_search 时设置 read_full=3~5，确保通过 FireCrawl 获取网页完整正文（Markdown）。\n"
                "4. **多维验证**：不同来源存在矛盾数据时，追加搜索做交叉验证。"
                "也可调用 knowledge_retrieve 检索内部知识库辅助核对。\n"
                "5. **发现归纳**：对已获取的全文内容进行跨源比对，提炼一致结论，标注矛盾点。\n\n"
                "## 输出要求\n"
                "返回包含以下部分的结构化研究报告：\n"
                "- **research_summary**：综合研究发现（2-3 句话概述）。\n"
                "- **key_findings**：关键发现列表，每条附 [n] 引用来源。\n"
                "- **data_comparison**：如有数据类信息（销量、价格等），用表格对比多源数据。\n"
                "- **conflicts**：注明多源之间的分歧或不确定信息。\n"
                "- **citations**：引用来源列表（标题 + URL）。\n\n"
                "## 约束\n"
                "- 禁止凭空编造数据，所有量化结论必须来自搜索结果的全文。\n"
                "- 如果首次搜索结果不足以作答，继续生成新的关键词深挖。\n"
                "- 优先使用联网信息，knowledge_retrieve 仅作内部辅助核对。\n"
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
    loop_state: LoopState | None = None,
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

    from app.agentkit.subagent.context import child_state_from_parent

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
