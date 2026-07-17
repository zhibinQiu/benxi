"""Agent 问题规划缓存。"""

from __future__ import annotations

import uuid

from app.services.agent_plan_cache_service import (
    PLAN_TYPE_AGENT_EXECUTION,
    PLAN_TYPE_KNOWLEDGE_QA,
    agent_execution_scope_key,
    execution_plan_from_payload,
    execution_plan_to_payload,
    knowledge_qa_scope_key,
    lookup_cached_payload,
    normalize_question,
    question_similarity,
    store_cached_payload,
)
from app.agentkit.loop import AgentExecutionPlan


def test_normalize_question_collapses_punctuation():
    assert normalize_question("  查一下碳配额流程？ ") == normalize_question("查一下碳配额流程")


def test_question_similarity_detects_paraphrase():
    a = "公司碳排放配额怎么申请"
    b = "企业碳排放配额如何申请"
    assert question_similarity(a, b) >= 0.85


def test_store_and_lookup_agent_execution_plan():
    user_id = uuid.uuid4()
    scope = agent_execution_scope_key(
        user_id,
        available_atomic_tools={"knowledge_retrieve", "web_search"},
        uploaded_skills=set(),
    )
    plan = AgentExecutionPlan(
        reasoning="查内部制度",
        intent="查询碳配额流程",
        direct_answer=False,
        allowed_tools=("knowledge_retrieve",),
        blocked_tools=("web_search",),
        uploaded_skill=None,
        steps=("检索文档", "作答"),
        source="llm",
    )
    store_cached_payload(
        scope,
        "公司碳配额怎么申请？",
        plan_type=PLAN_TYPE_AGENT_EXECUTION,
        intent=plan.intent,
        payload=execution_plan_to_payload(plan),
    )
    hit = lookup_cached_payload(
        scope,
        "企业碳排放配额如何申请",
        plan_type=PLAN_TYPE_AGENT_EXECUTION,
    )
    assert hit is not None
    restored = execution_plan_from_payload(hit["payload"])
    assert restored.allowed_tools == plan.allowed_tools
    assert restored.source == "cache"


def test_knowledge_qa_plan_cache():
    user_id = uuid.uuid4()
    doc_ids = [uuid.uuid4(), uuid.uuid4()]
    scope = knowledge_qa_scope_key(user_id, doc_ids)
    store_cached_payload(
        scope,
        "这份报告的核心结论是什么",
        plan_type=PLAN_TYPE_KNOWLEDGE_QA,
        intent="拆解报告结论检索",
        payload={
            "reasoning": "拆解报告结论检索",
            "sub_questions": ["报告主要结论", "关键数据与依据"],
        },
    )
    hit = lookup_cached_payload(
        scope,
        "这份报告的核心结论是什么？",
        plan_type=PLAN_TYPE_KNOWLEDGE_QA,
    )
    assert hit is not None
    assert hit["payload"]["sub_questions"] == ["报告主要结论", "关键数据与依据"]
