"""本析首页：知识预检索与来源标注。"""

from __future__ import annotations

from app.services.agent_intent import plan_agent_tools, should_prefetch_knowledge_context
from app.services.ai_chat_service import build_ai_home_source_footer
from app.services.kg_service import KgQaContext


def test_should_prefetch_for_policy_question():
    plan = plan_agent_tools(
        "碳配额发放流程是什么？",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert should_prefetch_knowledge_context("碳配额发放流程是什么？", None, plan) is True


def test_should_not_prefetch_for_browser_screenshot():
    plan = plan_agent_tools(
        "百度搜索双碳并查看结果截图",
        attach_count=0,
        kb_enabled=True,
        kg_enabled=True,
        web_enabled=True,
    )
    assert (
        should_prefetch_knowledge_context("百度搜索双碳并查看结果截图", None, plan)
        is False
    )


def test_source_footer_lists_kb_and_kg():
    footer = build_ai_home_source_footer(
        channels={"kb": True, "kg": True, "web": False},
        citations=[{"source": "local", "index": 1}, {"source": "local", "index": 2}],
        kg_context=KgQaContext(
            context_text="实体A --关系--> 实体B",
            citations=[],
            matched_entity_ids=[],
            entity_count=2,
            relation_count=1,
        ),
    )
    assert "知识库（2 条片段）" in footer
    assert "本体图谱（2 实体 / 1 关系）" in footer
    assert footer.index("本体图谱") < footer.index("知识库")
    assert footer.startswith("\n\n---\n**参考来源**：")
