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
    entries = load_skills_routing_md()
    assert "web-search" in entries
    assert "document-library" in entries
    assert entries["knowledge-research"].use_when


def test_load_agents_routing_md_has_specialists():
    entries = load_agents_routing_md()
    assert "platform" in entries
    assert "platform" in entries
    assert "skill-dev" in entries


def test_rank_routing_entries_prefers_use_when():
    entries = load_agents_routing_md()
    ranked = rank_routing_entries("帮我写一份可研报告", entries)
    assert ranked[0][1] == "report"


def test_build_skills_routing_display_includes_uploaded_section():
    from app.core.routing_catalog_md import build_skills_routing_display, skills_routing_md_text
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        text = build_skills_routing_display(db)
        assert skills_routing_md_text().split("\n", 1)[0] in text
    finally:
        db.close()
