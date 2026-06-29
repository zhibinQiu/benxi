"""AI 智能体常驻层 — 短 prompt，细节交给 Skill 目录与专精块。"""

from __future__ import annotations

from app.core.agent_config import AGENT_INSTRUCTION_BLOCKS
from app.core.platform_assistant import assistant_ai_home_persona, assistant_conclusion_source_priority, assistant_user_communication_style
from app.core.session_chat_history import SESSION_CONTEXT_RULE
from app.skills.routing import SKILL_LOADING_RULES

# 子任务专精：过程在 workflow 展示，正文由调度层最后汇总
_SPECIALIST_TASK_MODE = (
    "本子任务：只调用工具完成操作；回复仅供系统记录，勿写面向用户的完整总结。"
    "探索/试错细节勿写入回复，只返回可验收的结论或结构化结果。"
)

_TOOL_DISCOVERY_RULES = (
    "工具：默认核心检索 + search_tools；"
    "复杂任务先匹配已有发展技能并 run_skill_script，无匹配再用 web_search 等原子工具。"
    "创建 Skill 前先查目录，能用则用，勿重复 create。"
    "必须 API tool_calls，禁止正文 DSML/脚本。"
)

_USER_REPLY_RULE = (
    "面向用户的最终结论必须准确回应用户问题与诉求，不可答非所问或只描述内部过程。"
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
    + "\n事实约束：只陈述工具返回、检索片段或用户在本会话明确提供的内容；"
    "禁止编造用户/文档/数字/邮箱/部门等任何未验证数据。"
    "信息不足、权限不明或存在多种理解时：说明不确定之处并请用户确认，勿猜测作答。"
)

_ROUTE_KIND_RULES = (
    "任务分域（调度/专精须一致）："
    "【系统操作】文档库/待办/通知/用户与部门 → platform；"
    "【调研检索】知识库正文/联网/政策 → research；"
    "【上传 Skill】创建/修改/执行 run_skill_script 取数 → skill-dev；"
    "【报告/图表/RPA/定时】→ report / diagram / rpa / scheduler；"
    "寒暄与简单心算 → orchestrator。"
    "禁止混用：系统名单勿用 knowledge_retrieve；脚本查价勿让用户手动执行命令。"
)


def build_ai_home_resident_prompt() -> str:
    """单体 Agent 或未拆分子任务时的 system 骨架。"""
    return f"""{assistant_ai_home_persona()}。

约定：简体中文；默认自称「小析」，【用户记忆】有名称则以记忆为准。
{SESSION_CONTEXT_RULE}
{_GROUNDING_RULES}
{_USER_REPLY_RULE}
{_USER_STYLE_RULES}
{_ROUTE_KIND_RULES}
{_TOOL_DISCOVERY_RULES}
{_TOOL_LOOP_REPLY_RULE}
{SKILL_LOADING_RULES}
{_WRITE_RATE_RULES}
够用即停；文档库=平台「知识中心→文档库」；无权限勿删改他人文档。

禁止：操作用户本地文件；无工具却声称已完成；绕过权限；编造未验证事实。"""


def _specialist_common_prefix(*, task_mode: bool = False) -> str:
    parts = [
        f"{assistant_ai_home_persona()}。",
        SESSION_CONTEXT_RULE,
        _GROUNDING_RULES,
    ]
    if task_mode:
        parts.extend(
            [
                _SPECIALIST_TASK_MODE,
                _TOOL_LOOP_REPLY_RULE,
                _TOOL_DISCOVERY_RULES,
            ]
        )
    else:
        parts.extend(
            [
                _USER_REPLY_RULE,
                _USER_STYLE_RULES,
                _TOOL_LOOP_REPLY_RULE,
                _TOOL_DISCOVERY_RULES,
            ]
        )
    parts.extend(
        [
            "有检索材料时标注 [1][2]。",
            _ROUTE_KIND_RULES,
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
        body = (config_body or AGENT_INSTRUCTION_BLOCKS["orchestrator"]).strip()
        return (
            f"{assistant_ai_home_persona()}。\n"
            "- 简体中文；【用户记忆】名称优先；寒暄与简单问答直接答\n"
            f"- {SESSION_CONTEXT_RULE}\n"
            f"- {_GROUNDING_RULES}\n"
            f"- {_USER_REPLY_RULE}\n"
            f"- {_USER_STYLE_RULES}\n"
            f"- {_ROUTE_KIND_RULES}\n"
            "- 复合任务拆给专精子 Agent；你只收子任务结论，不收其探索过程\n"
            f"{body}\n"
        )
    common = _specialist_common_prefix(task_mode=task_mode)
    if config_body:
        return common + config_body.strip() + "\n"
    block = AGENT_INSTRUCTION_BLOCKS.get(agent)
    if block:
        return common + block
    return common
