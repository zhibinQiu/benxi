"""OntologyHubService：概念解析 / 字段映射 / 查询计划（无 Neo4j）。"""

from __future__ import annotations

import asyncio

from app.semantic.models import MatchedEntity, ResolvedConcept
from app.semantic.ontology.concept_resolver import ConceptResolver
from app.semantic.ontology.field_mapper import FieldMapper
from app.semantic.ontology.path_planner import PathPlanner


def test_concept_resolver_maps_person_org():
    resolver = ConceptResolver()
    hits = asyncio.run(resolver.resolve("张三属于哪个公司或部门？"))
    codes = {c.type_code for c in hits}
    assert "person" in codes or "org" in codes
    assert all(c.rationale for c in hits)


def test_field_mapper_sql_and_neo4j_bindings():
    mapper = FieldMapper()
    concepts = [
        ResolvedConcept(
            type_code="person",
            label="人员",
            property_keys=["email", "phone"],
            confidence=0.9,
        )
    ]
    bindings = mapper.map_concepts(concepts)
    sources = {b.source for b in bindings}
    # 明细属性有 SQL 映射时不再重复声明 neo4j 持有该属性
    assert "sql" in sources
    assert "neo4j" not in sources
    sql = [b for b in bindings if b.source == "sql"]
    assert any(b.table == "users" and b.column == "email" for b in sql)
    assert not any(b.table == "metrics" for b in sql)


def test_path_planner_builds_why_and_sql_steps():
    planner = PathPlanner()
    concepts = [
        ResolvedConcept(
            type_code="person",
            label="人员",
            property_keys=["email"],
            relation_codes=["member_of"],
            confidence=0.8,
            rationale="命中人员",
        )
    ]
    bindings = FieldMapper().map_concepts(concepts)
    plan = planner.plan("小王的邮箱是什么？", concepts=concepts, bindings=bindings)
    assert plan.why
    assert "邮箱" in plan.why or "person" in plan.why or "映射" in plan.why
    assert any(s.source == "sql" for s in plan.field_bindings) or plan.sql_steps
    assert plan.summary_text()


def test_path_planner_abox_steps_with_matched_entities():
    planner = PathPlanner()
    matched = [
        MatchedEntity(id="e1", name="张三", type_code="person", score=100),
    ]
    plan = planner.build_abox_plan(
        matched,
        "owner-1",
        max_depth=2,
        include_inferred=True,
        transitive_codes=["contains"],
        inverse_map={"employs": "member_of"},
    )
    assert plan.neo4j_steps
    assert plan.neo4j_steps[0].description == "直接关联实体"
    assert any("通用多跳" in s.description for s in plan.neo4j_steps)
    assert any("*1..2" in s.cypher for s in plan.neo4j_steps)
    assert any("path_nodes" in s.cypher for s in plan.neo4j_steps)
    assert any("逆关系" in s.description for s in plan.neo4j_steps)
    assert plan.matched_entity_ids == ["e1"]


def test_path_planner_generic_multihop_without_transitive():
    """无 transitive 时仍应生成通用多跳步骤。"""
    plan = PathPlanner().build_abox_plan(
        [MatchedEntity(id="e1", name="甲", type_code="person", score=10)],
        "owner-1",
        max_depth=3,
        include_inferred=True,
        transitive_codes=[],
        inverse_map={},
    )
    assert any("通用多跳" in s.description for s in plan.neo4j_steps)
    assert any("path_nodes" in s.cypher for s in plan.neo4j_steps)
    assert not any("传递推理" in s.description for s in plan.neo4j_steps)


def test_path_planner_prefers_relation_codes_filter():
    planner = PathPlanner()
    concepts = [
        ResolvedConcept(
            type_code="person",
            relation_codes=["employs", "part_of"],
            confidence=0.9,
        )
    ]
    bindings = FieldMapper().map_concepts(concepts)
    matched = [MatchedEntity(id="e1", name="张三", type_code="person", score=100)]
    plan = planner.plan(
        "张三属于哪个公司",
        concepts=concepts,
        bindings=bindings,
        matched=matched,
        owner_id="o1",
        max_depth=3,
        include_inferred=True,
    )
    multi = [s for s in plan.neo4j_steps if "通用多跳" in s.description]
    assert multi
    assert "employs" in multi[0].description or "employs" in multi[0].cypher


def test_ontology_hub_plan_includes_controlled_sql_for_person():
    concepts = [
        ResolvedConcept(
            type_code="person",
            label="人员",
            property_keys=["email", "phone"],
            confidence=0.9,
        )
    ]
    bindings = FieldMapper().map_concepts(concepts)
    plan = PathPlanner().plan(
        "查询人员邮箱",
        concepts=concepts,
        bindings=bindings,
    )
    assert plan.why
    assert any(b.source == "sql" and b.table == "users" for b in plan.field_bindings)
    assert plan.sql_steps
    assert "受控只读" in plan.sql_steps[0].description or plan.sql_steps[0].table == "users"
