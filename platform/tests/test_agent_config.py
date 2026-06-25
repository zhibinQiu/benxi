"""AGENT.md 默认内容与解析测试。"""

from __future__ import annotations

from app.core.agent_config import (
    build_default_agent_md,
    get_config_instruction_body,
    get_effective_description,
    validate_agent_md,
)
from app.core.agent_profiles import get_agent_profile


def test_default_agent_md_has_frontmatter():
    defn = get_agent_profile("research")
    assert defn is not None
    md = build_default_agent_md(defn)
    assert "id: research" in md
    assert "description:" in md
    assert "knowledge_retrieve" in md


def test_validate_agent_md_requires_matching_id():
    defn = get_agent_profile("platform")
    assert defn is not None
    md = build_default_agent_md(defn)
    try:
        validate_agent_md("platform", md)
    except Exception:
        raise AssertionError("valid md should pass") from None

    bad = md.replace("id: platform", "id: research")
    import pytest
    from app.core.exceptions import AppError

    with pytest.raises(AppError):
        validate_agent_md("platform", bad)


def test_custom_config_body_used_at_runtime():
    defn = get_agent_profile("research")
    assert defn is not None
    custom = (
        "---\n"
        "id: research\n"
        "title: 检索研究\n"
        "description: 用户要查资料时使用。\n"
        "---\n"
        "# 自定义正文\n"
        "- 仅测试\n"
    )
    body = get_config_instruction_body(defn, custom)
    assert body is not None
    assert "自定义正文" in body
    desc = get_effective_description(defn, custom)
    assert desc == "用户要查资料时使用。"
