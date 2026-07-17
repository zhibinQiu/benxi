"""本体感知的多跳逻辑推理引擎 — Agentic KG-RAG 核心。

根据用户问题匹配的实体和本体定义（传递性、互逆关系、公理），
自动构建多步 Cypher 推理计划并执行，返回结构化上下文。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from app.agentkit.graph import Neo4jBaseService
from app.schemas.kg import KgQaContext
from app.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)


@dataclass
class CypherStep:
    """推理步骤。"""

    description: str
    cypher: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningResult:
    """推理结果。"""

    contexts: list[dict[str, Any]] = field(default_factory=list)
    entity_ids: set[str] = field(default_factory=set)
    relation_ids: set[str] = field(default_factory=set)
    hops: int = 0
    inferred_entities: int = 0


class KGReasoningEngine(Neo4jBaseService):
    """本体感知的多跳逻辑推理引擎。

    用法:
        engine = KGReasoningEngine(driver)
        ctx = await engine.reason(question="哪些指标受碳排放管理办法约束？", user_id="...")
    """

    def __init__(self, driver: AsyncDriver) -> None:
        super().__init__(driver)
        self._ontology = OntologyService(driver)

    async def reason(
        self,
        question: str,
        user_id: str,
        *,
        max_depth: int = 5,
        include_inferred: bool = True,
    ) -> KgQaContext:
        """对自然语言问题执行多跳推理。

        Args:
            question: 用户问题
            user_id: 用户 ID
            max_depth: 推理最大深度
            include_inferred: 是否包含推理结果

        Returns:
            KgQaContext: 格式化后的推理上下文
        """
        matched_entities = await self._match_entities_in_question(question, user_id)

        if not matched_entities:
            return await self._fallback_context(user_id)

        plan = await self._build_reasoning_plan(
            matched_entities, user_id, max_depth, include_inferred
        )

        result = await self._execute_plan(plan)

        context = await self._build_context(
            result, matched_entities, question, user_id
        )
        return context

    async def _match_entities_in_question(
        self, question: str, user_id: str
    ) -> list[dict[str, Any]]:
        """从问题文本中匹配用户图谱实体。"""
        q = (question or "").strip().lower()
        if not q:
            return []

        records = await self.run_and_collect(
            """
            MATCH (e:Entity {owner_id: $owner_id})
            RETURN e.id AS id, e.name AS name,
                   e.type_code AS type_code,
                   e.description AS description
            """,
            params=dict(owner_id=user_id),
        )
        candidates: list[dict[str, Any]] = []
        for record in records:
            name = (record.get("name") or "").strip().lower()
            desc = (record.get("description") or "").strip().lower()
            score = 0.0
            if name and name in q:
                score = 100.0 + len(name)
            if score == 0 and desc and len(desc) >= 4 and desc[:16] in q:
                score = 10.0
            if score > 0:
                candidates.append(
                    {
                        "id": record.get("id"),
                        "name": record.get("name"),
                        "type_code": record.get("type_code"),
                        "score": score,
                    }
                )

        candidates.sort(key=lambda x: (-x["score"], -len(x["name"])))
        return candidates[:5]

    async def _build_reasoning_plan(
        self,
        matched_entities: list[dict[str, Any]],
        user_id: str,
        max_depth: int,
        include_inferred: bool,
    ) -> list[CypherStep]:
        """根据匹配实体和本体定义，构建多步推理计划。"""
        steps: list[CypherStep] = []
        entity_ids = [e["id"] for e in matched_entities]

        # Step 1: 直接邻域查询
        steps.append(
            CypherStep(
                description="直接关联实体",
                cypher="""
                    MATCH (a:Entity)-[r:RELATES]-(b:Entity)
                    WHERE a.id IN $ids AND b.owner_id = $owner
                    RETURN a.id AS source_id, a.name AS source_name,
                           a.type_code AS source_type,
                           r.id AS rel_id, r.type_code AS rel_type,
                           r.description AS rel_desc, r.inferred AS rel_inferred,
                           b.id AS target_id, b.name AS target_name,
                           b.type_code AS target_type
                """,
                params={"ids": entity_ids, "owner": user_id},
            )
        )

        if not include_inferred:
            return steps

        # Step 2: 传递闭包推理
        transitive_rels = await self._ontology.get_transitive_relation_types()
        for rel_code in transitive_rels:
            steps.append(
                CypherStep(
                    description=f"传递推理: {rel_code}",
                    cypher=f"""
                        MATCH path = (a:Entity)-[:RELATES*1..{max_depth}
                            {{type_code: '{rel_code}'}}]-(b:Entity)
                        WHERE a.id IN $ids AND b.owner_id = $owner
                        RETURN a.id AS source_id, a.name AS source_name,
                               a.type_code AS source_type,
                               b.id AS target_id, b.name AS target_name,
                               b.type_code AS target_type,
                               length(path) AS hops,
                               '{rel_code}' AS rel_type,
                               true AS is_inferred
                    """,
                    params={"ids": entity_ids, "owner": user_id},
                )
            )

        # Step 3: 逆关系推理
        inverse_map = await self._ontology.get_inverse_relation_types()
        for rel_code, inverse_code in inverse_map.items():
            steps.append(
                CypherStep(
                    description=f"逆关系推理: {rel_code} → {inverse_code}",
                    cypher=f"""
                        MATCH (a:Entity)-[r:RELATES
                            {{type_code: '{inverse_code}'}}]->(b:Entity)
                        WHERE b.id IN $ids
                        RETURN a.id AS source_id, a.name AS source_name,
                               a.type_code AS source_type,
                               'inverse_of_{inverse_code}' AS rel_type,
                               b.id AS target_id, b.name AS target_name,
                               b.type_code AS target_type,
                               1 AS hops,
                               true AS is_inferred
                    """,
                    params={"ids": entity_ids},
                )
            )

        return steps

    async def _execute_plan(self, plan: list[CypherStep]) -> ReasoningResult:
        """执行推理计划，合并结果。"""
        result = ReasoningResult()
        seen_pairs: set[tuple[str, str, str]] = set()

        async with self._driver.session() as s:
            for step in plan:
                try:
                    cursor = await s.run(step.cypher, step.params)
                    async for record in cursor:
                        rd = dict(record)
                        source_id = rd.get("source_id") or ""
                        target_id = rd.get("target_id") or ""
                        rel_type = rd.get("rel_type") or ""
                        pair_key = (source_id, rel_type, target_id)

                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            result.contexts.append(rd)
                            if source_id:
                                result.entity_ids.add(source_id)
                            if target_id:
                                result.entity_ids.add(target_id)
                            if rd.get("is_inferred"):
                                result.inferred_entities += 1
                            hops = rd.get("hops") or 1
                            if isinstance(hops, int):
                                result.hops = max(result.hops, hops)
                except Exception as exc:
                    logger.warning("推理步骤失败 %s: %s", step.description, exc)

        return result

    async def _build_context(
        self,
        result: ReasoningResult,
        matched_entities: list[dict[str, Any]],
        question: str,
        user_id: str,
    ) -> KgQaContext:
        """将推理结果格式化为问答上下文。"""
        matched_ids = {e["id"] for e in matched_entities}

        all_entity_ids = list(result.entity_ids)
        sorted_entity_ids = sorted(
            all_entity_ids,
            key=lambda eid: (0 if eid in matched_ids else 1),
        )

        entity_details: dict[str, dict[str, Any]] = {}
        if sorted_entity_ids:
            records = await self.run_and_collect(
                """
                MATCH (e:Entity) WHERE e.id IN $ids
                RETURN e.id AS id, e.name AS name,
                       e.type_code AS type_code,
                       e.description AS description,
                       e.properties AS properties
                """,
                params=dict(ids=sorted_entity_ids),
            )
            for rd in records:
                entity_details[rd["id"]] = rd

        lines: list[str] = []
        citation_sources: list[dict[str, Any]] = []
        index = 0

        for entity_id in sorted_entity_ids:
            detail = entity_details.get(entity_id)
            if not detail:
                continue
            index += 1
            type_code = detail.get("type_code", "")
            et = await self._ontology.get_entity_type(type_code)

            rel_lines: list[str] = []
            for ctx in result.contexts:
                if ctx.get("source_id") == entity_id:
                    target = entity_details.get(ctx.get("target_id", ""))
                    target_name = target["name"] if target else ctx.get("target_name", "?")
                    rel_type = ctx.get("rel_type", "?")
                    inferred_mark = " [推理]" if ctx.get("is_inferred") else ""
                    hops = ctx.get("hops", 1)
                    hop_str = f" (跳数:{hops})" if hops > 1 else ""
                    rel_lines.append(
                        f"  → [{rel_type}]{inferred_mark}{hop_str} → {target_name}"
                    )
                elif ctx.get("target_id") == entity_id:
                    source = entity_details.get(ctx.get("source_id", ""))
                    source_name = source["name"] if source else ctx.get("source_name", "?")
                    rel_type = ctx.get("rel_type", "?")
                    inferred_mark = " [推理]" if ctx.get("is_inferred") else ""
                    rel_lines.append(
                        f"  ← [{rel_type}]{inferred_mark} ← {source_name}"
                    )

            desc = (detail.get("description") or "").strip()
            parts: list[str] = []
            if desc:
                parts.append(f"  描述: {desc}")
            if rel_lines:
                parts.append("  关联:")
                parts.extend(rel_lines)

            type_label = et.label if et else type_code
            title = f"[{index}] {type_label} · {detail.get('name', '?')}"
            lines.append(title)
            if parts:
                lines.extend(parts)
            lines.append("")

            citation_sources.append(
                {
                    "index": index,
                    "title": title,
                    "entity_id": entity_id,
                    "type_label": type_label,
                    "source": "kg",
                }
            )

        context_text = ""
        if lines:
            context_text = "【知识图谱推理上下文】\n" + "\n".join(lines)

        return KgQaContext(
            context_text=context_text,
            citations=citation_sources,
            matched_entity_ids=list(matched_ids),
            entity_count=len(all_entity_ids),
            relation_count=len(result.contexts),
            reasoning_hops=result.hops or 0,
            inferred_entities=result.inferred_entities,
        )

    async def query_ontology(self, question: str) -> str:
        """查询本体定义（实体类型列表、关系类型约束等）。"""
        entity_types = await self._ontology.list_entity_types()
        relation_types = await self._ontology.list_relation_types()

        lines: list[str] = ["【本体定义（Ontology Schema）】"]

        lines.append("\n## 实体类型")
        for et in entity_types:
            required = [
                k for k, v in (et.property_schema or {}).items() if v.required
            ]
            req_str = f" [必需属性: {', '.join(required)}]" if required else ""
            lines.append(f"- {et.code} ({et.label}){req_str}")

        lines.append("\n## 关系类型")
        for rt in relation_types:
            domain = f" domain:{rt.domain_types}" if rt.domain_types else ""
            range_ = f" range:{rt.range_types}" if rt.range_types else ""
            trans = " [传递]" if rt.transitive else ""
            inv = f" [互逆:{rt.inverse_of}]" if rt.inverse_of else ""
            lines.append(f"- {rt.code} ({rt.label}){domain}{range_}{trans}{inv}")

        return "\n".join(lines)

    async def _fallback_context(self, user_id: str) -> KgQaContext:
        """兜底：返回用户图谱概览。"""
        cnt = await self.count_query(
            "MATCH (e:Entity {owner_id: $owner_id}) RETURN count(e) AS cnt",
            params=dict(owner_id=user_id),
        )

        if cnt == 0:
            return KgQaContext(
                context_text="【知识图谱】当前图谱为空，未匹配到相关实体。",
            )

        return KgQaContext(
            context_text="【知识图谱】未从问题中识别到具体实体，请提供更详细的问题。",
            entity_count=cnt,
        )
