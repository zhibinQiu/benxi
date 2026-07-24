"""语义查询引擎 — 适配本析 Entity / RELATES / Ontology* 图模型。"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .models import (
    GraphStats,
    MatchedEntity,
    NeighborHit,
    PathHop,
    PathResult,
)
from .neo4j_ops import Neo4jOps

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][\w.-]{1,}", re.UNICODE)


def question_match_tokens(question: str, *, max_tokens: int = 48) -> list[str]:
    """从问题提取用于实体匹配的 token（长度≥2），保序去重。

    连续中文串额外切出 2～4 字窗口（常见姓名/专名长度），供精确名匹配。
    """
    q = (question or "").strip()
    if not q:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def _add(tok: str) -> bool:
        t = tok.strip().lower()
        if len(t) < 2 or t in seen:
            return len(out) < max_tokens
        seen.add(t)
        out.append(t)
        return len(out) < max_tokens

    for m in _TOKEN_RE.finditer(q):
        raw = m.group(0)
        if not _add(raw):
            return out
        # 中文连续串：优先长窗口，再短窗口
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", raw):
            for n in (4, 3, 2):
                if len(raw) < n:
                    continue
                for i in range(0, len(raw) - n + 1):
                    if not _add(raw[i : i + n]):
                        return out
    return out


class SemanticQueryEngine:
    """本体感知查询：语义搜索、邻居、路径、统计、精简 schema。"""

    def __init__(self, driver: AsyncDriver) -> None:
        self._ops = Neo4jOps(driver)

    async def semantic_search(
        self,
        query: str,
        owner_id: str,
        *,
        limit: int = 10,
    ) -> list[MatchedEntity]:
        q = (query or "").strip()
        if not q or not owner_id:
            return []
        rows = await self._ops.collect(
            """
            MATCH (e:Entity {owner_id: $owner_id})
            WHERE toLower(coalesce(e.name, '')) CONTAINS toLower($q)
               OR toLower(coalesce(e.description, '')) CONTAINS toLower($q)
            RETURN e.id AS id, e.name AS name,
                   e.type_code AS type_code,
                   e.description AS description
            LIMIT $limit
            """,
            {"owner_id": owner_id, "q": q, "limit": limit},
        )
        out: list[MatchedEntity] = []
        q_l = q.lower()
        for row in rows:
            name = str(row.get("name") or "")
            score = 50.0 + len(name) if name.lower() in q_l else 20.0
            out.append(
                MatchedEntity(
                    id=str(row.get("id") or ""),
                    name=name,
                    type_code=str(row.get("type_code") or ""),
                    score=score,
                    description=str(row.get("description") or ""),
                )
            )
        out.sort(key=lambda x: (-x.score, -len(x.name)))
        return out[:limit]

    async def match_entities_in_question(
        self,
        question: str,
        owner_id: str,
        *,
        limit: int = 5,
    ) -> list[MatchedEntity]:
        """实体名出现在问题中：在 Neo4j 侧过滤，禁止全量拉取实体到 Python。"""
        q_raw = (question or "").strip()
        q = q_raw.lower()
        if not q or not owner_id:
            return []
        tokens = question_match_tokens(q_raw)
        # 拉取上限略大于 limit，便于本地按 name 长度精排
        fetch_limit = max(limit * 4, 20)
        rows = await self._ops.collect(
            """
            MATCH (e:Entity {owner_id: $owner_id})
            WHERE size(coalesce(e.name, '')) >= 2
              AND (
                any(t IN $tokens WHERE toLower(e.name) = t)
                OR toLower($q) CONTAINS toLower(e.name)
                OR (
                  e.type_code = 'memory'
                  AND any(t IN $tokens WHERE size(t) >= 2 AND toLower(e.name) CONTAINS t)
                )
              )
            RETURN e.id AS id, e.name AS name,
                   e.type_code AS type_code,
                   e.description AS description
            ORDER BY size(e.name) DESC
            LIMIT $limit
            """,
            {
                "owner_id": owner_id,
                "q": q,
                "tokens": tokens,
                "limit": fetch_limit,
            },
        )
        candidates: list[MatchedEntity] = []
        for row in rows:
            name = (row.get("name") or "").strip()
            name_l = name.lower()
            if not name_l:
                continue
            score = 0.0
            if name_l in q:
                score = 100.0 + len(name_l)
            elif name_l in tokens:
                score = 90.0 + len(name_l)
            else:
                continue
            candidates.append(
                MatchedEntity(
                    id=str(row.get("id") or ""),
                    name=name,
                    type_code=str(row.get("type_code") or ""),
                    score=score,
                    description=str(row.get("description") or ""),
                )
            )
        candidates.sort(key=lambda x: (-x.score, -len(x.name)))
        return candidates[:limit]

    async def get_neighbors(
        self,
        entity_name_or_id: str,
        owner_id: str,
        *,
        depth: int = 1,
        limit: int = 30,
    ) -> list[NeighborHit]:
        key = (entity_name_or_id or "").strip()
        if not key or not owner_id:
            return []
        depth = max(1, min(int(depth), 3))
        rows = await self._ops.collect(
            f"""
            MATCH (e:Entity {{owner_id: $owner_id}})
            WHERE e.id = $key OR e.name = $key
            WITH e
            MATCH path = (e)-[:RELATES*1..{depth}]-(n:Entity)
            WHERE n.owner_id = $owner_id
            WITH n, relationships(path) AS rels, length(path) AS dist
            RETURN n.id AS id, n.name AS name, n.type_code AS type_code,
                   dist AS distance,
                   CASE WHEN size(rels) > 0 THEN rels[0].type_code ELSE '' END AS relation_type
            LIMIT $limit
            """,
            {"owner_id": owner_id, "key": key, "limit": limit},
        )
        return [
            NeighborHit(
                id=str(r.get("id") or ""),
                name=str(r.get("name") or ""),
                type_code=str(r.get("type_code") or ""),
                relation_type=str(r.get("relation_type") or ""),
                distance=int(r.get("distance") or 1),
            )
            for r in rows
        ]

    async def find_path(
        self,
        start: str,
        end: str,
        owner_id: str,
        *,
        max_depth: int = 3,
        limit: int = 5,
    ) -> list[PathResult]:
        s = (start or "").strip()
        e = (end or "").strip()
        if not s or not e or not owner_id:
            return []
        max_depth = max(1, min(int(max_depth), 5))
        rows = await self._ops.collect(
            f"""
            MATCH (a:Entity {{owner_id: $owner_id}}), (b:Entity {{owner_id: $owner_id}})
            WHERE (a.id = $start OR a.name = $start)
              AND (b.id = $end OR b.name = $end)
            MATCH path = shortestPath((a)-[:RELATES*1..{max_depth}]-(b))
            RETURN [n IN nodes(path) | {{
                id: n.id, name: n.name, type_code: n.type_code
            }}] AS nodes,
            [r IN relationships(path) | r.type_code] AS rels
            LIMIT $limit
            """,
            {"owner_id": owner_id, "start": s, "end": e, "limit": limit},
        )
        results: list[PathResult] = []
        for row in rows:
            nodes = row.get("nodes") or []
            rels = row.get("rels") or []
            hops: list[PathHop] = []
            for i, node in enumerate(nodes):
                if not isinstance(node, dict):
                    continue
                rel = rels[i - 1] if i > 0 and i - 1 < len(rels) else ""
                hops.append(
                    PathHop(
                        entity_id=str(node.get("id") or ""),
                        entity_name=str(node.get("name") or ""),
                        type_code=str(node.get("type_code") or ""),
                        relation_type=str(rel or ""),
                    )
                )
            results.append(PathResult(hops=hops, length=max(0, len(hops) - 1)))
        return results

    async def get_graph_statistics(self, owner_id: str) -> GraphStats:
        total_e = await self._ops.count(
            "MATCH (e:Entity {owner_id: $owner_id}) RETURN count(e) AS cnt",
            {"owner_id": owner_id},
        )
        total_r = await self._ops.count(
            """
            MATCH (:Entity {owner_id: $owner_id})-[r:RELATES]-()
            RETURN count(DISTINCT r) AS cnt
            """,
            {"owner_id": owner_id},
        )
        et_rows = await self._ops.collect(
            """
            MATCH (e:Entity {owner_id: $owner_id})
            RETURN e.type_code AS type_code, count(*) AS cnt
            """,
            {"owner_id": owner_id},
        )
        rt_rows = await self._ops.collect(
            """
            MATCH (:Entity {owner_id: $owner_id})-[r:RELATES]-()
            RETURN r.type_code AS type_code, count(DISTINCT r) AS cnt
            """,
            {"owner_id": owner_id},
        )
        return GraphStats(
            total_entities=total_e,
            total_relations=total_r,
            entity_type_counts={
                str(r.get("type_code") or ""): int(r.get("cnt") or 0) for r in et_rows
            },
            relation_type_counts={
                str(r.get("type_code") or ""): int(r.get("cnt") or 0) for r in rt_rows
            },
        )

    async def schema_compact(
        self,
        question: str = "",
        *,
        type_codes: list[str] | None = None,
        limit_types: int = 12,
    ) -> str:
        """精简 TBox 文本；可按问题关键词或已命中 type_codes 过滤。"""
        et_rows = await self._ops.collect(
            """
            MATCH (et:OntologyEntityType)
            RETURN et.code AS code, et.label AS label
            ORDER BY coalesce(et.sort_order, 100)
            """
        )
        rt_rows = await self._ops.collect(
            """
            MATCH (rt:OntologyRelationType)
            RETURN rt.code AS code, rt.label AS label,
                   rt.domain_types AS domain_types,
                   rt.range_types AS range_types,
                   rt.transitive AS transitive,
                   rt.inverse_of AS inverse_of
            ORDER BY coalesce(rt.sort_order, 100)
            """
        )
        wanted = {c for c in (type_codes or []) if c}
        q = (question or "").strip().lower()
        if q and not wanted:
            for row in et_rows:
                code = str(row.get("code") or "")
                label = str(row.get("label") or "")
                if code and (code in q or label.lower() in q):
                    wanted.add(code)
            # 常见归属问题：自动带上 person/org
            if any(k in q for k in ("公司", "部门", "组织", "任职", "成员", "谁")):
                wanted.update({"person", "org"})

        def _keep_et(row: dict[str, Any]) -> bool:
            if not wanted:
                return True
            return str(row.get("code") or "") in wanted

        filtered_et = [r for r in et_rows if _keep_et(r)][:limit_types]
        et_codes = {str(r.get("code") or "") for r in filtered_et}

        def _keep_rt(row: dict[str, Any]) -> bool:
            if not wanted:
                return True
            domains = row.get("domain_types") or []
            ranges = row.get("range_types") or []
            if not domains and not ranges:
                return True
            codes = set(domains or []) | set(ranges or [])
            return bool(codes & et_codes)

        filtered_rt = [r for r in rt_rows if _keep_rt(r)][: limit_types * 2]

        lines = ["【本体摘要（相关类型）】", "## 实体类型"]
        for r in filtered_et:
            lines.append(f"- {r.get('code')} ({r.get('label')})")
        lines.append("## 关系类型")
        for r in filtered_rt:
            domain = f" domain:{r.get('domain_types')}" if r.get("domain_types") else ""
            range_ = f" range:{r.get('range_types')}" if r.get("range_types") else ""
            trans = " [传递]" if r.get("transitive") else ""
            inv = f" [互逆:{r.get('inverse_of')}]" if r.get("inverse_of") else ""
            lines.append(
                f"- {r.get('code')} ({r.get('label')}){domain}{range_}{trans}{inv}"
            )
        return "\n".join(lines)

    async def list_transitive_relation_codes(self) -> list[str]:
        rows = await self._ops.collect(
            """
            MATCH (rt:OntologyRelationType)
            WHERE rt.transitive = true
            RETURN rt.code AS code
            """
        )
        return [str(r.get("code") or "") for r in rows if r.get("code")]

    async def list_inverse_relation_map(self) -> dict[str, str]:
        rows = await self._ops.collect(
            """
            MATCH (rt:OntologyRelationType)
            WHERE rt.inverse_of IS NOT NULL AND rt.inverse_of <> ''
            RETURN rt.code AS code, rt.inverse_of AS inverse_of
            """
        )
        return {
            str(r.get("code") or ""): str(r.get("inverse_of") or "")
            for r in rows
            if r.get("code") and r.get("inverse_of")
        }

    async def get_entity_type_label(self, type_code: str) -> str:
        rows = await self._ops.collect(
            """
            MATCH (et:OntologyEntityType {code: $code})
            RETURN et.label AS label
            LIMIT 1
            """,
            {"code": type_code},
        )
        if rows and rows[0].get("label"):
            return str(rows[0]["label"])
        return type_code

    async def get_relation_type_label(self, type_code: str) -> str:
        code = (type_code or "").removeprefix("inverse_of_")
        rows = await self._ops.collect(
            """
            MATCH (rt:OntologyRelationType {code: $code})
            RETURN rt.label AS label
            LIMIT 1
            """,
            {"code": code},
        )
        if rows and rows[0].get("label"):
            return str(rows[0]["label"])
        return type_code
