"""Skill 路由 — 复杂任务先匹配已有发展技能，再考虑原子工具。"""

from __future__ import annotations

from app.skills.types import SkillDefinition, SkillSource

SKILL_LOADING_RULES = """【Skill 优先】
1. 复杂/重复任务：先 list_agent_skills 或阅读 available_skills，匹配 slug 则 run_skill_script
2. 无匹配发展技能时，简单一次性查价/公开数据可用 web_search，勿为此创建 Skill
3. 仅用户明确要求创建/更新 Skill，或任务与某条 Use when 明确匹配时，才 create/update
4. 现有技能不能满足：小改用 update_uploaded_skill_file，大改才 create_uploaded_skill（数据类须 main.py）
5. 新建或修改后须 run_skill_script 验证；内置编排技能禁止 load_uploaded_skill"""


def _truncate(text: str, limit: int = 72) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def format_skill_route_line(
    defn: SkillDefinition,
    *,
    tag: str = "",
) -> str:
    """单行路由描述：Use when / Don't use when / Output。"""
    use = _truncate(defn.use_when or defn.description or "任务明确匹配时")
    dont = _truncate(defn.dont_use_when or "闲聊、无关任务、仅需原子工具时")
    output = _truncate(defn.output or "按 SKILL.md 或脚本结论作答")
    prefix = f"`{defn.name}`"
    if tag:
        prefix = f"{prefix} {tag}"
    return f"- {prefix} — Use when: {use} | Don't: {dont} | Output: {output}"


def uploaded_skill_tag(*, has_script: bool) -> str:
    return "[脚本型]" if has_script else "[指令型]"
