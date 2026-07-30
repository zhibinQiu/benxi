"""KG 事实查询服务 — Agent / 工具唯一入口，封装 Neo4j。

Driver 与 SchemaView 由宿主注入；本模块不调用平台连接工厂。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.semantic.models import (
    GraphStats,
    MatchedEntity,
    NeighborHit,
    PathResult,
    QueryPlan,
)

from .query_engine import KgQueryEngine, question_match_tokens
from .reasoning import ReasoningEngine, ReasoningPayload
from app.semantic.ontology.schema_view import SchemaView

if TYPE_CHECKING:
    from neo4j import AsyncDriver

__all__ = [
    "KgQueryService",
    "question_match_tokens",
    "ReasoningPayload",
]


class KgQueryService:
    """按本体计划执行 ABox 查询；Agent 禁止直接 get_neo4j。"""

    def __init__(
        self,
        driver: AsyncDriver,
        *,
        schema: SchemaView | None = None,
    ) -> None:
        self._driver = driver
        self._schema = schema
        self._engine = KgQueryEngine(driver)
        self._reasoning: ReasoningEngine | None = None

    def bind_schema(self, schema: SchemaView) -> None:
        """注入本体 Schema（标签与推理元数据）。"""
        self._schema = schema
        self._reasoning = None

    def _get_reasoning(self) -> ReasoningEngine:
        if self._reasoning is None:
            self._reasoning = ReasoningEngine(
                self._driver,
                entity_label_fn=self._entity_label,
                relation_label_fn=self._relation_label,
            )
        return self._reasoning

    async def _entity_label(self, type_code: str) -> str:
        if self._schema is None:
            return type_code
        return await self._schema.entity_type_label(type_code)

    async def _relation_label(self, type_code: str) -> str:
        if self._schema is None:
            return type_code
        return await self._schema.relation_type_label(type_code)

    async def match_entities(
        self,
        question: str,
        owner_id: str,
        *,
        limit: int = 5,
        type_codes: list[str] | None = None,
    ) -> list[MatchedEntity]:
        return await self._engine.match_entities_in_question(
            question, owner_id, limit=limit, type_codes=type_codes
        )

    async def semantic_search(
        self,
        query: str,
        owner_id: str,
        *,
        limit: int = 10,
    ) -> list[MatchedEntity]:
        return await self._engine.semantic_search(query, owner_id, limit=limit)

    async def neighbors(
        self,
        entity_name_or_id: str,
        owner_id: str,
        *,
        depth: int = 1,
        limit: int = 30,
    ) -> list[NeighborHit]:
        return await self._engine.get_neighbors(
            entity_name_or_id, owner_id, depth=depth, limit=limit
        )

    async def find_path(
        self,
        start: str,
        end: str,
        owner_id: str,
        *,
        max_depth: int = 3,
        limit: int = 5,
    ) -> list[PathResult]:
        return await self._engine.find_path(
            start, end, owner_id, max_depth=max_depth, limit=limit
        )

    async def stats(self, owner_id: str) -> GraphStats:
        return await self._engine.get_graph_statistics(owner_id)

    async def execute_plan(
        self,
        plan: QueryPlan,
        owner_id: str,
        *,
        matched: list[MatchedEntity] | None = None,
        db: Any | None = None,
    ) -> ReasoningPayload:
        """执行本体计划：先 Neo4j（若有），再受控只读 SQL。"""
        _ = owner_id
        entities = list(matched or [])
        if not entities and plan.matched_entity_ids:
            entities = [
                MatchedEntity(id=eid, name="", type_code="")
                for eid in plan.matched_entity_ids
            ]
        if plan.neo4j_steps:
            payload = await self._get_reasoning().execute_query_plan(plan, entities)
        else:
            payload = ReasoningPayload(
                matched_entities=entities,
                has_material=False,
            )
        if plan.sql_steps and db is not None:
            from app.semantic.sql_executor import execute_sql_steps

            sql_text = execute_sql_steps(
                db,
                list(plan.sql_steps),
                matched=entities,
                question=plan.question or "",
            )
            if sql_text.strip():
                base = (payload.context_text or "").rstrip()
                payload.context_text = (
                    f"{base}\n\n## 【SQL 证据】\n{sql_text}"
                    if base
                    else f"## 【SQL 证据】\n{sql_text}"
                )
                useful = (
                    "无匹配行" not in sql_text
                    and "跳过:" not in sql_text
                    and "执行失败" not in sql_text
                )
                payload.has_material = payload.has_material or useful
                payload.citations = list(payload.citations or [])
                payload.citations.append(
                    {
                        "source": "sql",
                        "title": "受控只读 SQL",
                        "snippet": sql_text[:400],
                    }
                )
        return payload

    async def reason(
        self,
        question: str,
        owner_id: str,
        *,
        max_depth: int = 3,
        include_inferred: bool = True,
        plan: QueryPlan | None = None,
        db: Any | None = None,
    ) -> ReasoningPayload:
        """事实推理：优先执行传入计划；否则请本体规划后再执行。"""
        matched = await self.match_entities(question, owner_id)
        if not matched:
            return await self._get_reasoning().reason(
                question, owner_id, max_depth=max_depth, include_inferred=False
            )

        active_plan = plan
        if active_plan is None or not active_plan.neo4j_steps:
            from app.semantic.ontology.path_planner import PathPlanner

            transitive: list[str] = []
            inverse_map: dict[str, str] = {}
            if self._schema is not None:
                transitive = await self._schema.transitive_relation_codes()
                inverse_map = await self._schema.inverse_relation_map()
            active_plan = PathPlanner().build_abox_plan(
                matched,
                owner_id,
                max_depth=max_depth,
                include_inferred=include_inferred,
                transitive_codes=transitive,
                inverse_map=inverse_map,
            )

        return await self.execute_plan(
            active_plan, owner_id, matched=matched, db=db
        )
