"""Skill 路由文案格式化 — 短格式，节约 prompt token。"""

from __future__ import annotations

from app.agentkit.skills.types import SkillDefinition


def truncate_route_text(text: str, limit: int = 72) -> str:
    """压缩空白并截断路由描述。"""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def format_skill_route_line(defn: SkillDefinition, *, tag: str = "") -> str:
    """单行路由描述（用于 skills.md / 动态目录）。"""
    use = truncate_route_text(defn.use_when or defn.description or "任务明确匹配时")
    dont = truncate_route_text(defn.dont_use_when or "闲聊、无关任务、仅需原子工具时")
    output = truncate_route_text(defn.output or "按 SKILL.md 或脚本结论作答")
    prefix = f"`{defn.name}`"
    if tag:
        prefix = f"{prefix} {tag}"
    return f"- {prefix} — Use when: {use} | Don't: {dont} | Output: {output}"
