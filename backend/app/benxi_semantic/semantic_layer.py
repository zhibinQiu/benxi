"""语义层统一入口 — 构建 AgentDecisionContext。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .intents import (
    INTENT_CAPABILITY,
    detect_intent_tags,
    tools_for_intents,
)
from .models import AgentDecisionContext
from .query_engine import SemanticQueryEngine
from .reasoning import ReasoningEngine

if TYPE_CHECKING:
    from neo4j import AsyncDriver

_CAPABILITY_TYPES = frozenset({"agent", "tool", "skill"})


class SemanticLayer:
    """本体 + 图谱 → Agent 决策上下文。"""

    def __init__(self, driver: AsyncDriver) -> None:
        self.query = SemanticQueryEngine(driver)
        self.reasoning = ReasoningEngine(driver)

    async def build_decision_context(
        self,
        question: str,
        owner_id: str,
        *,
        max_depth: int = 3,
        include_inferred: bool = True,
    ) -> AgentDecisionContext:
        q = (question or "").strip()
        intent_tags = detect_intent_tags(q)
        preferred, blocked = tools_for_intents(intent_tags)

        payload = await self.reasoning.reason(
            q,
            owner_id,
            max_depth=max_depth,
            include_inferred=include_inferred,
        )
        matched = list(payload.matched_entities)

        type_codes = list({e.type_code for e in matched if e.type_code})
        tbox = await self.query.schema_compact(q, type_codes=type_codes or None)

        capability_hints: list[str] = []
        for ent in matched:
            if ent.type_code in _CAPABILITY_TYPES:
                capability_hints.append(f"{ent.type_code}:{ent.name}")
                if INTENT_CAPABILITY not in intent_tags:
                    intent_tags.append(INTENT_CAPABILITY)
                if "kg_query" not in preferred:
                    preferred = ["kg_query", *preferred]

        # 命中实体但无归属意图时，仍优先图谱
        if matched and payload.has_material and "kg_query" not in preferred:
            preferred = ["kg_query", *preferred]
            if "entity_lookup" not in intent_tags:
                intent_tags.append("entity_lookup")

        preferred = list(dict.fromkeys(preferred))
        blocked = list(dict.fromkeys(blocked))

        confidence = 0.0
        if payload.has_material:
            confidence = min(0.95, 0.4 + 0.1 * len(matched) + 0.05 * payload.relation_count)
        elif intent_tags:
            confidence = 0.35
        elif matched:
            confidence = 0.25

        return AgentDecisionContext(
            matched_entities=matched,
            abox_snippets=payload.context_text if payload.has_material else "",
            tbox_compact=tbox,
            intent_tags=intent_tags,
            preferred_tools=preferred,
            blocked_tools=blocked,
            confidence=confidence,
            has_material=payload.has_material,
            citations=list(payload.citations),
            entity_count=payload.entity_count,
            relation_count=payload.relation_count,
            reasoning_hops=payload.reasoning_hops,
            inferred_entities=payload.inferred_entities,
            capability_hints=capability_hints,
        )

    async def reason_abox(
        self,
        question: str,
        owner_id: str,
        *,
        max_depth: int = 3,
        include_inferred: bool = True,
    ):
        """直接返回推理 payload（供 kg_query 工具）。"""
        return await self.reasoning.reason(
            question,
            owner_id,
            max_depth=max_depth,
            include_inferred=include_inferred,
        )

    async def ontology_compact(self, question: str = "", type_codes: list[str] | None = None) -> str:
        return await self.query.schema_compact(question, type_codes=type_codes)
