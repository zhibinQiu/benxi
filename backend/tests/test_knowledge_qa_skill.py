"""knowledge-qa 技能注册与路由目录。"""

from __future__ import annotations

from app.core.routing_catalog_md import (
    agents_routing_md_text,
    load_skills_routing_md,
)
from app.core.tool_skill_taxonomy import (
    AGENT_DEFAULT_SKILLS,
    SKILL_KNOWLEDGE_QA,
    mounted_tool_names_for_agent,
)
from app.skills.registry import ensure_skills_loaded, get_skill


def test_knowledge_qa_skill_registered():
    ensure_skills_loaded()
    skill = get_skill(SKILL_KNOWLEDGE_QA)
    assert skill is not None
    assert skill.name == "knowledge-qa"
    assert skill.title == "知识问答"
    action_names = {t.name for t in skill.tools}
    assert "ask" in action_names


def test_knowledge_qa_bound_to_orchestrator():
    assert SKILL_KNOWLEDGE_QA in AGENT_DEFAULT_SKILLS.get("orchestrator", ())
    mounted = mounted_tool_names_for_agent("orchestrator")
    assert "ontology_query" in mounted
    assert "knowledge_retrieve" in mounted
    assert "kg_query" in mounted


def test_skills_md_includes_knowledge_qa():
    load_skills_routing_md.cache_clear()
    entries = load_skills_routing_md()
    assert "knowledge-qa" in entries
    assert "知识问答" in (entries["knowledge-qa"].title or "")


def test_agents_md_orchestrator_mentions_knowledge_qa():
    text = agents_routing_md_text()
    assert "knowledge-qa" in text
