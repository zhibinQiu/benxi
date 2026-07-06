"""Skill 路由描述。"""

from __future__ import annotations

from app.skills.routing import format_skill_route_line
from app.skills.types import SkillDefinition, SkillReadiness, SkillSource


def test_format_skill_route_line_uses_routing_fields():
    defn = SkillDefinition(
        name="demo",
        title="Demo",
        description="fallback",
        source=SkillSource.BUILTIN,
        use_when="用户要画图",
        dont_use_when="闲聊",
        output="mermaid 源码",
    )
    line = format_skill_route_line(defn, tag="[builtin]")
    assert "Use when:" in line
    assert "用户要画图" in line
    assert "Don't:" in line
    assert "闲聊" in line
