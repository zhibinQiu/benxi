"""skills.md / agents.md 路由目录测试。"""

from __future__ import annotations

from app.core.routing_catalog_md import (
    load_agents_routing_md,
    load_skills_routing_md,
    parse_routing_md,
    rank_routing_entries,
)


def test_parse_routing_md_sections():
    text = """
# 标题

## web-search
- Use when: 联网检索
- Don't use when: 文档库
- Output: 摘要

## platform
- Title: 平台
- Use when: 文档操作
"""
    entries = parse_routing_md(text)
    assert "web-search" in entries
    assert entries["web-search"].use_when == "联网检索"
    assert entries["platform"].title == "平台"


def test_load_skills_routing_md_has_core_skills():
    load_skills_routing_md.cache_clear()
    entries = load_skills_routing_md()
    assert "carbon-qa" in entries
    assert "knowledge-qa" in entries


def test_load_agents_routing_md_has_specialists():
    entries = load_agents_routing_md()
    assert "platform" in entries
    assert "platform" in entries
    assert "skill-dev" in entries


def test_rank_routing_entries_prefers_use_when():
    entries = load_agents_routing_md()
    ranked = rank_routing_entries("帮我写一份可研报告", entries)
    assert ranked[0][1] == "report"


def test_rank_routing_entries_ignores_dont_use_when_only_token():
    """仅出现在 Don't use when 的词不得正向加分（避免「需要」误中 stock）。"""
    text = """
## stock-deep-analysis
- Use when: 个股基本面深度分析
- Don't use when: 需要多角色辩论或量价技术面分析
- Output: 结构化报告

## carbon-qa
- Use when: 需要解读碳价行情与碳交易政策
- Don't use when: 其他非双碳领域
- Output: 事实底稿
"""
    entries = parse_routing_md(text)
    ranked = rank_routing_entries("把两只大象放进冰箱需要几步", entries)
    ids = [sid for _, sid in ranked]
    assert "stock-deep-analysis" not in ids
    assert "carbon-qa" in ids

    ranked_pos = rank_routing_entries("个股基本面深度分析", entries)
    assert ranked_pos[0][1] == "stock-deep-analysis"


def test_build_skills_routing_display_includes_uploaded_section():
    from app.core.routing_catalog_md import build_skills_routing_display, skills_routing_md_text
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        text = build_skills_routing_display(db)
        assert skills_routing_md_text().split("\n", 1)[0] in text
    finally:
        db.close()
