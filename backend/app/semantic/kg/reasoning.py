"""本体感知多跳推理 — 消费 QueryPlan 或内部构建 Neo4j 步骤后执行。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from app.semantic.models import MatchedEntity, Neo4jPlanStep, QueryPlan

from .neo4j_ops import Neo4jOps
from .query_engine import KgQueryEngine

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

LabelFn = Callable[[str], Awaitable[str]]


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
    evidence_paths: list[str] = field(default_factory=list)


@dataclass
class _PlanResult:
    contexts: list[dict[str, Any]] = field(default_factory=list)
    entity_ids: set[str] = field(default_factory=set)
    hops: int = 0
    inferred_entities: int = 0
    path_keys: set[str] = field(default_factory=set)


def _path_signature(rd: dict[str, Any]) -> str:
    nodes = rd.get("path_nodes") or []
    rels = rd.get("path_rels") or []
    if nodes:
        ids = []
        for n in nodes:
            if isinstance(n, dict):
                ids.append(str(n.get("id") or ""))
            else:
                ids.append(str(n))
        return "|".join(ids) + "#" + ">".join(str(r) for r in rels)
    return f"{rd.get('source_id')}|{rd.get('rel_type')}|{rd.get('target_id')}"


def _normalize_path_nodes(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in raw or []:
        if isinstance(n, dict):
            out.append(
                {
                    "id": str(n.get("id") or ""),
                    "name": str(n.get("name") or ""),
                    "type_code": str(n.get("type_code") or ""),
                }
            )
    return out


async def _format_path_text(
    rd: dict[str, Any],
    *,
    relation_label_fn: LabelFn | None = None,
) -> str | None:
    """按边真实方向渲染路径；无向遍历时逆向边画成 <-[type]-。"""
    nodes = _normalize_path_nodes(rd.get("path_nodes"))
    if len(nodes) < 2:
        return None
    edges_raw = rd.get("path_edges")
    if isinstance(edges_raw, list) and edges_raw:
        edges: list[tuple[str, bool]] = []
        for e in edges_raw:
            if isinstance(e, dict):
                edges.append(
                    (
                        str(e.get("type_code") or ""),
                        bool(e.get("forward", True)),
                    )
                )
            else:
                edges.append((str(e or ""), True))
    else:
        edges = [(str(r or ""), True) for r in (rd.get("path_rels") or [])]

    parts: list[str] = [nodes[0].get("name") or nodes[0].get("id") or "?"]
    for i, (rel, forward) in enumerate(edges):
        label = rel
        if relation_label_fn and rel:
            try:
                label = await relation_label_fn(rel)
            except Exception:
                label = rel
        edge = f"{label}/{rel}" if label and label != rel else (rel or "?")
        nxt = nodes[i + 1] if i + 1 < len(nodes) else {}
        nxt_name = nxt.get("name") or nxt.get("id") or "?"
        if forward:
            parts.append(f"-[{edge}]->")
        else:
            parts.append(f"<-[{edge}]-")
        parts.append(nxt_name)
    return " ".join(parts)


def _format_properties_line(raw: Any) -> str:
    """将实体 properties（dict 或 JSON 字符串）格式化为 phone=… 便于直答解析。"""
    import json

    props: dict[str, Any] = {}
    if isinstance(raw, dict):
        props = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                props = parsed
        except Exception:
            return ""
    if not props:
        return ""
    bits: list[str] = []
    for k, v in props.items():
        key = str(k or "").strip()
        if not key or key.startswith("_"):
            continue
        val = str(v or "").strip()
        if not val:
            continue
        bits.append(f"{key}={val}")
    return "; ".join(bits)


_EMPTY_MARKERS = ("未匹配到", "未从问题中识别", "当前图谱为空")

# 人员归属：邻接组织类型与关系类型（含无向 MATCH 下 employs 方向颠倒、互逆推理）
_ORG_TYPE_CODES = frozenset({"org", "department"})
_AFFILIATION_REL_CODES = frozenset(
    {
        "member_of",
        "part_of",
        "employs",
        "belongs_to",
        "inverse_of_employs",
        "inverse_of_member_of",
        "inverse_of_part_of",
        "inverse_of_belongs_to",
    }
)


def _is_affiliation_neighbor(rel_type: str, neighbor_type: str) -> bool:
    rt = (rel_type or "").strip()
    nt = (neighbor_type or "").strip()
    if nt not in _ORG_TYPE_CODES:
        return False
    if rt in _AFFILIATION_REL_CODES:
        return True
    if rt.startswith("inverse_of_"):
        base = rt[len("inverse_of_") :]
        return base in _AFFILIATION_REL_CODES
    return False


class ReasoningEngine:
    """多跳推理：邻域 + 传递闭包 + 互逆关系（执行层，不做语义决策）。"""

    def __init__(
        self,
        driver: AsyncDriver,
        *,
        entity_label_fn: LabelFn | None = None,
        relation_label_fn: LabelFn | None = None,
    ) -> None:
        self._ops = Neo4jOps(driver)
        self._qe = KgQueryEngine(driver)
        self._entity_label_fn = entity_label_fn
        self._relation_label_fn = relation_label_fn

    async def _entity_label(self, type_code: str) -> str:
        if self._entity_label_fn:
            return await self._entity_label_fn(type_code)
        return type_code or "?"

    async def _relation_label(self, type_code: str) -> str:
        if self._relation_label_fn:
            return await self._relation_label_fn(type_code)
        return type_code or "?"

    async def execute_steps(
        self,
        steps: list[Neo4jPlanStep],
        matched: list[MatchedEntity],
    ) -> ReasoningPayload:
        result = await self._execute_plan(steps)
        return await self._format(result, matched)

    async def execute_query_plan(
        self,
        plan: QueryPlan,
        matched: list[MatchedEntity] | None = None,
    ) -> ReasoningPayload:
        matched = list(matched or [])
        if not plan.neo4j_steps:
            return ReasoningPayload(
                context_text="【知识图谱】查询计划无 Neo4j 步骤。",
                matched_entities=matched,
                has_material=False,
            )
        return await self.execute_steps(plan.neo4j_steps, matched)

    async def reason(
        self,
        question: str,
        owner_id: str,
        *,
        max_depth: int = 5,
        include_inferred: bool = True,
        plan: QueryPlan | None = None,
        build_steps: Callable[..., Awaitable[list[Neo4jPlanStep]]] | None = None,
    ) -> ReasoningPayload:
        matched = await self._qe.match_entities_in_question(question, owner_id)
        if not matched:
            return await self._fallback(owner_id)

        if plan and plan.neo4j_steps:
            return await self.execute_steps(plan.neo4j_steps, matched)

        if build_steps is not None:
            steps = await build_steps(
                matched,
                owner_id,
                max_depth=max_depth,
                include_inferred=include_inferred,
            )
            return await self.execute_steps(steps, matched)

        # 无规划器时：仅直接邻域（不拉 TBox 传递/互逆）
        steps = [
            Neo4jPlanStep(
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
                params={"ids": [e.id for e in matched], "owner": owner_id},
            )
        ]
        return await self.execute_steps(steps, matched)

    async def _execute_plan(self, plan: list[Neo4jPlanStep]) -> _PlanResult:
        result = _PlanResult()
        seen: set[tuple[str, str, str]] = set()
        async with self._ops.driver.session() as session:
            for step in plan:
                try:
                    cursor = await session.run(step.cypher, step.params)
                    async for record in cursor:
                        rd = dict(record)
                        path_nodes = _normalize_path_nodes(rd.get("path_nodes"))
                        if path_nodes:
                            sig = _path_signature(rd)
                            if sig in result.path_keys:
                                continue
                            result.path_keys.add(sig)
                            rd["path_nodes"] = path_nodes
                            rd["path_rels"] = [str(r or "") for r in (rd.get("path_rels") or [])]
                            if rd.get("path_edges") is not None:
                                rd["path_edges"] = list(rd.get("path_edges") or [])
                            result.contexts.append(rd)
                            for n in path_nodes:
                                if n.get("id"):
                                    result.entity_ids.add(n["id"])
                        else:
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
                       e.description AS description,
                       e.properties AS properties
                """,
                {"ids": list(sorted_ids)},
            )
            for rd in rows:
                entity_details[rd["id"]] = rd
            for ent in matched:
                if ent.id not in entity_details:
                    entity_details[ent.id] = {
                        "id": ent.id,
                        "name": ent.name,
                        "type_code": ent.type_code,
                        "description": ent.description,
                        "properties": ent.props or {},
                    }

        lines: list[str] = []
        citations: list[dict[str, Any]] = []
        evidence_paths: list[str] = []
        index = 0

        # 先收集多跳路径证据（按跳数排序，最多 8 条）
        path_rows: list[tuple[int, dict[str, Any]]] = []
        for ctx in result.contexts:
            if ctx.get("path_nodes"):
                hops = int(ctx.get("hops") or 1)
                path_rows.append((hops, ctx))
        path_rows.sort(key=lambda x: (x[0], _path_signature(x[1])))
        path_entries: list[tuple[int, str, list[str]]] = []
        for hops, ctx in path_rows[:8]:
            path_text = await _format_path_text(
                ctx, relation_label_fn=self._relation_label
            )
            if not path_text:
                continue
            node_ids = [
                str(n.get("id") or "")
                for n in _normalize_path_nodes(ctx.get("path_nodes"))
                if n.get("id")
            ]
            path_entries.append((hops, path_text, node_ids))
            evidence_paths.append(path_text)
            citations.append(
                {
                    "kind": "kg_path",
                    "path_text": path_text,
                    "hops": hops,
                    "node_ids": node_ids,
                    "source": "kg",
                }
            )

        for entity_id in sorted_ids:
            detail = entity_details.get(entity_id)
            if not detail:
                continue
            index += 1
            type_code = detail.get("type_code", "")
            type_label = await self._entity_label(type_code)
            rel_lines: list[str] = []
            affiliation_orgs: list[str] = []
            for ctx in result.contexts:
                if ctx.get("path_nodes") and int(ctx.get("hops") or 1) > 1:
                    # 多跳完整路径已在证据区块展示，邻接列表只保留 1 跳边
                    continue
                rel_type = str(ctx.get("rel_type") or "?")
                rel_label = await self._relation_label(rel_type)
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
                    if _is_affiliation_neighbor(rel_type, str(target_type)):
                        affiliation_orgs.append(str(target_name))
                elif ctx.get("target_id") == entity_id:
                    source = entity_details.get(ctx.get("source_id", ""))
                    source_name = source["name"] if source else ctx.get("source_name", "?")
                    source_type = (source or {}).get("type_code") or ctx.get("source_type") or ""
                    if rel_type == "employs" and source_type in _ORG_TYPE_CODES:
                        rel_lines.append(
                            f"  → [任职于/member_of]{inferred_mark} → {source_name}"
                        )
                        affiliation_orgs.append(str(source_name))
                    else:
                        rel_lines.append(
                            f"  ← [{rel_label}/{rel_type}]{inferred_mark} ← {source_name}"
                        )
                        if _is_affiliation_neighbor(rel_type, str(source_type)):
                            affiliation_orgs.append(str(source_name))

            parts: list[str] = []
            if affiliation_orgs and type_code == "person":
                uniq = list(dict.fromkeys(affiliation_orgs))
                parts.append(f"  所属组织: {'、'.join(uniq)}")
            prop_line = _format_properties_line(detail.get("properties"))
            if prop_line:
                parts.append(f"  属性: {prop_line}")
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

        context_parts: list[str] = []
        if path_entries:
            path_block = ["【多跳证据路径】"]
            for i, (hops, path_text, _) in enumerate(path_entries, 1):
                path_block.append(f"路径{i} ({hops}跳): {path_text}")
            context_parts.append("\n".join(path_block))
        if lines:
            context_parts.append("【知识图谱推理上下文】\n" + "\n".join(lines))
        context_text = "\n\n".join(context_parts)

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
            evidence_paths=evidence_paths,
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


# 兼容：旧 CypherStep 别名
CypherStep = Neo4jPlanStep
