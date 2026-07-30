"""用户指定智能体/技能固定前缀解析。"""

from __future__ import annotations

from app.core.agent_profiles import AGENT_PROFILES
from app.services.user_capability_directive import (
    analysis_text_for_semantic,
    parse_user_capability_directive,
    resolve_user_capability_directive,
)


def test_parse_agent_directive_splits_body():
    d = parse_user_capability_directive("请让 报告撰写 Agent：张三属于哪个部门")
    assert d is not None
    assert d.kind == "agent"
    assert "报告撰写" in d.raw_label
    assert d.body == "张三属于哪个部门"


def test_parse_skill_directive_splits_body():
    d = parse_user_capability_directive("请使用 carbon-report 技能：写一份履约摘要")
    assert d is not None
    assert d.kind == "skill"
    assert d.raw_label == "carbon-report"
    assert d.body == "写一份履约摘要"


def test_resolve_skill_slug_without_catalog_hit():
    """catalog 未命中时，合法 slug 仍应作为 skill_name 硬定位。"""
    from unittest.mock import MagicMock, patch

    with patch(
        "app.skills.catalog.list_all_skill_definitions",
        return_value=[],
    ), patch(
        "app.services.agent_skill_routing.build_skill_agent_index",
        return_value={},
    ):
        d = resolve_user_capability_directive(
            MagicMock(),
            "请使用 zhangxuefeng-skill 技能：孩子想学金融怎么办？",
        )
    assert d is not None
    assert d.kind == "skill"
    assert d.resolved
    assert d.skill_name == "zhangxuefeng-skill"
    assert d.body == "孩子想学金融怎么办？"
    assert d.agent_id == ""


def test_analysis_text_strips_prefix():
    assert (
        analysis_text_for_semantic("请让 双碳智能体 Agent：本月碳价")
        == "本月碳价"
    )
    assert analysis_text_for_semantic("普通问题不带前缀") == "普通问题不带前缀"
    assert analysis_text_for_semantic("请使用 foo 技能：") == ""


def test_resolve_agent_directive_against_builtin():
    from unittest.mock import MagicMock

    p = next(x for x in AGENT_PROFILES if x.id == "report")
    msg = f"请让 {p.title} Agent：生成大纲"
    d = resolve_user_capability_directive(MagicMock(), msg)
    assert d is not None
    assert d.resolved
    assert d.agent_id == "report"
    assert d.body == "生成大纲"
