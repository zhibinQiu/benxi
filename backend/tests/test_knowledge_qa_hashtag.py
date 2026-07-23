"""知识问答硬触发（不经模型选型）。"""

from __future__ import annotations

from app.core.tool_skill_taxonomy import SKILL_KNOWLEDGE_QA
from app.services.agent_planner import _rule_plan_for_knowledge_qa_hashtag
from app.services.agent_skill_router import match_knowledge_qa_hashtag


def test_match_knowledge_qa_hashtag_prefix():
    assert match_knowledge_qa_hashtag("#知识问答 公司考勤制度是什么") == "公司考勤制度是什么"
    assert match_knowledge_qa_hashtag("# knowledge-qa  carbon market") == "carbon market"
    assert match_knowledge_qa_hashtag("#Knowledge-QA\n问题") == "问题"
    assert match_knowledge_qa_hashtag("#知识问答") == ""
    assert match_knowledge_qa_hashtag("普通问题 知识问答") is None


def test_match_knowledge_qa_please_use_skill():
    assert (
        match_knowledge_qa_hashtag("请使用 知识问答 技能：烟台如何搭建零碳园区")
        == "烟台如何搭建零碳园区"
    )
    assert (
        match_knowledge_qa_hashtag("请使用知识问答技能：烟台如何搭建零碳园区")
        == "烟台如何搭建零碳园区"
    )
    assert match_knowledge_qa_hashtag("使用 knowledge-qa 技能 园区规划") == "园区规划"
    assert match_knowledge_qa_hashtag("调用知识问答技能") == ""


def test_rule_plan_for_knowledge_qa_hashtag():
    plan = _rule_plan_for_knowledge_qa_hashtag("#知识问答 实体关系有哪些")
    assert plan is not None
    assert plan.uploaded_skill == SKILL_KNOWLEDGE_QA
    assert plan.source == "rule"
    assert plan.direct_answer is False

    plan2 = _rule_plan_for_knowledge_qa_hashtag(
        "请使用 知识问答 技能：烟台如何搭建零碳园区"
    )
    assert plan2 is not None
    assert plan2.uploaded_skill == SKILL_KNOWLEDGE_QA
    assert "烟台如何搭建零碳园区" in plan2.steps[0]

    assert _rule_plan_for_knowledge_qa_hashtag("随便问问") is None
