"""本体语义中枢服务 — Agent 决策唯一入口（概念理解 / 映射 / 路径规划）。

本体不是知识仓库：不直接跑 Cypher/SQL 取事实；事实由 KgQueryService 执行。
Schema / Kg / DB 字段映射由宿主注入，本模块不拉平台连接工厂。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.semantic.models import (
    AgentDecisionContext,
    FieldBinding,
    MatchedEntity,
    QueryPlan,
    ResolvedConcept,
)

from .concept_resolver import ConceptResolver
from .field_mapper import FieldMapper
from .intents import INTENT_CAPABILITY, INTENT_ENTITY_LOOKUP, detect_intent_tags, tools_for_intents
from .path_planner import PathPlanner
from .schema_view import SchemaView

if TYPE_CHECKING:
    from app.semantic.kg.service import KgQueryService

_CAPABILITY_TYPES = frozenset({"agent", "tool", "skill"})

MapperFactory = Callable[[Any], FieldMapper]


class OntologyHubService:
    """语义中枢：问什么、该查什么、去哪查、按什么路径、为什么。"""

    def __init__(
        self,
        *,
        schema: SchemaView | None = None,
        resolver: ConceptResolver | None = None,
        mapper: FieldMapper | None = None,
        mapper_factory: MapperFactory | None = None,
        planner: PathPlanner | None = None,
        kg: KgQueryService | None = None,
    ) -> None:
        self._schema = schema
        self._resolver = resolver or ConceptResolver(schema)
        self._mapper = mapper or FieldMapper()
        self._mapper_factory = mapper_factory
        self._planner = planner or PathPlanner()
        self._kg = kg

    def bind_kg(self, kg: KgQueryService) -> None:
        self._kg = kg

    async def _kg_svc(self) -> KgQueryService:
        if self._kg is None:
            raise RuntimeError(
                "KgQueryService not bound; pass kg= to OntologyHubService or call bind_kg()"
            )
        return self._kg

    async def resolve_concepts(self, question: str) -> list[ResolvedConcept]:
        return await self._resolver.resolve(question)

    def map_fields(
        self,
        concepts: list[ResolvedConcept],
        *,
        db: Any | None = None,
    ) -> list[FieldBinding]:
        if db is not None and self._mapper_factory is not None:
            return self._mapper_factory(db).map_concepts(concepts)
        return self._mapper.map_concepts(concepts)

    async def compact_schema(
        self,
        question: str = "",
        *,
        type_codes: list[str] | None = None,
        limit_types: int = 12,
    ) -> str:
        if self._schema is None:
            return ""
        return await self._schema.compact(
            question, type_codes=type_codes, limit_types=limit_types
        )

    async def plan_query(
        self,
        question: str,
        *,
        owner_id: str | None = None,
        matched: list[MatchedEntity] | None = None,
        max_depth: int = 3,
        include_inferred: bool = True,
        db: Any | None = None,
    ) -> QueryPlan:
        concepts = await self.resolve_concepts(question)
        concepts = FieldMapper.expand_concepts_via_relations(concepts)
        bindings = self.map_fields(concepts, db=db)
        type_codes = [c.type_code for c in concepts if c.type_code]
        entities = list(matched or [])
        if owner_id and not entities:
            kg = await self._kg_svc()
            entities = await kg.match_entities(
                question, owner_id, type_codes=type_codes or None
            )

        transitive: list[str] = []
        inverse_map: dict[str, str] = {}
        if entities and include_inferred and self._schema is not None:
            transitive = await self._schema.transitive_relation_codes()
            inverse_map = await self._schema.inverse_relation_map()

        return self._planner.plan(
            question,
            concepts=concepts,
            bindings=bindings,
            matched=entities,
            owner_id=owner_id or "",
            max_depth=max_depth,
            include_inferred=include_inferred,
            transitive_codes=transitive,
            inverse_map=inverse_map,
        )

    async def build_decision_context(
        self,
        question: str,
        owner_id: str,
        *,
        max_depth: int = 3,
        include_inferred: bool = True,
        db: Any | None = None,
    ) -> AgentDecisionContext:
        q = (question or "").strip()
        intent_tags = detect_intent_tags(q)
        preferred, blocked = tools_for_intents(intent_tags)

        # 先本体解析概念类型，再按类型引导 ABox 命中
        concepts = await self.resolve_concepts(q)
        concepts = FieldMapper.expand_concepts_via_relations(concepts)
        type_codes = [c.type_code for c in concepts if c.type_code]

        kg = await self._kg_svc()
        matched = await kg.match_entities(
            q, owner_id, type_codes=type_codes or None
        )
        plan = await self.plan_query(
            q,
            owner_id=owner_id,
            matched=matched,
            max_depth=max_depth,
            include_inferred=include_inferred,
            db=db,
        )
        preferred = list(dict.fromkeys([*plan.preferred_tools, *preferred]))
        blocked = list(dict.fromkeys([*plan.blocked_tools, *blocked]))
        intent_tags = list(dict.fromkeys([*plan.intent_tags, *intent_tags]))

        from app.semantic.kg.reasoning import ReasoningPayload

        payload: ReasoningPayload | None = None
        if matched:
            payload = await kg.execute_plan(
                plan, owner_id, matched=matched, db=db
            )
        elif plan.sql_steps and db is not None:
            payload = await kg.execute_plan(
                plan, owner_id, matched=[], db=db
            )

        matched = list(payload.matched_entities) if payload and payload.matched_entities else matched
        type_codes_out = list({e.type_code for e in matched if e.type_code})
        if not type_codes_out and plan.concepts:
            type_codes_out = [c.type_code for c in plan.concepts]
        tbox = await self.compact_schema(q, type_codes=type_codes_out or None)

        capability_hints: list[str] = []
        for ent in matched:
            if ent.type_code in _CAPABILITY_TYPES:
                capability_hints.append(f"{ent.type_code}:{ent.name}")
                if INTENT_CAPABILITY not in intent_tags:
                    intent_tags.append(INTENT_CAPABILITY)
                if "kg_query" not in preferred:
                    preferred = ["kg_query", *preferred]

        has_material = bool(payload and payload.has_material)
        snippets = ""
        if payload and has_material:
            snippets = payload.context_text or ""
        elif payload and (payload.context_text or "").strip():
            text = (payload.context_text or "").strip()
            if text and "无匹配行" not in text and "跳过:" not in text:
                snippets = text
                has_material = True
                payload.has_material = True

        if has_material and "kg_query" not in preferred:
            preferred = ["kg_query", *preferred]
            if INTENT_ENTITY_LOOKUP not in intent_tags:
                intent_tags.append(INTENT_ENTITY_LOOKUP)

        preferred = list(dict.fromkeys(preferred))
        blocked = list(dict.fromkeys(blocked))

        confidence = 0.0
        if has_material and payload:
            confidence = min(
                0.95,
                0.4
                + 0.1 * max(len(matched), 1)
                + 0.05 * int(payload.relation_count or 0),
            )
        elif intent_tags:
            confidence = 0.35
        elif matched:
            confidence = 0.25
        elif plan.concepts:
            confidence = 0.2

        return AgentDecisionContext(
            matched_entities=matched,
            abox_snippets=snippets,
            tbox_compact=tbox,
            intent_tags=intent_tags,
            preferred_tools=preferred,
            blocked_tools=blocked,
            confidence=confidence,
            has_material=has_material,
            citations=list(payload.citations) if payload else [],
            entity_count=int(payload.entity_count) if payload else 0,
            relation_count=int(payload.relation_count) if payload else 0,
            reasoning_hops=int(payload.reasoning_hops) if payload else 0,
            inferred_entities=int(payload.inferred_entities) if payload else 0,
            capability_hints=capability_hints,
            query_plan=plan,
            evidence_paths=list(payload.evidence_paths) if payload else [],
        )

    async def explain_for_tool(self, question: str) -> str:
        """ontology_query 工具：概念 + 映射 + 计划 why（非整库 dump）。"""
        plan = await self.plan_query(question)
        tbox = await self.compact_schema(
            question,
            type_codes=[c.type_code for c in plan.concepts] or None,
        )
        parts = [
            "【语义中枢决策】",
            plan.summary_text(max_chars=900) or plan.why or "无明确概念命中",
        ]
        if tbox.strip():
            parts.append("")
            parts.append(tbox)
        else:
            parts.append("")
            parts.append("当前本体为空，建议先通过「本体定义」初始化默认本体")
        return "\n".join(parts).strip()
