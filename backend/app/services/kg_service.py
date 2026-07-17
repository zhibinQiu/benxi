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

from app.agentkit.graph import (
    Neo4jBaseService,
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
from app.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)


class KgService(Neo4jBaseService):
    """知识图谱服务。

    通过 Neo4j 驱动管理实例数据，创建/查询/更新/删除实体和关系。
    自动验证 entity type_code 和 relation type_code 是否存在于 ontology。
    """

    def __init__(self, driver: AsyncDriver) -> None:
        super().__init__(driver)
        self._ontology: OntologyService | None = None

    @property
    def ontology(self) -> OntologyService:
        if self._ontology is None:
            self._ontology = OntologyService(self._driver)
        return self._ontology

    # ── 实体 CRUD ──────────────────────────────────────────────────────────

    async def create_entity(self, body: EntityIn, user_id: str) -> EntityOut:
        """创建实体实例，自动验证 ontology type_code。"""
        et = await self.ontology.get_entity_type(body.type_code)
        if not et:
            raise ValueError(f"实体类型 '{body.type_code}' 不在本体定义中")

        errors = await self.ontology.validate_entity_properties(
            body.type_code, body.properties or {}
        )
        if errors:
            raise ValueError(f"属性验证失败: {'; '.join(errors)}")

        entity_id = str(uuid.uuid4())
        record = await self.run_single(
            """
            CREATE (e:Entity {
                id: $id, type_code: $type_code, name: $name,
                description: $description, owner_id: $owner_id,
                properties: $properties, source_type: $source_type,
                source_document_id: $source_document_id,
                created_by: $created_by,
                created_at: datetime(), updated_at: datetime()
            })
            RETURN e
            """,
            params=dict(
                id=entity_id,
                type_code=body.type_code,
                name=body.name.strip(),
                description=body.description or "",
                owner_id=user_id,
                properties=json.dumps(body.properties or {}, ensure_ascii=False),
                source_type=body.source_type or "manual",
                source_document_id=body.source_document_id or "",
                created_by=user_id,
            ),
        )
        if not record:
            raise ValueError("创建实体失败")
        return entity_node_to_out(record["e"], et)

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
        items: list[EntityOut] = []
        for record in records:
            item = await self._enrich_entity(record["e"])
            items.append(item)
        return items

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
            et = await self.ontology.get_entity_type(body.type_code)
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
        rt = await self.ontology.get_relation_type(body.type_code)
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

            errors = await self.ontology.validate_relation_domain_range(
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
        where_clauses = ["r.owner_id = $owner_id"]
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
            rt = await self.ontology.get_relation_type(body.type_code)
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
        depth_clamped = max(1, min(depth, 5))
        where_clause = ""
        params: dict[str, Any] = {"focus_id": focus_id, "depth": depth_clamped}
        if user_id:
            where_clause = (
                "WHERE (connected.owner_id IS NULL OR connected.owner_id = $owner_id)"
            )
            params["owner_id"] = user_id

        record = await self.run_single(
            f"""
            MATCH (focus:Entity {{id: $focus_id}})
            OPTIONAL MATCH path = (focus)-[:RELATES*1..$depth]-(connected:Entity)
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

    async def get_full_graph(self, user_id: str, limit: int = 50) -> GraphOut:
        """获取完整图谱（限制节点数）。"""
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
            WHERE r.owner_id = $owner_id
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
    ) -> dict[str, int]:
        """批量将文档导入为图谱实体。

        Args:
            documents: list of (id, title, description, owner_id) tuples.

        Returns:
            dict with created and skipped counts.
        """
        imported = 0
        skipped = 0
        for doc_id, title, description, owner_id in documents:
            # 检查是否已存在
            existing = await self.run_single(
                "MATCH (e:Entity {source_document_id: $sid}) RETURN e LIMIT 1",
                params=dict(sid=doc_id),
            )
            if existing:
                skipped += 1
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
                        name=title.strip() or "未命名文档",
                        description=description or "",
                        source_type="extraction",
                        source_document_id=doc_id,
                        owner_id=owner_id,
                        created_by=owner_id,
                    ),
                )
                imported += 1
            except Exception as exc:
                logger.warning("导入文档实体失败 [%s]: %s", doc_id, exc)
                skipped += 1
        return {"imported": imported, "skipped": skipped}

    # ── 平台数据同步 ──────────────────────────────────────────────────────

    async def sync_platform_org(
        self, db: Any, owner_id: str
    ) -> dict[str, int]:
        """将平台用户/部门同步为 Neo4j 实体（person / org + employs / contains）。"""
        from app.models.org import Department, User, UserDepartment, UserStatus
        from sqlalchemy import select

        stats: dict[str, int] = {"departments": 0, "users": 0, "relations": 0}

        if not await self.ontology.get_entity_type("org"):
            logger.warning("sync_platform_org: 实体类型 'org' 尚未定义")
            return stats
        if not await self.ontology.get_entity_type("person"):
            logger.warning("sync_platform_org: 实体类型 'person' 尚未定义")
            return stats

        async with self._driver.session() as s:
            # 部门 -> org
            dept_rows = db.scalars(
                select(Department).order_by(Department.sort_order, Department.name)
            ).all()
            dept_map: dict[str, str] = {}
            for dept in dept_rows:
                did = str(dept.id)
                existing = await s.run(
                    "MATCH (e:Entity {platform_department_id: $did}) RETURN e LIMIT 1", did=did
                )
                rec = await existing.single()
                if rec:
                    dept_map[did] = dict(rec["e"])["id"]
                    continue
                eid = str(uuid.uuid4())
                await s.run(
                    "CREATE (e:Entity {id: $id, type_code: 'org', name: $name, "
                    "description: '组织部门', properties: '{}', source_type: 'system', "
                    "platform_department_id: $did, owner_id: $owner, created_by: $owner, "
                    "created_at: datetime(), updated_at: datetime()})",
                    id=eid, name=dept.name.strip(), did=did, owner=owner_id,
                )
                dept_map[did] = eid
                stats["departments"] += 1

            # contains 关系
            for dept in dept_rows:
                did = str(dept.id)
                pdid = str(dept.parent_id) if dept.parent_id else None
                child_id = dept_map.get(did)
                if not pdid or not child_id:
                    continue
                parent_id = dept_map.get(pdid)
                if not parent_id:
                    continue
                dup = await s.run(
                    "MATCH (a:Entity {id: $frm})-[r:RELATES {type_code: 'contains'}]->(b:Entity {id: $to}) "
                    "RETURN r LIMIT 1", frm=parent_id, to=child_id,
                )
                if await dup.single():
                    continue
                rid = str(uuid.uuid4())
                await s.run(
                    "MATCH (a:Entity {id: $frm}) MATCH (b:Entity {id: $to}) "
                    "CREATE (a)-[r:RELATES {id: $rid, type_code: 'contains', "
                    "description: '', inferred: false, owner_id: $owner, "
                    "created_at: datetime()}]->(b)",
                    frm=parent_id, to=child_id, rid=rid, owner=owner_id,
                )
                stats["relations"] += 1

            # 用户 -> person + employs
            users = db.scalars(
                select(User).where(User.status == UserStatus.active.value)
            ).all()
            memberships = db.scalars(select(UserDepartment)).all()
            membership_map: dict[str, str] = {}
            for m in memberships:
                membership_map[str(m.user_id)] = str(m.dept_id)

            for u in users:
                uid = str(u.id)
                label = (u.display_name or u.username or u.phone or "用户").strip()
                existing = await s.run(
                    "MATCH (e:Entity {platform_user_id: $uid}) RETURN e LIMIT 1", uid=uid
                )
                rec = await existing.single()
                if rec:
                    person_id = dict(rec["e"])["id"]
                else:
                    person_id = str(uuid.uuid4())
                    desc_parts = [f"手机 {u.phone}" if u.phone else "",
                                  f"邮箱 {u.email}" if u.email else "",
                                  f"账号 {u.username}" if u.username else ""]
                    desc = " · ".join(p for p in desc_parts if p) or "平台用户"
                    await s.run(
                        "CREATE (e:Entity {id: $id, type_code: 'person', name: $name, "
                        "description: $desc, properties: '{}', source_type: 'system', "
                        "platform_user_id: $uid, owner_id: $owner, created_by: $owner, "
                        "created_at: datetime(), updated_at: datetime()})",
                        id=person_id, name=label, desc=desc, uid=uid, owner=owner_id,
                    )
                    stats["users"] += 1

                dept_id = membership_map.get(uid)
                if dept_id:
                    dept_eid = dept_map.get(dept_id)
                    if dept_eid:
                        dup = await s.run(
                            "MATCH (a:Entity {id: $frm})-[r:RELATES {type_code: 'employs'}]->(b:Entity {id: $to}) "
                            "RETURN r LIMIT 1", frm=dept_eid, to=person_id,
                        )
                        if not await dup.single():
                            rid = str(uuid.uuid4())
                            await s.run(
                                "MATCH (a:Entity {id: $frm}) MATCH (b:Entity {id: $to}) "
                                "CREATE (a)-[r:RELATES {id: $rid, type_code: 'employs', "
                                "description: '', inferred: false, owner_id: $owner, "
                                "created_at: datetime()}]->(b)",
                                frm=dept_eid, to=person_id, rid=rid, owner=owner_id,
                            )
                            stats["relations"] += 1

        logger.info("平台组织同步完成: %s", stats)
        return stats

    async def sync_platform_agents(
        self, db: Any, owner_id: str
    ) -> dict[str, int]:
        """将平台智能体/工具/Skill 同步为 Neo4j 实体。"""
        from app.core.agent_profiles import AGENT_PROFILES
        from app.services.agent_profile_service import (
            is_agent_enabled,
            resolve_agent_internal_atomic_tools,
            resolve_agent_skill_names,
        )
        from app.services.agent_tool_registry import list_agent_tools
        from app.skills.catalog import list_all_skill_definitions

        stats: dict[str, int] = {"agents": 0, "tools": 0, "skills": 0, "relations": 0}
        for tc in ("agent", "tool", "skill"):
            if not await self.ontology.get_entity_type(tc):
                logger.warning("sync_platform_agents: 类型 '%s' 尚未定义", tc)
                return stats

        async with self._driver.session() as s:
            # 工具 -> tool
            tool_map: dict[str, str] = {}
            for tool in list_agent_tools(db, user=None):
                tname = tool.name
                existing = await s.run(
                    "MATCH (e:Entity {platform_tool_name: $n}) RETURN e LIMIT 1", n=tname
                )
                rec = await existing.single()
                if rec:
                    tool_map[tname] = dict(rec["e"])["id"]
                    continue
                eid = str(uuid.uuid4())
                await s.run(
                    "CREATE (e:Entity {id: $id, type_code: 'tool', name: $name, "
                    "description: $desc, properties: '{}', source_type: 'system', "
                    "platform_tool_name: $tn, owner_id: $owner, created_by: $owner, "
                    "created_at: datetime(), updated_at: datetime()})",
                    id=eid, name=tname,
                    desc=(tool.description or "").strip() or "平台原子工具",
                    tn=tname, owner=owner_id,
                )
                tool_map[tname] = eid
                stats["tools"] += 1

            # Skill
            skill_defs = list_all_skill_definitions(
                db, admin_view=True, include_disabled=True, catalog_only=False
            )
            skill_map: dict[str, str] = {}
            for skill in skill_defs:
                sname = skill.name
                existing = await s.run(
                    "MATCH (e:Entity {platform_skill_name: $n}) RETURN e LIMIT 1", n=sname
                )
                rec = await existing.single()
                if rec:
                    skill_map[sname] = dict(rec["e"])["id"]
                    continue
                eid = str(uuid.uuid4())
                await s.run(
                    "CREATE (e:Entity {id: $id, type_code: 'skill', name: $name, "
                    "description: $desc, properties: '{}', source_type: 'system', "
                    "platform_skill_name: $sn, owner_id: $owner, created_by: $owner, "
                    "created_at: datetime(), updated_at: datetime()})",
                    id=eid, name=(skill.title or sname).strip()[:256],
                    desc=(skill.description or "").strip() or "平台 Skill",
                    sn=sname, owner=owner_id,
                )
                skill_map[sname] = eid
                stats["skills"] += 1

            # 智能体 -> agent + 关系
            for defn in AGENT_PROFILES:
                aid = defn.id
                existing = await s.run(
                    "MATCH (e:Entity {platform_agent_id: $aid}) RETURN e LIMIT 1", aid=aid
                )
                rec = await existing.single()
                if rec:
                    agent_id = dict(rec["e"])["id"]
                else:
                    agent_id = str(uuid.uuid4())
                    enabled = is_agent_enabled(db, aid)
                    await s.run(
                        "CREATE (e:Entity {id: $id, type_code: 'agent', name: $name, "
                        "description: $desc, properties: '{}', source_type: 'system', "
                        "platform_agent_id: $aid, owner_id: $owner, created_by: $owner, "
                        "created_at: datetime(), updated_at: datetime()})",
                        id=agent_id, name=defn.title.strip(),
                        desc=defn.description.strip(), aid=aid, owner=owner_id,
                    )
                    stats["agents"] += 1

                # has_tool
                for tname in resolve_agent_internal_atomic_tools(db, aid):
                    tid = tool_map.get(tname)
                    if not tid:
                        continue
                    dup = await s.run(
                        "MATCH (a:Entity {id: $frm})-[r:RELATES {type_code: 'has_tool'}]->(b:Entity {id: $to}) "
                        "RETURN r LIMIT 1", frm=agent_id, to=tid,
                    )
                    if await dup.single():
                        continue
                    rid = str(uuid.uuid4())
                    await s.run(
                        "MATCH (a:Entity {id: $frm}) MATCH (b:Entity {id: $to}) "
                        "CREATE (a)-[r:RELATES {id: $rid, type_code: 'has_tool', "
                        "description: '', inferred: false, owner_id: $owner, "
                        "created_at: datetime()}]->(b)",
                        frm=agent_id, to=tid, rid=rid, owner=owner_id,
                    )
                    stats["relations"] += 1

                # has_skill
                for sname in resolve_agent_skill_names(db, aid):
                    sid = skill_map.get(sname)
                    if not sid:
                        continue
                    dup = await s.run(
                        "MATCH (a:Entity {id: $frm})-[r:RELATES {type_code: 'has_skill'}]->(b:Entity {id: $to}) "
                        "RETURN r LIMIT 1", frm=agent_id, to=sid,
                    )
                    if await dup.single():
                        continue
                    rid = str(uuid.uuid4())
                    await s.run(
                        "MATCH (a:Entity {id: $frm}) MATCH (b:Entity {id: $to}) "
                        "CREATE (a)-[r:RELATES {id: $rid, type_code: 'has_skill', "
                        "description: '', inferred: false, owner_id: $owner, "
                        "created_at: datetime()}]->(b)",
                        frm=agent_id, to=sid, rid=rid, owner=owner_id,
                    )
                    stats["relations"] += 1

            # orchestrates
            for skill in skill_defs:
                sid = skill_map.get(skill.name)
                if not sid:
                    continue
                for tname in skill.orchestrated_tools:
                    tid = tool_map.get(tname)
                    if not tid:
                        continue
                    dup = await s.run(
                        "MATCH (a:Entity {id: $frm})-[r:RELATES {type_code: 'orchestrates'}]->(b:Entity {id: $to}) "
                        "RETURN r LIMIT 1", frm=sid, to=tid,
                    )
                    if await dup.single():
                        continue
                    rid = str(uuid.uuid4())
                    await s.run(
                        "MATCH (a:Entity {id: $frm}) MATCH (b:Entity {id: $to}) "
                        "CREATE (a)-[r:RELATES {id: $rid, type_code: 'orchestrates', "
                        "description: '', inferred: false, owner_id: $owner, "
                        "created_at: datetime()}]->(b)",
                        frm=sid, to=tid, rid=rid, owner=owner_id,
                    )
                    stats["relations"] += 1

        logger.info("平台智能体/工具/Skill 同步完成: %s", stats)
        return stats

    async def sync_agent_memory_to_kg(self, user_id: str) -> dict[str, int]:
        """将用户 MEMORY.md 章节抽取为 memory 类型实体。"""
        from app.services.agent_memory_service import read_user_memory

        stats: dict[str, int] = {"entities": 0}
        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        memory_text = read_user_memory(uid)
        if not memory_text.strip():
            return stats

        sections: list[tuple[str, str]] = []
        current_title = "概述"
        current_lines: list[str] = []
        for line in memory_text.split("\n"):
            if line.startswith("## "):
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines).strip()))
                current_title = line.lstrip("#").strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((current_title, "\n".join(current_lines).strip()))

        async with self._driver.session() as s:
            for title, content in sections:
                if not content:
                    continue
                safe_title = title.strip()[:256]
                existing = await s.run(
                    "MATCH (e:Entity {type_code: 'memory', name: $n, owner_id: $o}) "
                    "RETURN e LIMIT 1", n=safe_title, o=user_id,
                )
                if await existing.single():
                    continue
                eid = str(uuid.uuid4())
                await s.run(
                    "CREATE (e:Entity {id: $id, type_code: 'memory', name: $name, "
                    "description: $desc, properties: '{}', source_type: 'system', "
                    "owner_id: $owner, created_by: $owner, "
                    "created_at: datetime(), updated_at: datetime()})",
                    id=eid, name=safe_title, desc=content[:500], owner=user_id,
                )
                stats["entities"] += 1

        logger.info("记忆同步完成: %s", stats)
        return stats

    async def batch_extract_documents_from_content(
        self,
        db: Any,
        user_id: str,
        *,
        max_docs: int = 20,
    ) -> dict[str, Any]:
        """批量读取已上传文档的正文，通过 LLM 抽取实体/关系。

        Args:
            db: SQLAlchemy session for document queries.
            user_id: 当前用户 ID.
            max_docs: 最大处理文档数（防止过度消耗 LLM token）.

        Returns:
            统计信息。
        """
        from app.models.org import User
        from app.services.agent_document_service import read_document_content_for_agent
        from app.services.kg_extraction_service import extract_kg_from_text_v2
        from sqlalchemy import select

        stats: dict[str, Any] = {
            "processed": 0, "total_docs": 0,
            "entities_created": 0, "relations_created": 0,
            "errors": 0,
        }

        # 获取已存在 source_document_id 的实体，跳过已抽取的文档
        existing_sids: set[str] = set()
        existing = await self.run(
            "MATCH (e:Entity) WHERE e.source_document_id IS NOT NULL "
            "AND e.source_document_id <> '' "
            "RETURN e.source_document_id AS sid",
        )
        for record in existing:
            sid = record.get("sid", "")
            if sid:
                existing_sids.add(str(sid))

        # 获取当前用户
        user = db.scalar(select(User).where(User.id == uuid.UUID(user_id)))
        if not user:
            stats["error"] = "用户不存在"
            return stats

        # 查询未删除文档
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
            if did in existing_sids:
                continue  # 已有对应的 doc 实体，但仍可抽取内容实体

            # 先确保 doc 实体存在
            doc_exists = await self.run_single(
                "MATCH (e:Entity {source_document_id: $sid}) RETURN e LIMIT 1",
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

            # 读取正文
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

            # LLM 抽取
            try:
                result = await extract_kg_from_text_v2(
                    driver=driver,
                    title=doc.title or "文档",
                    text=full_text,
                    user_id=user_id,
                    source_type="extraction",
                    source_id=did,
                )
                if not result.get("skipped", True):
                    stats["entities_created"] += result.get("entities_created", 0)
                    stats["relations_created"] += result.get("relations_created", 0)
                    processed += 1
            except Exception as exc:
                logger.warning("文档 LLM 抽取失败 [%s]: %s", did, exc)
                stats["errors"] += 1

        stats["processed"] = processed
        logger.info("批量文档内容抽取完成: %s", stats)
        return stats

    async def _enrich_entity(self, node: Any) -> EntityOut:
        """将 Neo4j 节点富化为 EntityOut（附带本体类型信息）。"""
        props = dict(node)
        type_code = props.get("type_code", "")
        et = await self.ontology.get_entity_type(type_code)
        return entity_node_to_out(node, et)

    async def _nodes_and_edges_to_graph(
        self,
        nodes: list[Any],
        edges: list[Any],
        focus_id: str,
    ) -> GraphOut:
        graph_nodes: list[GraphNodeOut] = []
        seen_ids: set[str] = set()
        for node in nodes:
            nd = dict(node)
            nid = nd.get("id", "")
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            type_code = nd.get("type_code", "")
            et = await self.ontology.get_entity_type(type_code)
            graph_nodes.append(
                GraphNodeOut(
                    id=nid,
                    name=nd.get("name", ""),
                    type_code=type_code,
                    type_label=et.label if et else type_code,
                    type_color=et.color if et else "gray",
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
            graph_edges.append(
                GraphEdgeOut(
                    id=eid,
                    type_code=ed.get("type_code", ""),
                    type_label=ed.get("type_code", ""),
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
        graph_nodes: list[GraphNodeOut] = []
        seen_ids: set[str] = set()
        for node in nodes:
            nd = dict(node)
            nid = nd.get("id", "")
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            type_code = nd.get("type_code", "")
            et = await self.ontology.get_entity_type(type_code)
            graph_nodes.append(
                GraphNodeOut(
                    id=nid,
                    name=nd.get("name", ""),
                    type_code=type_code,
                    type_label=et.label if et else type_code,
                    type_color=et.color if et else "gray",
                )
            )

        graph_edges: list[GraphEdgeOut] = []
        for rec in edge_records:
            r = rec.get("r", {})
            a = rec.get("a", {})
            b = rec.get("b", {})
            graph_edges.append(
                GraphEdgeOut(
                    id=r.get("id", ""),
                    type_code=r.get("type_code", ""),
                    type_label=r.get("type_code", ""),
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


def merge_kg_qa_into_context(db_session, user, kg_ctx, base_context: str = "") -> str:
    """向后兼容：将 KG 问答上下文合并到检索上下文字符串。"""
    if kg_ctx is None:
        return base_context
    ctx_text = (getattr(kg_ctx, "context_text", "") or "").strip()
    if ctx_text:
        return f"{base_context}\n\n{ctx_text}" if base_context else ctx_text
    return base_context


def try_department_members_deterministic_reply(
    db_session, user, message: str, *, reply: str = ""
) -> str | None:
    """向后兼容遗存函数，返回 None 表示不拦截。"""
    return None
