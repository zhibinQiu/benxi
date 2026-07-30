"""通过 KgQueryService 执行多跳推理，将结果适配为 KgQaContext。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from app.schemas.kg import KgQaContext

logger = logging.getLogger(__name__)


def _payload_to_kg_context(payload: Any) -> KgQaContext:
    matched_ids = [e.id for e in (getattr(payload, "matched_entities", None) or [])]
    return KgQaContext(
        context_text=getattr(payload, "context_text", "") or "",
        citations=list(getattr(payload, "citations", None) or []),
        matched_entity_ids=matched_ids,
        entity_count=int(getattr(payload, "entity_count", 0) or 0),
        relation_count=int(getattr(payload, "relation_count", 0) or 0),
        reasoning_hops=int(getattr(payload, "reasoning_hops", 0) or 0),
        inferred_entities=int(getattr(payload, "inferred_entities", 0) or 0),
    )


class KGReasoningEngine:
    """本体感知的多跳逻辑推理引擎（KgQueryService 门面）。"""

    def __init__(self, driver: AsyncDriver) -> None:
        from app.semantic import KgQueryService, OntologyHubService

        self._kg = KgQueryService(driver)
        self._hub = OntologyHubService(kg=self._kg)

    async def reason(
        self,
        question: str,
        user_id: str,
        *,
        max_depth: int = 5,
        include_inferred: bool = True,
    ) -> KgQaContext:
        plan = await self._hub.plan_query(
            question,
            owner_id=user_id,
            max_depth=max_depth,
            include_inferred=include_inferred,
        )
        payload = await self._kg.reason(
            question,
            user_id,
            max_depth=max_depth,
            include_inferred=include_inferred,
            plan=plan,
        )
        return _payload_to_kg_context(payload)

    async def query_ontology(self, question: str) -> str:
        """语义中枢说明（概念/映射/计划），非整库 dump。"""
        return await self._hub.explain_for_tool(question or "")
