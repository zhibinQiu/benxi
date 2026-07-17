"""Agent 工具循环状态定义 — LangGraph 风格 State Schema。

loop_state 原为 ``dict[str, Any]`` 的自由字典，
本文件定义 ``LoopState(TypedDict, total=False)`` 让类型检查器、
IDE 补全和代码审查能识别所有 key 的类型。

迁移策略：
  1. 所有 ``loop_state: dict[str, Any]`` 类型标注逐步改为 ``loop_state: LoopState``
  2. 新增 key 时先在此文件中声明，再在业务代码中使用
  3. 不改动运行时行为（该 TypedDict 不用于校验，仅用于类型注解）
"""

from __future__ import annotations

from typing import Any, TypedDict


class LoopState(TypedDict, total=False):
    """Agent 工具循环执行状态 — LangGraph 风格 State Schema。

    所有字段均为 ``NotRequired``（约定等价于 ``total=False``），
    因为 loop_state 在执行过程中逐步积累字段，不要求初始化时全部提供。
    """

    # ── 初始字段（在 _iter_agent_tool_loop_body 入口初始化） ─────────────
    conversation_id: str | None
    """会话 ID，所有工具调用共享。"""
    attachment_session_id: str | None
    """附件会话 ID，用于临时附件访问。"""
    citations: list[dict[str, Any]]
    """收集到的引用来源列表，每项含 title/url/snippet 等。"""
    kg_context: Any
    """知识图谱查询返回的上下文对象 / dict。"""
    allowed_skill_names: set[str] | None
    """当前 Agent 可调用的 Skill 名集合，None 表示不限。"""
    _all_tool_specs: list[dict[str, Any]]
    """全部工具 spec（OpenAI function calling 格式），用于可见性筛选。"""
    scoped_doc_ids: list[str] | None
    """限定可操作的文档 ID 列表，None 表示不限。"""
    local_kb_disabled: bool
    """是否禁用本地知识库检索（如全局检索场景）。"""
    task_mode: bool
    """是否处于子任务模式（非最终输出，结果回传给调度层）。"""
    agent_id: str | None
    """当前 Agent 标识（platform/research/skill-dev 等），None 为主 Agent。"""
    auto_skill_creation: bool
    """是否为调度自动补能力发起的创建 Skill 流程。"""
    _tool_failure_counts: dict[str, int]
    """断路器：各工具在本轮对话中的连续失败次数。"""
    _execution_plan: Any
    """当前或最近一次的执行计划对象（AgentExecutionPlan）。"""

    # ── 执行过程中逐步积累 ──────────────────────────────────
    streamed_attachment_urls: set[str]
    """已通过 SSE attachment 事件流式下发的附件 URL 集合（去重用）。"""
    deterministic_reply: str | None
    """确定性回复（如部门成员列表格式化后原文），非空时直接用于回复。"""
    planned_uploaded_skill: str | None
    """本轮计划执行的上传 Skill 名称。"""
    expects_skill_data: bool
    """用户期望获取 Skill 执行后的结构化数据（而非仅文字回答）。"""
    _checkpoint_suspended: str | None
    """进入 suspended 状态的 checkpoint ID，用于前端恢复。"""
    _hitl_confirmed: bool
    """本轮是否已通过 HITL 确认（防重复弹确认框）。"""
    tool_outcome_lines: list[str]
    """已执行工具的摘要列表（供前端展示和最终回复合成）。"""
    stream_attachments: list[dict[str, Any]]
    """待流式下发的附件队列（主要浏览器截图）。"""
    delivered_parts: list[str]
    """已流式输出给用户的内容片段列表（用于最终合并）。"""
    content_only_nudges: int
    """本轮仅输出文字未调工具的 nudge 提醒次数。"""
    browser_session_used: bool
    """本轮是否使用了浏览器会话（用于补截图判断）。"""
    skill_dev_playbook_injected: bool
    """是否已注入 Skill 开发规范（仅 skill-dev Agent）。"""
    injected_skill_mds: list[str]
    """已注入到上下文的 SKILL.md 名称列表（去重）。"""
    agent_document_context: dict[str, Any] | None
    """当前 Agent 正在阅读的文档上下文（title + full_text）。"""
    pending_skill_md_inject: str | None
    """创建 Skill 后待注入到下一轮上下文的 SKILL.md 名称。"""
    created_uploaded_skills: list[str]
    """本轮对话中已创建的 Skill 名称列表。"""
    orchestrator_assist_request: dict[str, Any] | None
    """向调度层提交的协助请求（含 reason/needed_from/suggested_agent_id）。"""
    invoked_uploaded_skills: list[str]
    """本轮已通过 run_skill_script 执行的 Skill 名称列表。"""
    last_skill_conclusion: str | None
    """最近一次 Skill 脚本执行的结论摘要。"""
    retrieval_context_parts: list[str]
    """已注入到 system 消息中的检索材料片段列表。"""
    skill_explore_parts: list[str]
    """Skill 编写调研过程中收集的调研材料片段。"""
    skill_repair_attempts: int
    """当前 Skill 修复尝试的次数计数。"""
    pending_skill_repair: str | None
    """等待修复的 Skill 名称。"""
    skill_repair_parts: list[str]
    """Skill 修复上下文记录列表。"""
    executed_tool_calls: list[dict[str, Any]]
    """已执行工具调用记录（用于去重缓存和摘要）。"""
    executed_tool_cache: dict[str, str]
    """本轮已执行工具的去重缓存（fingerprint -> result_text）。"""
    task_deliverable: str | None
    """子任务模式下的最终可交付内容文本。"""
    subagent_summaries: list[dict[str, Any]]
    """子 Agent 执行结果摘要列表（汇总到父 Agent）。"""
    unlocked_tools: set[str]
    """通过 describe_tool / execution_plan 动态解锁的工具名集合。"""
    discovered_skill_routes: list[str]
    """通过 search_skills 发现的 Skill 路由描述。"""
    collected_attachments: list[dict[str, Any]]
    """已收集的附件信息列表（用于最终回复 Markdown 插入）。"""
    atomic_retrieval_queries: set[str]
    """已执行过的检索查询指纹集合（去重）。"""


__all__ = [
    "LoopState",
]
