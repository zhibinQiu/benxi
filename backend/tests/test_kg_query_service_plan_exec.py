"""KgQueryService.execute_plan — mock Neo4jOps，不连真实库。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.semantic.kg.reasoning import ReasoningEngine
from app.semantic.kg.service import KgQueryService
from app.semantic.models import MatchedEntity, Neo4jPlanStep, QueryPlan


def test_execute_plan_runs_neo4j_steps():
    driver = MagicMock()
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    class _Rec(dict):
        pass

    async def _run(cypher, params=None):
        _ = cypher, params

        class _Cursor:
            async def __aiter__(self):
                yield _Rec(
                    source_id="e1",
                    source_name="张三",
                    source_type="person",
                    rel_type="member_of",
                    target_id="o1",
                    target_name="研发部",
                    target_type="org",
                )

        return _Cursor()

    session.run = AsyncMock(side_effect=_run)
    driver.session = MagicMock(return_value=session)

    matched = [MatchedEntity(id="e1", name="张三", type_code="person", score=100)]
    plan = QueryPlan(
        neo4j_steps=[
            Neo4jPlanStep(
                description="直接关联实体",
                cypher="MATCH (a)-[r]-(b) RETURN a.id AS source_id",
                params={"ids": ["e1"], "owner": "u1"},
            )
        ],
        matched_entity_ids=["e1"],
        why="test",
    )

    engine = ReasoningEngine(
        driver,
        entity_label_fn=AsyncMock(side_effect=lambda c: c or "?"),
        relation_label_fn=AsyncMock(side_effect=lambda c: c or "?"),
    )

    async def _fake_collect(query, params=None):
        _ = query, params
        return [
            {
                "id": "e1",
                "name": "张三",
                "type_code": "person",
                "description": "",
            },
            {
                "id": "o1",
                "name": "研发部",
                "type_code": "org",
                "description": "",
            },
        ]

    with patch.object(engine._ops, "collect", AsyncMock(side_effect=_fake_collect)):
        payload = asyncio.run(engine.execute_query_plan(plan, matched))

    assert payload.has_material
    assert "张三" in payload.context_text
    assert payload.relation_count >= 1


def test_kg_service_execute_plan_delegates():
    driver = MagicMock()
    svc = KgQueryService(driver)
    plan = QueryPlan(
        neo4j_steps=[
            Neo4jPlanStep(description="noop", cypher="RETURN 1", params={})
        ],
        why="x",
    )
    fake = MagicMock()
    fake.has_material = False
    fake.context_text = ""
    fake.matched_entities = []
    fake.entity_count = 0
    fake.relation_count = 0
    fake.reasoning_hops = 0
    fake.inferred_entities = 0
    fake.citations = []

    with patch.object(
        svc,
        "_get_reasoning",
        return_value=MagicMock(execute_query_plan=AsyncMock(return_value=fake)),
    ):
        out = asyncio.run(svc.execute_plan(plan, "owner"))
    assert out is fake
