"""语义工作流事件文案单测。"""

from app.services.semantic_workflow import (
    semantic_cache_reuse_event,
    semantic_probe_done_events,
    semantic_probe_start_events,
)


def test_semantic_probe_start_mentions_ontology_and_kg():
    evs = semantic_probe_start_events("s1")
    assert len(evs) == 2
    assert evs[0]["tool"] == "ontology_query"
    assert "本体" in evs[0]["title"]
    assert evs[1]["tool"] == "kg_query"
    assert "知识图谱" in evs[1]["title"]


def test_semantic_probe_done_direct_includes_thought():
    planning = "问什么/为何: 用户问的是组织归属；映射概念 人员、组织。"
    evs = semantic_probe_done_events(
        "s1", planning_text=planning, direct=True, has_material=True
    )
    tools = [e["tool"] for e in evs]
    assert "ontology_query" in tools
    assert "kg_query" in tools
    thought = [e for e in evs if e["phase"] == "agent_thought"]
    assert thought
    assert "本体" in thought[0]["title"] and "图谱" in thought[0]["title"]


def test_semantic_cache_reuse_event():
    ev = semantic_cache_reuse_event("s1")
    assert ev["phase"] == "agent_thought"
    assert "复用" in ev["title"]
