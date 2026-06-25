"""AI 智能体常驻层 — 短 prompt，细节交给 Skill 目录与专精块。"""

from __future__ import annotations

from app.core.agent_config import AGENT_INSTRUCTION_BLOCKS
from app.core.platform_assistant import assistant_ai_home_persona

# 子任务专精：过程在 workflow 展示，正文由调度层最后汇总
_SPECIALIST_TASK_MODE = (
    "本子任务：只调用工具完成操作；回复仅供系统记录，勿写面向用户的完整总结。"
)


def build_ai_home_resident_prompt() -> str:
    """单体 Agent 或未拆分子任务时的 system 骨架。"""
    return f"""{assistant_ai_home_persona()}。

约定：简体中文；默认自称「小析」，【用户记忆】有名称则以记忆为准；可用简短 Markdown。
工具：按会话中的 Skill 目录选用；够用即停，勿堆砌调用。
文档库指平台「知识中心→文档库」，不是本地文件夹；无权限勿删改他人文档；勿编造未检索/未工具返回的内容。

禁止：操作用户本地文件；无工具却声称已完成；绕过权限。"""


def _specialist_common_prefix(*, task_mode: bool = False) -> str:
    parts = [
        f"{assistant_ai_home_persona()}。",
        "简体中文；【用户记忆】名称优先；有检索材料时标注 [1][2]；勿编造。",
    ]
    if task_mode:
        parts.append(_SPECIALIST_TASK_MODE)
    parts.append("够用即停。")
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
            f"{body}\n"
        )
    common = _specialist_common_prefix(task_mode=task_mode)
    if config_body:
        return common + config_body.strip() + "\n"
    block = AGENT_INSTRUCTION_BLOCKS.get(agent)
    if block:
        return common + block
    return common
