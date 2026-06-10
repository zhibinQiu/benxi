from app.services.knowledge_agent_service import plan_knowledge_query


def test_plan_detects_version_compare_intent():
    plan = plan_knowledge_query(
        question="v1和v2有什么差异？",
        document_count=1,
        knowflow_available=True,
    )
    assert "version_compare" in plan["intents"]
    assert "version_changelogs" in plan["data_sources"]
    assert "knowflow_chunks" in plan["data_sources"]


def test_plan_default_document_qa():
    plan = plan_knowledge_query(
        question="碳排放核算边界是什么？",
        document_count=2,
        knowflow_available=False,
    )
    assert plan["intent"] == "document_qa"
    assert "local_fulltext" in plan["data_sources"]
    assert "version_changelogs" not in plan["data_sources"]
