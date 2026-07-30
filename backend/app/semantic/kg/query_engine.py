"""知识图谱 ABox 查询引擎 — 仅 Neo4j 事实，不含 TBox 决策。"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from app.semantic.models import (
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
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", raw):
            for n in (4, 3, 2):
                if len(raw) < n:
                    continue
                for i in range(0, len(raw) - n + 1):
                    if not _add(raw[i : i + n]):
                        return out
    return out


class KgQueryEngine:
    """ABox：语义搜索、邻居、路径、统计。"""

    def __init__(self, driver: AsyncDriver) -> None:
        self._ops = Neo4jOps(driver)

    @property
    def ops(self) -> Neo4jOps:
        return self._ops

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
                   e.description AS description,
                   e.platform_user_id AS platform_user_id,
                   e.platform_department_id AS platform_department_id
            LIMIT $limit
            """,
            {"owner_id": owner_id, "q": q, "limit": limit},
        )
        out: list[MatchedEntity] = []
        q_l = q.lower()
        for row in rows:
            name = str(row.get("name") or "")
            score = 50.0 + len(name) if name.lower() in q_l else 20.0
            props: dict[str, Any] = {}
            if row.get("platform_user_id"):
                props["platform_user_id"] = str(row["platform_user_id"])
            if row.get("platform_department_id"):
                props["platform_department_id"] = str(row["platform_department_id"])
            out.append(
                MatchedEntity(
                    id=str(row.get("id") or ""),
                    name=name,
                    type_code=str(row.get("type_code") or ""),
                    score=score,
                    description=str(row.get("description") or ""),
                    props=props,
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
        type_codes: list[str] | None = None,
    ) -> list[MatchedEntity]:
        """实体名出现在问题中：在 Neo4j 侧过滤，禁止全量拉取实体到 Python。

        type_codes：本体解析出的概念类型。有则优先保留这些类型，
        但仍保留问题中按名称命中的其它类型实例（主体专名）。
        """
        q_raw = (question or "").strip()
        q = q_raw.lower()
        if not q or not owner_id:
            return []
        tokens = question_match_tokens(q_raw)
        type_set = {str(t).strip() for t in (type_codes or []) if str(t).strip()}
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
                   e.description AS description,
                   e.platform_user_id AS platform_user_id,
                   e.platform_department_id AS platform_department_id
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
            type_code = str(row.get("type_code") or "")
            # 本体类型命中加权；不硬排除名称命中的其它类型
            if type_set and type_code in type_set:
                score += 25.0
            props: dict[str, Any] = {}
            if row.get("platform_user_id"):
                props["platform_user_id"] = str(row["platform_user_id"])
            if row.get("platform_department_id"):
                props["platform_department_id"] = str(row["platform_department_id"])
            candidates.append(
                MatchedEntity(
                    id=str(row.get("id") or ""),
                    name=name,
                    type_code=type_code,
                    score=score,
                    description=str(row.get("description") or ""),
                    props=props,
                )
            )
        candidates.sort(
            key=lambda x: (
                0 if (not type_set or x.type_code in type_set) else 1,
                -x.score,
                -len(x.name),
            )
        )
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


# 对外别名：历史调用方仍可使用 SemanticQueryEngine
SemanticQueryEngine = KgQueryEngine
