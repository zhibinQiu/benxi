"""AI 智能体常驻层 — 短 prompt，细节交给 Skill 目录与专精块。"""

from __future__ import annotations

from app.core.agent_config import get_default_instruction_body
from app.core.platform_assistant import (
    assistant_ai_home_persona,
    assistant_conclusion_source_priority,
    assistant_search_strategy,
    assistant_user_communication_style,
    orchestrator_failure_communication_rule,
)
from app.core.session_chat_history import SESSION_CONTEXT_RULE

# 子任务专精：过程在 workflow 展示，正文由调度层最后汇总
_SPECIALIST_TASK_MODE = (
    "本子任务：只调用工具完成操作；回复仅供系统记录，勿写面向用户的完整总结。"
    "必须准确执行用户需求，不可偏离或遗漏。"
    "探索/试错细节勿写入回复，只返回可验收的结论或结构化结果。"
    "本域无法完成时调用 tool request_orchestrator_assist，reason 写明困难与需求，"
    "由调度层协助；勿直接调用其他专精。"
)

_USER_REPLY_RULE = (
    "必须准确理解并回应用户的问题与诉求，不可答非所问、偏离用户意图或只描述内部过程。"
)

_USER_STYLE_RULES = assistant_user_communication_style()

_TOOL_LOOP_REPLY_RULE = (
    "工具执行阶段：只发起 tool_calls，content 留空或一行内部状态；"
    "面向用户的最终结论由系统在工具结束后单独生成，你在本阶段写的正文不会展示给用户。"
)

_WRITE_RATE_RULES = (
    "外部 API 写操作：尽量批量写入，避免 for 循环逐条调用；遇 HTTP 429 等待 2–5 秒后重试（最多 3 次）。"
)

_GROUNDING_RULES = (
    assistant_conclusion_source_priority()
    + "\n事实约束：组织内部信息（用户/文档/数字/邮箱/部门/平台配置等）必须基于工具返回或检索"
    "片段，禁止编造。通用常识可直接用模型知识回答。信息不足时说明不确定之处。"
)

_SEARCH_STRATEGY_RULES = assistant_search_strategy()

_HUMAN_IN_THE_LOOP_RULES = (
    "当已有信息不足以做决策，或存在多种合理方案时，使用 ask_user_choice 工具让用户选择。"
    "适用场景举例：导出格式选择、分析时间范围、报告风格偏好、多方案择优等。"
    "不要替用户做不确定的决策——问清楚再继续。"
)

_SPECIALIST_SCOPE_RULE = (
    "你已是专精子 Agent：只在本域内自主规划与 tool_calls。"
    "本域无法完成时调用 tool request_orchestrator_assist，reason 写明你遇到了什么困难、"
    "需要什么帮助（如需要其他智能体协助的具体事项），"
    "由调度层重新分配或直接答复用户；"
    "收到调度交还的协助结果后继续完成本子任务。"
    "发展 Skill 的 playbook 见 available_skills；内置编排 Skill（如 knowledge-research）勿 load。"
)

_SPECIALIST_TOOL_RULES = (
    "本域通过 invoke_skill 调用已绑定 Skill；search_skills 补充 Skill 路由。"
    "load/run_skill_script 用于发展技能。必须 API tool_calls，禁止正文 DSML/脚本。"
)


def _specialist_common_prefix(*, task_mode: bool = False) -> str:
    parts = [
        f"{assistant_ai_home_persona()}。",
        SESSION_CONTEXT_RULE,
        _GROUNDING_RULES,
        _SEARCH_STRATEGY_RULES,
    ]
    if task_mode:
        parts.extend(
            [
                _SPECIALIST_TASK_MODE,
                _TOOL_LOOP_REPLY_RULE,
                _SPECIALIST_TOOL_RULES,
            ]
        )
    else:
        parts.extend(
            [
                _USER_REPLY_RULE,
                _USER_STYLE_RULES,
                _TOOL_LOOP_REPLY_RULE,
                _SPECIALIST_TOOL_RULES,
            ]
        )
    parts.extend(
        [
            "有检索材料时标注 [1][2]。",
            _SPECIALIST_SCOPE_RULE,
            _HUMAN_IN_THE_LOOP_RULES,
            "够用即停。",
        ]
    )
    return "\n".join(f"- {p}" for p in parts) + "\n"


def build_specialist_resident_prompt(
    agent_id: str,
    *,
    config_body: str | None = None,
    task_mode: bool = False,
) -> str:
    """子智能体 prompt — 仅本域约定。"""
    agent = (agent_id or "").strip()
    if agent == "orchestrator":
        body = (config_body or get_default_instruction_body("orchestrator") or "").strip()
        return (
            f"{assistant_ai_home_persona()}。\n"
            "- \u7b80\u4f53\u4e2d\u6587\uff1b\u3010\u7528\u6237\u8bb0\u5fc6\u3011\u540d\u79f0\u4f18\u5148\n"
            "══════════════════════════════════════════\n"
            "## 调度原则\n"
            "⊙ 你是一个调度 Agent，职责：理解→分配→验收。\n"
            "⊙ 你能直接做的：回答常识/寒暄（不用任何工具）、联网检索、知识库检索、知识图谱查询、图表绘制（mermaid_diagram）、双碳问答（carbon_qa_query）等。\n"
            "⊙ 平台操作、浏览器自动化等 → 由路由系统自动分配给专精 Agent 处理。\n"
            "⊙ 当专精 Agent 通过 request_orchestrator_assist 交还任务时，仔细阅读其反馈的问题描述，\n"
            "   重新规划处理方式（直接回复、调用工具、或分配给其他专精）。\n"
            "⊙ 不要自己执行专精工具，那是专精 Agent 的事。\n"
            "⊙ 历史消息中的工具使用场景不代表当前问题也需要同样处理，每次独立判断。\n"
            "══════════════════════════════════════════\n"
            f"- {SESSION_CONTEXT_RULE}\n"
            f"- {_GROUNDING_RULES}\n"
            f"- {_USER_REPLY_RULE}\n"
            f"- {_USER_STYLE_RULES}\n"
            f"- {orchestrator_failure_communication_rule()}\n"
            f"- {_HUMAN_IN_THE_LOOP_RULES}\n"
            "- 复合任务拆子任务分发给专精子 Agent；你只收结论，验收通过后汇总给用户\n"
            f"{body}\n"
        )
    common = _specialist_common_prefix(task_mode=task_mode)
    if agent == "skill-dev":
        from app.core.tool_skill_taxonomy import build_skill_dev_system_access_hint

        common += build_skill_dev_system_access_hint() + "\n"
        common += (
            "- 用户要求**生成/创建** Skill 时直接 invoke_skill(skill-development, call, {operation: create_skill, ...})，"
            "勿 list/load/run 已有包。\n"
            "- 浏览器调研（创建抓取 Skill 的中间步骤）：直接 invoke_skill(browser-automation, call, "
            "{operation: browser_navigate|browser_snapshot|browser_screenshot|..., params})，"
            "调研完立即回到技能创建主流程。\n"
            "- 纯主题检索调研：invoke_context_subagent(kind=explore, queries=[...]) 委托子 Agent。\n"
        )
    if config_body:
        return common + config_body.strip() + "\n"
    block = get_default_instruction_body(agent)
    if block:
        return common + block
    return common
