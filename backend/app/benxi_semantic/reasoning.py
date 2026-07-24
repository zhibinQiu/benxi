"""本体感知多跳推理 — owner_id 作用域。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .models import MatchedEntity
from .neo4j_ops import Neo4jOps
from .query_engine import SemanticQueryEngine

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


@dataclass
class CypherStep:
    description: str
    cypher: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningPayload:
    """推理结果（包内结构；宿主可映射到 KgQaContext）。"""

    context_text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    matched_entities: list[MatchedEntity] = field(default_factory=list)
    entity_count: int = 0
    relation_count: int = 0
    reasoning_hops: int = 0
    inferred_entities: int = 0
    has_material: bool = False


@dataclass
class _PlanResult:
    contexts: list[dict[str, Any]] = field(default_factory=list)
    entity_ids: set[str] = field(default_factory=set)
    hops: int = 0
    inferred_entities: int = 0


_EMPTY_MARKERS = ("未匹配到", "未从问题中识别", "当前图谱为空")


class ReasoningEngine:
    """多跳推理：邻域 + 传递闭包 + 互逆关系。"""

    def __init__(self, driver: AsyncDriver) -> None:
        self._ops = Neo4jOps(driver)
        self._qe = SemanticQueryEngine(driver)

    async def reason(
        self,
        question: str,
        owner_id: str,
        *,
        max_depth: int = 5,
        include_inferred: bool = True,
    ) -> ReasoningPayload:
        matched = await self._qe.match_entities_in_question(question, owner_id)
        if not matched:
            return await self._fallback(owner_id)

        plan = await self._build_plan(matched, owner_id, max_depth, include_inferred)
        result = await self._execute_plan(plan)
        return await self._format(result, matched)

    async def _build_plan(
        self,
        matched: list[MatchedEntity],
        owner_id: str,
        max_depth: int,
        include_inferred: bool,
    ) -> list[CypherStep]:
        steps: list[CypherStep] = []
        entity_ids = [e.id for e in matched]
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
                params={"ids": entity_ids, "owner": owner_id},
            )
        )
        if not include_inferred:
            return steps

        for rel_code in await self._qe.list_transitive_relation_codes():
            safe = rel_code.replace("'", "")
            steps.append(
                CypherStep(
                    description=f"传递推理: {safe}",
                    cypher=f"""
                        MATCH path = (a:Entity)-[:RELATES*1..{max_depth}
                            {{type_code: '{safe}'}}]-(b:Entity)
                        WHERE a.id IN $ids AND b.owner_id = $owner
                        RETURN a.id AS source_id, a.name AS source_name,
                               a.type_code AS source_type,
                               b.id AS target_id, b.name AS target_name,
                               b.type_code AS target_type,
                               length(path) AS hops,
                               '{safe}' AS rel_type,
                               true AS is_inferred
                    """,
                    params={"ids": entity_ids, "owner": owner_id},
                )
            )

        for rel_code, inverse_code in (await self._qe.list_inverse_relation_map()).items():
            safe_inv = inverse_code.replace("'", "")
            steps.append(
                CypherStep(
                    description=f"逆关系推理: {rel_code} → {safe_inv}",
                    cypher=f"""
                        MATCH (a:Entity)-[r:RELATES
                            {{type_code: '{safe_inv}'}}]->(b:Entity)
                        WHERE b.id IN $ids
                        RETURN a.id AS source_id, a.name AS source_name,
                               a.type_code AS source_type,
                               'inverse_of_{safe_inv}' AS rel_type,
                               b.id AS target_id, b.name AS target_name,
                               b.type_code AS target_type,
                               1 AS hops,
                               true AS is_inferred
                    """,
                    params={"ids": entity_ids},
                )
            )
        return steps

    async def _execute_plan(self, plan: list[CypherStep]) -> _PlanResult:
        result = _PlanResult()
        seen: set[tuple[str, str, str]] = set()
        async with self._ops.driver.session() as session:
            for step in plan:
                try:
                    cursor = await session.run(step.cypher, step.params)
                    async for record in cursor:
                        rd = dict(record)
                        source_id = rd.get("source_id") or ""
                        target_id = rd.get("target_id") or ""
                        rel_type = rd.get("rel_type") or ""
                        pair = (source_id, rel_type, target_id)
                        if pair in seen:
                            continue
                        seen.add(pair)
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

    async def _format(
        self,
        result: _PlanResult,
        matched: list[MatchedEntity],
    ) -> ReasoningPayload:
        matched_ids = {e.id for e in matched}
        # 孤立实体（无边）也要进入上下文，否则点赞 memory 等无法成材
        all_ids = set(result.entity_ids) | matched_ids
        sorted_ids = sorted(
            all_ids,
            key=lambda eid: (0 if eid in matched_ids else 1),
        )
        entity_details: dict[str, dict[str, Any]] = {}
        if sorted_ids:
            rows = await self._ops.collect(
                """
                MATCH (e:Entity) WHERE e.id IN $ids
                RETURN e.id AS id, e.name AS name,
                       e.type_code AS type_code,
                       e.description AS description
                """,
                {"ids": list(sorted_ids)},
            )
            for rd in rows:
                entity_details[rd["id"]] = rd
            # 查询失败时仍可用 match 结果兜底
            for ent in matched:
                if ent.id not in entity_details:
                    entity_details[ent.id] = {
                        "id": ent.id,
                        "name": ent.name,
                        "type_code": ent.type_code,
                        "description": ent.description,
                    }

        lines: list[str] = []
        citations: list[dict[str, Any]] = []
        index = 0
        for entity_id in sorted_ids:
            detail = entity_details.get(entity_id)
            if not detail:
                continue
            index += 1
            type_code = detail.get("type_code", "")
            type_label = await self._qe.get_entity_type_label(type_code)
            rel_lines: list[str] = []
            affiliation_orgs: list[str] = []
            for ctx in result.contexts:
                rel_type = str(ctx.get("rel_type") or "?")
                rel_label = await self._qe.get_relation_type_label(rel_type)
                inferred_mark = " [推理]" if ctx.get("is_inferred") else ""
                hops = ctx.get("hops", 1)
                hop_str = f" (跳数:{hops})" if isinstance(hops, int) and hops > 1 else ""
                if ctx.get("source_id") == entity_id:
                    target = entity_details.get(ctx.get("target_id", ""))
                    target_name = target["name"] if target else ctx.get("target_name", "?")
                    target_type = (target or {}).get("type_code") or ctx.get("target_type") or ""
                    rel_lines.append(
                        f"  → [{rel_label}/{rel_type}]{inferred_mark}{hop_str} → {target_name}"
                    )
                    if rel_type in ("member_of", "part_of") and target_type == "org":
                        affiliation_orgs.append(str(target_name))
                elif ctx.get("target_id") == entity_id:
                    source = entity_details.get(ctx.get("source_id", ""))
                    source_name = source["name"] if source else ctx.get("source_name", "?")
                    source_type = (source or {}).get("type_code") or ctx.get("source_type") or ""
                    if rel_type == "employs" and source_type == "org":
                        rel_lines.append(
                            f"  → [任职于/member_of]{inferred_mark} → {source_name}"
                        )
                        affiliation_orgs.append(str(source_name))
                    else:
                        rel_lines.append(
                            f"  ← [{rel_label}/{rel_type}]{inferred_mark} ← {source_name}"
                        )

            parts: list[str] = []
            if affiliation_orgs and type_code == "person":
                uniq = list(dict.fromkeys(affiliation_orgs))
                parts.append(f"  所属组织: {'、'.join(uniq)}")
            desc = (detail.get("description") or "").strip()
            if desc:
                parts.append(f"  描述: {desc}")
            if rel_lines:
                parts.append("  关联:")
                parts.extend(rel_lines)

            title = f"[{index}] {type_label} · {detail.get('name', '?')}"
            lines.append(title)
            if parts:
                lines.extend(parts)
            lines.append("")
            citations.append(
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

        return ReasoningPayload(
            context_text=context_text,
            citations=citations,
            matched_entities=matched,
            entity_count=len(result.entity_ids),
            relation_count=len(result.contexts),
            reasoning_hops=result.hops or 0,
            inferred_entities=result.inferred_entities,
            has_material=bool(matched) and bool(context_text)
            and not any(m in context_text for m in _EMPTY_MARKERS),
        )

    async def _fallback(self, owner_id: str) -> ReasoningPayload:
        cnt = await self._ops.count(
            "MATCH (e:Entity {owner_id: $owner_id}) RETURN count(e) AS cnt",
            {"owner_id": owner_id},
        )
        if cnt == 0:
            text = "【知识图谱】当前图谱为空，未匹配到相关实体。"
        else:
            text = "【知识图谱】未从问题中识别到具体实体，请提供更详细的问题。"
        return ReasoningPayload(context_text=text, has_material=False)
