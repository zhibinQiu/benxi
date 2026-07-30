"""知识图谱（KG）服务层 — Neo4j 实现。

管理实例层（ABox）的实体/关系 CRUD，图谱可视化，与本体层（Ontology）联动验证。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from app.services.ontology_service import OntologyService

from app.core.neo4j import Neo4jBaseService
from app.core.neo4j_converter import (
    entity_node_to_out,
    relation_record_to_out,
)
from app.schemas.kg import (
    ClearOut,
    EntityIn,
    EntityOut,
    EntityUpdate,
    GraphEdgeOut,
    GraphNodeOut,
    GraphOut,
    KgQaContext,
    MetaOut,
    RelationIn,
    RelationOut,
    RelationUpdate,
)
from app.ontology.constants import type_uri as ontology_type_uri

logger = logging.getLogger(__name__)


class KgService(Neo4jBaseService):
    """知识图谱服务。

    通过 Neo4j 驱动管理实例数据，创建/查询/更新/删除实体和关系。
    自动验证 entity type_code 和 relation type_code 是否存在于 ontology。
    """

    def __init__(self, driver: AsyncDriver) -> None:
        from app.core.exceptions import service_unavailable

        def _unavailable(message: str, cause: BaseException) -> BaseException:
            return service_unavailable(message)

        super().__init__(driver, unavailable=_unavailable)
        self._ontology: OntologyService | None = None

    async def _get_ontology(self) -> OntologyService:
        if self._ontology is None:
            from app.services.ontology_factory import get_ontology_service

            self._ontology = await get_ontology_service()
        return self._ontology

    # ── 实体 CRUD ──────────────────────────────────────────────────────────

    async def create_entity(self, body: EntityIn, user_id: str) -> EntityOut:
        """创建实体实例：SHACL 校验 + 同名/别名合并复用。"""
        ontology = await self._get_ontology()
        type_code = await ontology._store.resolve_canonical_code(body.type_code)
        et = await ontology.get_entity_type(type_code, include_counts=False)
        if not et:
            raise ValueError(f"实体类型 '{body.type_code}' 不在本体定义中")

        errors = await ontology.validate_entity_properties(
            type_code, body.properties or {}, name=body.name or ""
        )
        if errors:
            raise ValueError(f"属性验证失败: {'; '.join(errors)}")

        name = body.name.strip()
        existing = await self.find_entity_by_identity(
            user_id, type_code=type_code, name=name
        )
        if existing:
            # 合并别名并返回已有实体
            await self._add_entity_alias(existing.id, name, user_id)
            return existing

        entity_id = str(uuid.uuid4())
        record = await self.run_single(
            """
            CREATE (e:Entity {
                id: $id, type_code: $type_code, type_uri: $type_uri, name: $name,
                description: $description, owner_id: $owner_id,
                properties: $properties, source_type: $source_type,
                source_document_id: $source_document_id,
                aliases: $aliases,
                created_by: $created_by,
                created_at: datetime(), updated_at: datetime()
            })
            RETURN e
            """,
            params=dict(
                id=entity_id,
                type_code=type_code,
                type_uri=ontology_type_uri(type_code),
                name=name,
                description=body.description or "",
                owner_id=user_id,
                properties=json.dumps(body.properties or {}, ensure_ascii=False),
                source_type=body.source_type or "manual",
                source_document_id=body.source_document_id or "",
                aliases=json.dumps([], ensure_ascii=False),
                created_by=user_id,
            ),
        )
        if not record:
            raise ValueError("创建实体失败")
        return entity_node_to_out(record["e"], et)

    async def find_entity_by_identity(
        self,
        user_id: str,
        *,
        type_code: str,
        name: str,
    ) -> EntityOut | None:
        """按类型 + 规范化名称/别名查找已有实体。"""
        from app.ontology.synonym_merge import normalize_label, names_match

        name_n = normalize_label(name)
        if not name_n:
            return None
        records = await self.run(
            """
            MATCH (e:Entity)
            WHERE (e.owner_id = $owner_id OR e.owner_id IS NULL)
              AND e.type_code = $type_code
            RETURN e
            LIMIT 500
            """,
            params=dict(owner_id=user_id, type_code=type_code),
        )
        for record in records:
            node = dict(record["e"])
            if names_match(str(node.get("name") or ""), name):
                return await self._enrich_entity(record["e"])
            try:
                aliases = json.loads(node.get("aliases") or "[]")
            except (TypeError, json.JSONDecodeError):
                aliases = []
            if isinstance(aliases, list):
                for a in aliases:
                    if names_match(str(a), name):
                        return await self._enrich_entity(record["e"])
        return None

    async def _add_entity_alias(self, entity_id: str, alias: str, user_id: str) -> None:
        if not alias:
            return
        record = await self.run_single(
            """
            MATCH (e:Entity {id: $id})
            WHERE e.owner_id IS NULL OR e.owner_id = $owner_id
            RETURN e
            """,
            params=dict(id=entity_id, owner_id=user_id),
        )
        if not record:
            return
        node = dict(record["e"])
        try:
            aliases = json.loads(node.get("aliases") or "[]")
        except (TypeError, json.JSONDecodeError):
            aliases = []
        if not isinstance(aliases, list):
            aliases = []
        name = str(node.get("name") or "")
        if alias == name or alias in aliases:
            return
        aliases.append(alias)
        await self.run_single(
            """
            MATCH (e:Entity {id: $id})
            SET e.aliases = $aliases, e.updated_at = datetime()
            RETURN e
            """,
            params=dict(id=entity_id, aliases=json.dumps(aliases, ensure_ascii=False)),
        )

    async def merge_entities(
        self, source_id: str, target_id: str, user_id: str
    ) -> dict[str, Any]:
        """将 source 实体合并到 target：边重挂、别名合并、删除 source。"""
        if source_id == target_id:
            raise ValueError("源与目标不能相同")
        src = await self.get_entity(source_id, user_id)
        tgt = await self.get_entity(target_id, user_id)
        if not src or not tgt:
            raise ValueError("源或目标实体不存在")

        await self._add_entity_alias(target_id, src.name, user_id)
        # 重挂出边 / 入边
        out_records = await self.run(
            """
            MATCH (s:Entity {id: $sid})-[r:RELATES]->(o:Entity)
            WHERE s.owner_id = $owner OR s.owner_id IS NULL
            RETURN r.type_code AS type_code, r.description AS description,
                   r.inferred AS inferred, o.id AS to_id, r.id AS rid
            """,
            params=dict(sid=source_id, owner=user_id),
        )
        for rec in out_records:
            await self.run_single(
                """
                MATCH (t:Entity {id: $tid})
                MATCH (o:Entity {id: $oid})
                OPTIONAL MATCH (t)-[old:RELATES {type_code: $tc}]->(o)
                FOREACH (_ IN CASE WHEN old IS NULL THEN [1] ELSE [] END |
                  CREATE (t)-[:RELATES {
                    id: $nid, type_code: $tc, description: $desc,
                    inferred: $inf, owner_id: $owner, created_at: datetime()
                  }]->(o)
                )
                WITH old
                OPTIONAL MATCH ()-[r:RELATES {id: $rid}]->()
                DELETE r
                RETURN 1 AS ok
                """,
                params=dict(
                    tid=target_id,
                    oid=rec.get("to_id"),
                    tc=rec.get("type_code"),
                    desc=rec.get("description") or "",
                    inf=bool(rec.get("inferred")),
                    owner=user_id,
                    nid=str(uuid.uuid4()),
                    rid=rec.get("rid"),
                ),
            )
        in_records = await self.run(
            """
            MATCH (o:Entity)-[r:RELATES]->(s:Entity {id: $sid})
            WHERE s.owner_id = $owner OR s.owner_id IS NULL
            RETURN r.type_code AS type_code, r.description AS description,
                   r.inferred AS inferred, o.id AS from_id, r.id AS rid
            """,
            params=dict(sid=source_id, owner=user_id),
        )
        for rec in in_records:
            await self.run_single(
                """
                MATCH (o:Entity {id: $oid})
                MATCH (t:Entity {id: $tid})
                OPTIONAL MATCH (o)-[old:RELATES {type_code: $tc}]->(t)
                FOREACH (_ IN CASE WHEN old IS NULL THEN [1] ELSE [] END |
                  CREATE (o)-[:RELATES {
                    id: $nid, type_code: $tc, description: $desc,
                    inferred: $inf, owner_id: $owner, created_at: datetime()
                  }]->(t)
                )
                WITH 1 AS _
                OPTIONAL MATCH ()-[r:RELATES {id: $rid}]->()
                DELETE r
                RETURN 1 AS ok
                """,
                params=dict(
                    tid=target_id,
                    oid=rec.get("from_id"),
                    tc=rec.get("type_code"),
                    desc=rec.get("description") or "",
                    inf=bool(rec.get("inferred")),
                    owner=user_id,
                    nid=str(uuid.uuid4()),
                    rid=rec.get("rid"),
                ),
            )
        await self.delete_entity(source_id, user_id)
        return {"source_id": source_id, "target_id": target_id}

    async def get_entity(self, entity_id: str, user_id: str) -> EntityOut | None:
        """获取实体详情。"""
        record = await self.run_single(
            """
            MATCH (e:Entity {id: $id})
            WHERE e.owner_id IS NULL OR e.owner_id = $owner_id
            RETURN e
            """,
            params=dict(id=entity_id, owner_id=user_id),
        )
        if not record:
            return None
        return await self._enrich_entity(record["e"])

    async def list_entities(
        self,
        user_id: str,
        *,
        type_code: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EntityOut]:
        """列出实体，支持类型和关键词过滤。"""
        where_clauses = ["(e.owner_id = $owner_id OR e.owner_id IS NULL)"]
        params: dict[str, Any] = {"owner_id": user_id, "limit": limit, "offset": offset}

        if type_code:
            where_clauses.append("e.type_code = $type_code")
            params["type_code"] = type_code

        if q and q.strip():
            keyword = q.strip()
            where_clauses.append(
                "(toLower(e.name) CONTAINS toLower($q) OR toLower(e.description) CONTAINS toLower($q))"
            )
            params["q"] = keyword

        where_str = " AND ".join(where_clauses)
        records = await self.run(
            f"""
            MATCH (e:Entity)
            WHERE {where_str}
            RETURN e
            ORDER BY e.updated_at DESC
            SKIP $offset LIMIT $limit
            """,
            params=params,
        )
        type_map = await self._entity_type_map()
        return [
            entity_node_to_out(record["e"], type_map.get(dict(record["e"]).get("type_code", "")))
            for record in records
        ]

    async def update_entity(
        self, entity_id: str, body: EntityUpdate, user_id: str
    ) -> EntityOut | None:
        """更新实体。"""
        sets: list[str] = []
        params: dict[str, Any] = {"id": entity_id, "owner_id": user_id}

        if body.name is not None:
            sets.append("e.name = $name")
            params["name"] = body.name.strip()
        if body.type_code is not None:
            et = await (await self._get_ontology()).get_entity_type(body.type_code)
            if not et:
                raise ValueError(f"实体类型 '{body.type_code}' 不在本体定义中")
            sets.append("e.type_code = $type_code")
            params["type_code"] = body.type_code
        if body.description is not None:
            sets.append("e.description = $description")
            params["description"] = body.description
        if body.properties is not None:
            sets.append("e.properties = $properties")
            params["properties"] = json.dumps(body.properties, ensure_ascii=False)

        if not sets:
            return await self.get_entity(entity_id, user_id)

        sets.append("e.updated_at = datetime()")
        set_clause = ", ".join(sets)
        record = await self.run_single(
            f"""
            MATCH (e:Entity {{id: $id}})
            WHERE e.owner_id IS NULL OR e.owner_id = $owner_id
            SET {set_clause}
            RETURN e
            """,
            params=params,
        )
        if not record:
            return None
        return await self._enrich_entity(record["e"])

    async def delete_entity(self, entity_id: str, user_id: str) -> bool:
        """删除实体及其关联关系。"""
        async with self._driver.session() as s:
            await s.run(
                """
                MATCH (e:Entity {id: $id})
                WHERE e.owner_id IS NULL OR e.owner_id = $owner_id
                OPTIONAL MATCH (e)-[r:RELATES]-()
                DELETE r
                """,
                id=entity_id,
                owner_id=user_id,
            )
            result = await s.run(
                """
                MATCH (e:Entity {id: $id})
                WHERE e.owner_id IS NULL OR e.owner_id = $owner_id
                DELETE e
                RETURN count(e) AS deleted
                """,
                id=entity_id,
                owner_id=user_id,
            )
            record = await result.single()
            return (record.get("deleted") or 0) > 0

    async def count_entities_by_type(self, user_id: str) -> dict[str, int]:
        """按类型统计实体数量。"""
        records = await self.run_and_collect(
            """
            MATCH (e:Entity)
            WHERE e.owner_id IS NULL OR e.owner_id = $owner_id
            RETURN e.type_code AS type, count(e) AS cnt
            """,
            params=dict(owner_id=user_id),
        )
        counts: dict[str, int] = {}
        for record in records:
            code = record.get("type", "")
            if code:
                counts[code] = record.get("cnt") or 0
        return counts

    # ── 关系 CRUD ──────────────────────────────────────────────────────────

    async def create_relation(self, body: RelationIn, user_id: str) -> RelationOut:
        """创建关系，自动验证 ontology domain/range 约束。"""
        rt = await (await self._get_ontology()).get_relation_type(body.type_code)
        if not rt:
            raise ValueError(f"关系类型 '{body.type_code}' 不在本体定义中")

        async with self._driver.session() as s:
            from_result = await s.run(
                "MATCH (e:Entity {id: $id}) RETURN e", id=body.from_entity_id
            )
            from_record = await from_result.single()
            if not from_record:
                raise ValueError(f"起点实体 '{body.from_entity_id}' 不存在")

            to_result = await s.run(
                "MATCH (e:Entity {id: $id}) RETURN e", id=body.to_entity_id
            )
            to_record = await to_result.single()
            if not to_record:
                raise ValueError(f"终点实体 '{body.to_entity_id}' 不存在")

            from_node = dict(from_record["e"])
            to_node = dict(to_record["e"])

            errors = await (await self._get_ontology()).validate_relation_domain_range(
                body.type_code, from_node.get("type_code", ""), to_node.get("type_code", "")
            )
            if errors:
                raise ValueError(f"关系约束验证失败: {'; '.join(errors)}")

            dup = await s.run(
                """
                MATCH (a:Entity {id: $from_id})-[r:RELATES {type_code: $type_code}]->(b:Entity {id: $to_id})
                RETURN r
                """,
                from_id=body.from_entity_id,
                type_code=body.type_code,
                to_id=body.to_entity_id,
            )
            if await dup.single():
                raise ValueError("相同关系已存在")

            relation_id = str(uuid.uuid4())
            result = await s.run(
                """
                MATCH (a:Entity {id: $from_id})
                MATCH (b:Entity {id: $to_id})
                CREATE (a)-[r:RELATES {
                    id: $id, type_code: $type_code,
                    description: $description, inferred: false,
                    owner_id: $owner_id, created_at: datetime()
                }]->(b)
                RETURN r, a, b
                """,
                id=relation_id,
                from_id=body.from_entity_id,
                to_id=body.to_entity_id,
                type_code=body.type_code,
                description=body.description or "",
                owner_id=user_id,
            )
            record = await result.single()
            if not record:
                raise ValueError("创建关系失败")
            return relation_record_to_out(record)

    async def list_relations(
        self,
        user_id: str,
        *,
        entity_id: str | None = None,
        type_code: str | None = None,
    ) -> list[RelationOut]:
        """列出关系，支持按实体或类型过滤。"""
        where_clauses = ["(r.owner_id = $owner_id OR r.owner_id IS NULL)"]
        params: dict[str, Any] = {"owner_id": user_id}

        if entity_id:
            where_clauses.append("(a.id = $entity_id OR b.id = $entity_id)")
            params["entity_id"] = entity_id
        if type_code:
            where_clauses.append("r.type_code = $type_code")
            params["type_code"] = type_code

        where_str = " AND ".join(where_clauses)
        records = await self.run(
            f"""
            MATCH (a)-[r:RELATES]->(b)
            WHERE {where_str}
            RETURN r, a, b
            ORDER BY r.created_at DESC
            """,
            params=params,
        )
        return [relation_record_to_out(r) for r in records]

    async def delete_relation(self, relation_id: str, user_id: str) -> bool:
        """删除关系。"""
        record = await self.run_single(
            """
            MATCH ()-[r:RELATES {id: $id}]->()
            WHERE r.owner_id = $owner_id
            DELETE r
            RETURN count(r) AS deleted
            """,
            params=dict(id=relation_id, owner_id=user_id),
        )
        return (record.get("deleted") or 0) > 0 if record else False

    async def update_relation(
        self, relation_id: str, body: RelationUpdate, user_id: str
    ) -> RelationOut | None:
        """更新关系。"""
        sets: list[str] = []
        params: dict[str, Any] = {"id": relation_id, "owner_id": user_id}

        if body.type_code is not None:
            rt = await (await self._get_ontology()).get_relation_type(body.type_code)
            if not rt:
                raise ValueError(f"关系类型 '{body.type_code}' 不在本体定义中")
            sets.append("r.type_code = $type_code")
            params["type_code"] = body.type_code
        if body.description is not None:
            sets.append("r.description = $description")
            params["description"] = body.description

        if not sets:
            # 无变更，返回当前关系
            records = await self.run(
                "MATCH (a)-[r:RELATES {id: $id}]->(b) "
                "WHERE r.owner_id = $owner_id RETURN r, a, b",
                params=params,
            )
            for record in records:
                return relation_record_to_out(record)
            return None

        sets.append("r.updated_at = datetime()")
        set_clause = ", ".join(sets)
        records = await self.run(
            f"""
            MATCH (a)-[r:RELATES {{id: $id}}]->(b)
            WHERE r.owner_id = $owner_id
            SET {set_clause}
            RETURN r, a, b
            """,
            params=params,
        )
        for record in records:
            return relation_record_to_out(record)
        return None

    # ── 图谱可视化 ──────────────────────────────────────────────────────────

    async def get_subgraph(
        self, focus_id: str, depth: int = 2, user_id: str | None = None
    ) -> GraphOut:
        """获取子图（Neo4j 原生图遍历）。

        始终返回焦点实体自身（即使没有任何关联节点）。
        """
        depth_clamped = max(1, min(int(depth), 5))
        where_clause = ""
        params: dict[str, Any] = {"focus_id": focus_id}
        if user_id:
            where_clause = (
                "WHERE (connected.owner_id IS NULL OR connected.owner_id = $owner_id)"
            )
            params["owner_id"] = user_id

        # Neo4j 不允许变长路径上下界使用参数（*1..$depth），须内联已钳制的整数
        record = await self.run_single(
            f"""
            MATCH (focus:Entity {{id: $focus_id}})
            OPTIONAL MATCH path = (focus)-[:RELATES*1..{depth_clamped}]-(connected:Entity)
            {where_clause}
            WITH focus,
                 collect(DISTINCT connected) AS conn_nodes,
                 [p IN collect(DISTINCT path) WHERE p IS NOT NULL | relationships(p)] AS path_rels
            WITH [focus] + [c IN conn_nodes WHERE c IS NOT NULL] AS all_nodes,
                 reduce(acc = [], rl IN path_rels | acc + rl) AS all_edges
            RETURN all_nodes, all_edges
            """,
            params=params,
        )
        if not record:
            return GraphOut(focus_entity_id=focus_id)

        return await self._nodes_and_edges_to_graph(
            record.get("all_nodes") or [],
            record.get("all_edges") or [],
            focus_id,
        )

    async def get_full_graph(self, user_id: str, limit: int = 300) -> GraphOut:
        """获取完整图谱（限制节点数；默认 300，供显式刷新全图）。"""
        records = await self.run(
            """
            MATCH (e:Entity)
            WHERE e.owner_id IS NULL OR e.owner_id = $owner_id
            RETURN e
            ORDER BY e.updated_at DESC
            LIMIT $limit
            """,
            params=dict(owner_id=user_id, limit=limit),
        )
        entity_ids: list[str] = []
        nodes: list[Any] = []
        for record in records:
            node = record["e"]
            nodes.append(node)
            entity_ids.append(dict(node).get("id", ""))

        if not entity_ids:
            return GraphOut()

        rel_records = await self.run(
            """
            MATCH (a:Entity)-[r:RELATES]->(b:Entity)
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN r, a, b
            """,
            params=dict(ids=entity_ids),
        )
        edges: list[dict[str, Any]] = []
        for record in rel_records:
            edges.append(
                {
                    "r": dict(record["r"]),
                    "a": dict(record["a"]),
                    "b": dict(record["b"]),
                }
            )

        return await self._build_graph_from_lists(nodes, edges)

    async def clear_user_graph(self, user_id: str) -> ClearOut:
        """清除用户的所有图谱数据。"""
        async with self._driver.session() as s:
            rel_result = await s.run(
                """
                MATCH ()-[r:RELATES]->()
                WHERE r.owner_id = $owner_id
                DELETE r
                RETURN count(r) AS deleted
                """,
                owner_id=user_id,
            )
            rel_record = await rel_result.single()
            deleted_relations = rel_record.get("deleted") or 0

            ent_result = await s.run(
                """
                MATCH (e:Entity {owner_id: $owner_id})
                DELETE e
                RETURN count(e) AS deleted
                """,
                owner_id=user_id,
            )
            ent_record = await ent_result.single()
            deleted_entities = ent_record.get("deleted") or 0

            return ClearOut(
                deleted_entities=deleted_entities,
                deleted_relations=deleted_relations,
            )

    # ── 概览 ────────────────────────────────────────────────────────────────

    async def get_meta(self, user_id: str) -> MetaOut:
        """获取知识图谱概览。"""
        entity_counts = await self.count_entities_by_type(user_id)
        relation_counts: dict[str, int] = {}

        records = await self.run_and_collect(
            """
            MATCH ()-[r:RELATES]->()
            WHERE r.owner_id IS NULL OR r.owner_id = $owner_id
            RETURN r.type_code AS type, count(r) AS cnt
            """,
            params=dict(owner_id=user_id),
        )
        for record in records:
            code = record.get("type", "")
            if code:
                relation_counts[code] = record.get("cnt") or 0

        return MetaOut(
            entity_total=sum(entity_counts.values()),
            relation_total=sum(relation_counts.values()),
            entity_type_counts=entity_counts,
            relation_type_counts=relation_counts,
        )

    # ── 辅助方法 ────────────────────────────────────────────────────────────

    async def batch_import_documents(
        self,
        documents: list[tuple[str, str, str, str]],
        *,
        prune_missing: bool = True,
    ) -> dict[str, int]:
        """全量同步文档为图谱 doc 实体：upsert 当前文档，可选清除已删文档对应实体。

        Args:
            documents: list of (id, title, description, owner_id) tuples.
            prune_missing: 为 True 时删除 source_document_id 不在当前集合中的 doc 实体。

        Returns:
            dict with imported / updated / deleted counts.
        """
        imported = 0
        updated = 0
        deleted = 0
        allowed_ids = [doc_id for doc_id, *_ in documents if doc_id]
        for doc_id, title, description, owner_id in documents:
            name = title.strip() or "未命名文档"
            desc = description or ""
            existing = await self.run_single(
                """
                MATCH (e:Entity {type_code: 'doc', source_document_id: $sid})
                RETURN e LIMIT 1
                """,
                params=dict(sid=doc_id),
            )
            if existing:
                await self.run_single(
                    """
                    MATCH (e:Entity {type_code: 'doc', source_document_id: $sid})
                    SET e.name = $name, e.description = $desc,
                        e.owner_id = $owner_id, e.updated_at = datetime()
                    RETURN e
                    """,
                    params=dict(sid=doc_id, name=name, desc=desc, owner_id=owner_id),
                )
                updated += 1
                continue
            entity_id = str(uuid.uuid4())
            try:
                await self.run_single(
                    """
                    CREATE (e:Entity {
                        id: $id, type_code: $type_code, name: $name,
                        description: $description,
                        source_type: $source_type,
                        source_document_id: $source_document_id,
                        owner_id: $owner_id,
                        created_by: $created_by,
                        created_at: datetime(), updated_at: datetime()
                    })
                    RETURN e
                    """,
                    params=dict(
                        id=entity_id,
                        type_code="doc",
                        name=name,
                        description=desc,
                        source_type="extraction",
                        source_document_id=doc_id,
                        owner_id=owner_id,
                        created_by=owner_id,
                    ),
                )
                imported += 1
            except Exception as exc:
                logger.warning("导入文档实体失败 [%s]: %s", doc_id, exc)

        if prune_missing:
            deleted = await self._prune_entities_not_in(
                prop_key="source_document_id",
                allowed_values=allowed_ids,
                extra_where="e.type_code = 'doc'",
            )

        return {
            "imported": imported,
            "updated": updated,
            "deleted": deleted,
            "skipped": 0,
        }

    # ── 平台数据同步（全量：upsert + 清除平台侧已不存在的实体/关系）──────────

    async def _upsert_platform_entity(
        self,
        session: Any,
        *,
        match_prop: str,
        match_value: str,
        type_code: str,
        name: str,
        description: str,
        owner_id: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """按平台标识 upsert Entity。properties 仅允许关键标识字段，不写业务明细。"""
        safe_props = {
            k: v
            for k, v in (properties or {}).items()
            if k in ("username", "name", "code", "title") and str(v or "").strip()
        }
        props_json = json.dumps(safe_props, ensure_ascii=False)
        existing = await session.run(
            f"MATCH (e:Entity {{{match_prop}: $v}}) RETURN e LIMIT 1",
            v=match_value,
        )
        rec = await existing.single()
        if rec:
            eid = dict(rec["e"])["id"]
            await session.run(
                f"""
                MATCH (e:Entity {{{match_prop}: $v}})
                SET e.name = $name, e.description = $desc, e.type_code = $tc,
                    e.properties = $props, e.source_type = 'system', e.owner_id = $owner,
                    e.updated_at = datetime()
                """,
                v=match_value,
                name=name,
                desc=description,
                tc=type_code,
                props=props_json,
                owner=owner_id,
            )
            return eid
        eid = str(uuid.uuid4())
        await session.run(
            f"""
            CREATE (e:Entity {{
                id: $id, type_code: $tc, name: $name, description: $desc,
                properties: $props, source_type: 'system',
                {match_prop}: $v, owner_id: $owner, created_by: $owner,
                created_at: datetime(), updated_at: datetime()
            }})
            """,
            id=eid,
            tc=type_code,
            name=name,
            desc=description,
            props=props_json,
            v=match_value,
            owner=owner_id,
        )
        return eid

    async def _prune_entities_not_in(
        self,
        *,
        prop_key: str,
        allowed_values: list[str],
        extra_where: str = "",
        owner_id: str | None = None,
    ) -> int:
        """删除带平台标识、且标识不在允许集合中的实体（含关联关系）。"""
        where_parts = [
            f"e.{prop_key} IS NOT NULL",
            f"e.{prop_key} <> ''",
            f"NOT e.{prop_key} IN $allowed",
        ]
        if extra_where:
            where_parts.append(extra_where)
        if owner_id is not None:
            where_parts.append("e.owner_id = $owner")
        where_clause = " AND ".join(where_parts)
        params: dict[str, Any] = {"allowed": list(allowed_values)}
        if owner_id is not None:
            params["owner"] = owner_id
        record = await self.run_single(
            f"""
            MATCH (e:Entity)
            WHERE {where_clause}
            WITH collect(e) AS to_delete
            FOREACH (n IN to_delete | DETACH DELETE n)
            RETURN size(to_delete) AS deleted
            """,
            params=params,
        )
        return int((record or {}).get("deleted") or 0)

    async def _rebuild_typed_relations(
        self,
        session: Any,
        *,
        type_code: str,
        pairs: list[tuple[str, str]],
        owner_id: str,
        endpoint_filter: str,
    ) -> int:
        """删除匹配端点上的旧关系后，按 pairs 重建。"""
        await session.run(
            f"""
            MATCH (a:Entity)-[r:RELATES {{type_code: $tc}}]->(b:Entity)
            WHERE {endpoint_filter}
            DELETE r
            """,
            tc=type_code,
        )
        created = 0
        for frm, to in pairs:
            if not frm or not to or frm == to:
                continue
            rid = str(uuid.uuid4())
            await session.run(
                """
                MATCH (a:Entity {id: $frm}) MATCH (b:Entity {id: $to})
                CREATE (a)-[r:RELATES {
                    id: $rid, type_code: $tc, description: '',
                    inferred: false, owner_id: $owner, created_at: datetime()
                }]->(b)
                """,
                frm=frm,
                to=to,
                rid=rid,
                tc=type_code,
                owner=owner_id,
            )
            created += 1
        return created

    async def sync_platform_org(
        self, db: Any, owner_id: str
    ) -> dict[str, int]:
        """全量同步平台用户/部门到图谱（upsert + 清除已删/停用对象及过期关系）。"""
        from app.models.org import Department, User, UserDepartment, UserStatus
        from sqlalchemy import select

        stats: dict[str, int] = {
            "departments": 0,
            "users": 0,
            "relations": 0,
            "deleted": 0,
        }

        if not await (await self._get_ontology()).get_entity_type("org"):
            logger.warning("sync_platform_org: 实体类型 'org' 尚未定义")
            return stats
        if not await (await self._get_ontology()).get_entity_type("person"):
            logger.warning("sync_platform_org: 实体类型 'person' 尚未定义")
            return stats

        dept_rows = list(
            db.scalars(
                select(Department).order_by(Department.name)
            ).all()
        )
        users = list(
            db.scalars(select(User).where(User.status == UserStatus.active.value)).all()
        )
        memberships = list(db.scalars(select(UserDepartment)).all())
        membership_map = {str(m.user_id): str(m.dept_id) for m in memberships}
        allowed_dept_ids = [str(d.id) for d in dept_rows]
        allowed_user_ids = [str(u.id) for u in users]

        async with self._driver.session() as s:
            dept_map: dict[str, str] = {}
            for dept in dept_rows:
                did = str(dept.id)
                dept_map[did] = await self._upsert_platform_entity(
                    s,
                    match_prop="platform_department_id",
                    match_value=did,
                    type_code="org",
                    name=dept.name.strip(),
                    description="组织部门",
                    owner_id=owner_id,
                )
            stats["departments"] = len(dept_map)

            person_map: dict[str, str] = {}
            for u in users:
                uid = str(u.id)
                label = (u.display_name or u.username or u.phone or "用户").strip()
                # KG 仅关键标识：名称 + username；明细属性留在事务库经问数映射查询
                key_props = {}
                if (u.username or "").strip():
                    key_props["username"] = u.username.strip()
                person_map[uid] = await self._upsert_platform_entity(
                    s,
                    match_prop="platform_user_id",
                    match_value=uid,
                    type_code="person",
                    name=label,
                    description="平台用户",
                    owner_id=owner_id,
                    properties=key_props,
                )
            stats["users"] = len(person_map)

        deleted_depts = await self._prune_entities_not_in(
            prop_key="platform_department_id",
            allowed_values=allowed_dept_ids,
        )
        deleted_users = await self._prune_entities_not_in(
            prop_key="platform_user_id",
            allowed_values=allowed_user_ids,
        )
        stats["deleted"] = deleted_depts + deleted_users

        contains_pairs: list[tuple[str, str]] = []
        for dept in dept_rows:
            if not dept.parent_id:
                continue
            parent_id = dept_map.get(str(dept.parent_id))
            child_id = dept_map.get(str(dept.id))
            if parent_id and child_id:
                contains_pairs.append((parent_id, child_id))

        employs_pairs: list[tuple[str, str]] = []
        for uid, person_id in person_map.items():
            dept_id = membership_map.get(uid)
            if not dept_id:
                continue
            dept_eid = dept_map.get(dept_id)
            if dept_eid:
                employs_pairs.append((dept_eid, person_id))

        async with self._driver.session() as s:
            contains_n = await self._rebuild_typed_relations(
                s,
                type_code="contains",
                pairs=contains_pairs,
                owner_id=owner_id,
                endpoint_filter=(
                    "a.platform_department_id IS NOT NULL "
                    "AND b.platform_department_id IS NOT NULL"
                ),
            )
            employs_n = await self._rebuild_typed_relations(
                s,
                type_code="employs",
                pairs=employs_pairs,
                owner_id=owner_id,
                endpoint_filter=(
                    "a.platform_department_id IS NOT NULL "
                    "AND b.platform_user_id IS NOT NULL"
                ),
            )
            stats["relations"] = contains_n + employs_n

        logger.info("平台组织全量同步完成: %s", stats)
        return stats

    async def sync_platform_agents(
        self, db: Any, owner_id: str
    ) -> dict[str, int]:
        """全量同步平台智能体/工具/Skill（upsert + 清除已不存在项及过期关系）。"""
        from app.core.agent_profiles import AGENT_PROFILES
        from app.services.agent_profile_service import (
            resolve_agent_internal_atomic_tools,
            resolve_agent_skill_names,
        )
        from app.services.agent_tool_registry import list_agent_tools
        from app.skills.catalog import list_all_skill_definitions

        stats: dict[str, int] = {
            "agents": 0,
            "tools": 0,
            "skills": 0,
            "relations": 0,
            "deleted": 0,
        }
        for tc in ("agent", "tool", "skill"):
            if not await (await self._get_ontology()).get_entity_type(tc):
                logger.warning("sync_platform_agents: 类型 '%s' 尚未定义", tc)
                return stats

        tools = list(list_agent_tools(db, user=None))
        skill_defs = list(
            list_all_skill_definitions(
                db, admin_view=True, include_disabled=True, catalog_only=False
            )
        )
        allowed_tools = [t.name for t in tools]
        allowed_skills = [sk.name for sk in skill_defs]
        allowed_agents = [defn.id for defn in AGENT_PROFILES]

        async with self._driver.session() as s:
            tool_map: dict[str, str] = {}
            for tool in tools:
                tname = tool.name
                tool_map[tname] = await self._upsert_platform_entity(
                    s,
                    match_prop="platform_tool_name",
                    match_value=tname,
                    type_code="tool",
                    name=tname,
                    description=(tool.description or "").strip() or "平台原子工具",
                    owner_id=owner_id,
                )
            stats["tools"] = len(tool_map)

            skill_map: dict[str, str] = {}
            for skill in skill_defs:
                sname = skill.name
                skill_map[sname] = await self._upsert_platform_entity(
                    s,
                    match_prop="platform_skill_name",
                    match_value=sname,
                    type_code="skill",
                    name=(skill.title or sname).strip()[:256],
                    description=(skill.description or "").strip() or "平台 Skill",
                    owner_id=owner_id,
                )
            stats["skills"] = len(skill_map)

            agent_map: dict[str, str] = {}
            for defn in AGENT_PROFILES:
                aid = defn.id
                agent_map[aid] = await self._upsert_platform_entity(
                    s,
                    match_prop="platform_agent_id",
                    match_value=aid,
                    type_code="agent",
                    name=defn.title.strip(),
                    description=defn.description.strip(),
                    owner_id=owner_id,
                )
            stats["agents"] = len(agent_map)

        deleted = 0
        deleted += await self._prune_entities_not_in(
            prop_key="platform_tool_name",
            allowed_values=allowed_tools,
        )
        deleted += await self._prune_entities_not_in(
            prop_key="platform_skill_name",
            allowed_values=allowed_skills,
        )
        deleted += await self._prune_entities_not_in(
            prop_key="platform_agent_id",
            allowed_values=allowed_agents,
        )
        stats["deleted"] = deleted

        has_tool_pairs: list[tuple[str, str]] = []
        has_skill_pairs: list[tuple[str, str]] = []
        for aid, agent_id in agent_map.items():
            for tname in resolve_agent_internal_atomic_tools(db, aid):
                tid = tool_map.get(tname)
                if tid:
                    has_tool_pairs.append((agent_id, tid))
            for sname in resolve_agent_skill_names(db, aid):
                sid = skill_map.get(sname)
                if sid:
                    has_skill_pairs.append((agent_id, sid))

        orchestrates_pairs: list[tuple[str, str]] = []
        for skill in skill_defs:
            sid = skill_map.get(skill.name)
            if not sid:
                continue
            for tname in skill.orchestrated_tools:
                tid = tool_map.get(tname)
                if tid:
                    orchestrates_pairs.append((sid, tid))

        async with self._driver.session() as s:
            rel_n = 0
            rel_n += await self._rebuild_typed_relations(
                s,
                type_code="has_tool",
                pairs=has_tool_pairs,
                owner_id=owner_id,
                endpoint_filter=(
                    "a.platform_agent_id IS NOT NULL "
                    "AND b.platform_tool_name IS NOT NULL"
                ),
            )
            rel_n += await self._rebuild_typed_relations(
                s,
                type_code="has_skill",
                pairs=has_skill_pairs,
                owner_id=owner_id,
                endpoint_filter=(
                    "a.platform_agent_id IS NOT NULL "
                    "AND b.platform_skill_name IS NOT NULL"
                ),
            )
            rel_n += await self._rebuild_typed_relations(
                s,
                type_code="orchestrates",
                pairs=orchestrates_pairs,
                owner_id=owner_id,
                endpoint_filter=(
                    "a.platform_skill_name IS NOT NULL "
                    "AND b.platform_tool_name IS NOT NULL"
                ),
            )
            stats["relations"] = rel_n

        logger.info("平台智能体/工具/Skill 全量同步完成: %s", stats)
        return stats

    async def sync_agent_memory_to_kg(self, user_id: str) -> dict[str, int]:
        """全量同步用户 MEMORY.md 章节为 memory 实体（更新内容并删除已移除章节）。"""
        from app.services.agent_memory_service import read_user_memory

        stats: dict[str, int] = {"entities": 0, "updated": 0, "deleted": 0}
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        memory_text = read_user_memory(uid)

        sections: list[tuple[str, str]] = []
        if memory_text.strip():
            current_title = "概述"
            current_lines: list[str] = []
            for line in memory_text.split("\n"):
                if line.startswith("## "):
                    if current_lines:
                        sections.append(
                            (current_title, "\n".join(current_lines).strip())
                        )
                    current_title = line.lstrip("#").strip()
                    current_lines = []
                else:
                    current_lines.append(line)
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))

        kept_titles: list[str] = []
        async with self._driver.session() as s:
            for title, content in sections:
                if not content:
                    continue
                safe_title = title.strip()[:256]
                kept_titles.append(safe_title)
                existing = await s.run(
                    "MATCH (e:Entity {type_code: 'memory', name: $n, owner_id: $o}) "
                    "RETURN e LIMIT 1",
                    n=safe_title,
                    o=user_id,
                )
                rec = await existing.single()
                if rec:
                    await s.run(
                        """
                        MATCH (e:Entity {type_code: 'memory', name: $n, owner_id: $o})
                        SET e.description = $desc, e.source_type = 'system',
                            e.updated_at = datetime()
                        """,
                        n=safe_title,
                        o=user_id,
                        desc=content[:500],
                    )
                    stats["updated"] += 1
                else:
                    eid = str(uuid.uuid4())
                    await s.run(
                        """
                        CREATE (e:Entity {
                            id: $id, type_code: 'memory', name: $name,
                            description: $desc, properties: '{}',
                            source_type: 'system',
                            owner_id: $owner, created_by: $owner,
                            created_at: datetime(), updated_at: datetime()
                        })
                        """,
                        id=eid,
                        name=safe_title,
                        desc=content[:500],
                        owner=user_id,
                    )
                    stats["entities"] += 1

        # 清除本用户下已不在 MEMORY.md 中的 memory 实体
        record = await self.run_single(
            """
            MATCH (e:Entity {type_code: 'memory', owner_id: $owner})
            WHERE NOT e.name IN $kept
            WITH collect(e) AS to_delete
            FOREACH (n IN to_delete | DETACH DELETE n)
            RETURN size(to_delete) AS deleted
            """,
            params=dict(owner=user_id, kept=kept_titles),
        )
        stats["deleted"] = int((record or {}).get("deleted") or 0)

        logger.info("记忆全量同步完成: %s", stats)
        return stats

    async def batch_extract_documents_from_content(
        self,
        db: Any,
        user_id: str,
        *,
        max_docs: int = 20,
        force: bool = False,
        discover_ontology: bool = True,
    ) -> dict[str, Any]:
        """批量读取已上传文档正文：可选本体发现 + 本体约束的实体/关系抽取。

        Args:
            db: SQLAlchemy session for document queries.
            user_id: 当前用户 ID.
            max_docs: 最大处理文档数（防止过度消耗 LLM token）.
            force: 为 True 时对已抽取文档也重新抽取.
            discover_ontology: 是否先发现并合并候选本体.

        Returns:
            统计信息。
        """
        from app.models.org import User
        from app.services.agent_document_service import read_document_content_for_agent
        from app.services.kg_extraction_service import (
            document_content_extracted,
            extract_kg_from_text_v2,
        )
        from sqlalchemy import select

        stats: dict[str, Any] = {
            "processed": 0,
            "skipped_already": 0,
            "total_docs": 0,
            "entities_created": 0,
            "relations_created": 0,
            "entity_types_created": 0,
            "relation_types_created": 0,
            "errors": 0,
        }

        user = db.scalar(select(User).where(User.id == uuid.UUID(user_id)))
        if not user:
            stats["error"] = "用户不存在"
            return stats

        from app.models.document import Document
        rows = db.scalars(
            select(Document).where(
                Document.deleted_at.is_(None),
                Document.owner_id == uuid.UUID(user_id),
            ).order_by(Document.created_at.desc()).limit(max_docs)
        ).all()
        stats["total_docs"] = len(rows)

        driver = self._driver
        processed = 0
        for doc in rows:
            did = str(doc.id)

            # 仅跳过「内容已抽取」的文档；doc 元数据实体存在不代表已 LLM 抽取
            if not force and await document_content_extracted(driver, did):
                stats["skipped_already"] += 1
                continue

            doc_exists = await self.run_single(
                "MATCH (e:Entity {source_document_id: $sid, type_code: 'doc'}) "
                "RETURN e LIMIT 1",
                params=dict(sid=did),
            )
            if not doc_exists:
                await self.run_single(
                    "CREATE (e:Entity {id: $id, type_code: 'doc', name: $name, "
                    "description: $desc, source_type: 'system', "
                    "source_document_id: $sid, owner_id: $owner, created_by: $owner, "
                    "created_at: datetime(), updated_at: datetime()})",
                    params=dict(
                        id=str(uuid.uuid4()),
                        name=doc.title.strip() or "未命名文档",
                        desc=(doc.description or ""),
                        sid=did, owner=user_id,
                    ),
                )

            try:
                content = read_document_content_for_agent(
                    db, user,
                    document_id=uuid.UUID(did),
                    max_chars=8000,
                )
            except Exception as exc:
                logger.debug("跳过文档 %s: 无法读取正文 (%s)", did, exc)
                continue

            full_text = (content.get("full_text") or "").strip()
            if len(full_text) < 50:
                continue

            try:
                result = await extract_kg_from_text_v2(
                    driver=driver,
                    title=doc.title or "文档",
                    text=full_text,
                    user_id=user_id,
                    source_type="extraction",
                    source_id=did,
                    discover_ontology=discover_ontology,
                )
                ont = result.get("ontology") or {}
                stats["entity_types_created"] += int(ont.get("entity_types_created") or 0)
                stats["relation_types_created"] += int(ont.get("relation_types_created") or 0)
                if not result.get("skipped", True):
                    stats["entities_created"] += result.get("entities_created", 0)
                    stats["relations_created"] += result.get("relations_created", 0)
                    processed += 1
                elif result.get("reason") in {"llm_failed", "ontology_empty"}:
                    stats["errors"] += 1
                    logger.info(
                        "文档抽取失败 [%s]: %s %s",
                        did,
                        result.get("reason"),
                        result.get("error") or "",
                    )
                else:
                    logger.info(
                        "文档抽取跳过 [%s]: %s %s",
                        did,
                        result.get("reason"),
                        result.get("error") or "",
                    )
            except Exception as exc:
                logger.warning("文档 LLM 抽取失败 [%s]: %s", did, exc)
                stats["errors"] += 1

        stats["processed"] = processed
        logger.info("批量文档内容抽取完成: %s", stats)
        return stats

    async def _entity_type_map(self) -> dict[str, Any]:
        """一次拉取全部实体类型，避免 N+1 GraphDB 查询。"""
        ontology = await self._get_ontology()
        types = await ontology.list_entity_types(include_counts=False)
        return {t.code: t for t in types}

    async def _relation_type_map(self) -> dict[str, Any]:
        ontology = await self._get_ontology()
        types = await ontology.list_relation_types(include_counts=False)
        return {t.code: t for t in types}

    async def _enrich_entity(self, node: Any) -> EntityOut:
        """将 Neo4j 节点富化为 EntityOut（附带本体类型信息）。"""
        props = dict(node)
        type_code = props.get("type_code", "")
        et = await (await self._get_ontology()).get_entity_type(type_code, include_counts=False)
        return entity_node_to_out(node, et)

    async def _nodes_and_edges_to_graph(
        self,
        nodes: list[Any],
        edges: list[Any],
        focus_id: str,
    ) -> GraphOut:
        type_map = await self._entity_type_map()
        rel_map = await self._relation_type_map()
        graph_nodes: list[GraphNodeOut] = []
        seen_ids: set[str] = set()
        for node in nodes:
            nd = dict(node)
            nid = nd.get("id", "")
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            type_code = nd.get("type_code", "")
            et = type_map.get(type_code)
            graph_nodes.append(
                GraphNodeOut(
                    id=nid,
                    name=nd.get("name", ""),
                    type_code=type_code,
                    type_label=et.label if et else type_code,
                    type_color=et.color if et else "gray",
                    type_uri=nd.get("type_uri") or ontology_type_uri(type_code),
                )
            )

        graph_edges: list[GraphEdgeOut] = []
        seen_edge_ids: set[str] = set()
        for edge in edges:
            ed = dict(edge)
            eid = ed.get("id", "")
            if eid in seen_edge_ids:
                continue
            seen_edge_ids.add(eid)
            # 从 Neo4j Relationship 对象的 start/end node 获取端点 ID
            from_id = ""
            to_id = ""
            try:
                from_id = str(dict(edge.start_node).get("id", ""))
            except Exception:
                from_id = ed.get("from_entity_id", "")
            try:
                to_id = str(dict(edge.end_node).get("id", ""))
            except Exception:
                to_id = ed.get("to_entity_id", "")
            type_code = ed.get("type_code", "")
            rt = rel_map.get(type_code)
            graph_edges.append(
                GraphEdgeOut(
                    id=eid,
                    type_code=type_code,
                    type_label=(rt.label if rt else type_code),
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    inferred=bool(ed.get("inferred", False)),
                    description=ed.get("description", ""),
                )
            )

        return GraphOut(
            nodes=graph_nodes,
            edges=graph_edges,
            focus_entity_id=focus_id,
        )

    async def _build_graph_from_lists(
        self,
        nodes: list[Any],
        edge_records: list[dict[str, Any]],
    ) -> GraphOut:
        type_map = await self._entity_type_map()
        rel_map = await self._relation_type_map()
        graph_nodes: list[GraphNodeOut] = []
        seen_ids: set[str] = set()
        for node in nodes:
            nd = dict(node)
            nid = nd.get("id", "")
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            type_code = nd.get("type_code", "")
            et = type_map.get(type_code)
            graph_nodes.append(
                GraphNodeOut(
                    id=nid,
                    name=nd.get("name", ""),
                    type_code=type_code,
                    type_label=et.label if et else type_code,
                    type_color=et.color if et else "gray",
                    type_uri=nd.get("type_uri") or ontology_type_uri(type_code),
                )
            )

        graph_edges: list[GraphEdgeOut] = []
        for rec in edge_records:
            r = rec.get("r", {})
            a = rec.get("a", {})
            b = rec.get("b", {})
            type_code = r.get("type_code", "")
            rt = rel_map.get(type_code)
            graph_edges.append(
                GraphEdgeOut(
                    id=r.get("id", ""),
                    type_code=type_code,
                    type_label=(rt.label if rt else type_code),
                    from_entity_id=a.get("id", ""),
                    to_entity_id=b.get("id", ""),
                    inferred=bool(r.get("inferred", False)),
                    description=r.get("description", ""),
                )
            )
        return GraphOut(nodes=graph_nodes, edges=graph_edges)


# ── 向后兼容函数（适配旧服务引用，使用 Neo4j 推理引擎） ──────────────────


def retrieve_kg_context_for_question(
    db_session, user, question: str, *, depth: int = 2, match_limit: int = 5
) -> KgQaContext | None:
    """向后兼容：旧服务通过此函数查询图谱。

    同步包装器，实际使用 Neo4j 推理引擎执行多跳推理。
    如果 Neo4j 不可用，返回空上下文。

    注：若从 async 上下文调用，请使用 retrieve_kg_context_for_question_async。
    """
    try:
        return asyncio.run(
            retrieve_kg_context_for_question_async(
                db_session, user, question, depth=depth, match_limit=match_limit
            )
        )
    except RuntimeError:
        # 已有运行中事件循环 → 在新线程中执行
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                retrieve_kg_context_for_question_async(
                    db_session, user, question, depth=depth, match_limit=match_limit
                ),
            )
            return future.result(timeout=30)
    except Exception:
        logger.warning("Neo4j 不可用，retrieve_kg_context_for_question 返回空")
        return KgQaContext(context_text="")


async def retrieve_kg_context_for_question_async(
    db_session, user, question: str, *, depth: int = 2, match_limit: int = 5
) -> KgQaContext | None:
    """异步版本：通过 Neo4j 推理引擎执行多跳推理。

    如果 Neo4j 不可用，返回空上下文。
    """
    try:
        from app.core.neo4j import get_neo4j
        from app.services.kg_reasoning import KGReasoningEngine

        driver = await get_neo4j()
        engine = KGReasoningEngine(driver)
        return await engine.reason(
            question=question,
            user_id=str(user.id),
            max_depth=depth,
            include_inferred=True,
        )
    except Exception:
        logger.warning("Neo4j 不可用，retrieve_kg_context_for_question_async 返回空")
        return KgQaContext(context_text="")


def ensure_ontology_defaults(db_session) -> None:
    """向后兼容：同步旧 PG 版本的本体默认值种子函数。"""
    logger.debug("ensure_ontology_defaults: PG 版已废弃，使用 ontology API 初始化")


def merge_kg_qa_into_context(
    a=None,
    b=None,
    c=None,
    *,
    base_context: str = "",
    kg_ctx=None,
) -> str:
    """将 KG 问答上下文合并到检索上下文字符串。

    兼容两种调用：
    - ``merge_kg_qa_into_context(base_context, citations, kg_ctx)``
    - ``merge_kg_qa_into_context(db, user, kg_ctx, base_context=...)``
    """
    ctx = kg_ctx
    base = base_context or ""
    if ctx is None and c is not None and hasattr(c, "context_text"):
        ctx = c
        if isinstance(a, str):
            base = a
        elif base_context:
            base = base_context
    elif ctx is None and a is not None and hasattr(a, "context_text"):
        ctx = a
    if ctx is None:
        return base
    ctx_text = (getattr(ctx, "context_text", "") or "").strip()
    if ctx_text:
        return f"{base}\n\n{ctx_text}" if base.strip() else ctx_text
    return base


def try_department_members_deterministic_reply(
    db_session, user, message: str, *, reply: str = ""
) -> str | None:
    """部门成员清单的确定性回复入口；无可靠格式化结果时返回 None。"""
    return None
