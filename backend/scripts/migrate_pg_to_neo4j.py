"""一次性迁移脚本：将 PostgreSQL 中的 KG 数据迁移到 Neo4j。

用法:
    cd backend
    python -m scripts.migrate_pg_to_neo4j

前提:
    - PostgreSQL 中 kg_* 表有数据
    - Neo4j 服务已启动并可连接
    - 环境变量 NEO4J_PASSWORD 已设置
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from neo4j import AsyncGraphDatabase
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def migrate():
    settings = get_settings()

    # PG 连接
    pg_engine = create_engine(settings.database_url)
    pg_session = Session(pg_engine)

    # Neo4j 连接
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    stats = {
        "entity_types": 0,
        "relation_types": 0,
        "entities": 0,
        "relations": 0,
        "errors": 0,
    }

    try:
        async with driver.session() as neo4j_session:
            # 1. 迁移实体类型 → OntologyEntityType
            logger.info("Migrating entity types...")
            rows = pg_session.execute(text("SELECT * FROM kg_entity_types")).fetchall()
            for row in rows:
                try:
                    await neo4j_session.run(
                        """
                        MERGE (et:OntologyEntityType {code: $code})
                        SET et.label = $label, et.color = $color,
                            et.icon = $icon, et.sort_order = $sort_order,
                            et.description = $description,
                            et.property_schema = $property_schema,
                            et.created_at = datetime(), et.updated_at = datetime()
                        """,
                        code=row.code,
                        label=row.label,
                        color=getattr(row, "color", "blue") or "blue",
                        icon=getattr(row, "icon", "help-circle") or "help-circle",
                        sort_order=getattr(row, "sort_order", 100) or 100,
                        description=getattr(row, "description", "") or "",
                        property_schema={},
                    )
                    stats["entity_types"] += 1
                except Exception as exc:
                    logger.error("Entity type migration failed: %s — %s", row.code, exc)
                    stats["errors"] += 1

            # 2. 迁移关系类型 → OntologyRelationType
            logger.info("Migrating relation types...")
            rows = pg_session.execute(text("SELECT * FROM kg_relation_types")).fetchall()
            for row in rows:
                try:
                    await neo4j_session.run(
                        """
                        MERGE (rt:OntologyRelationType {code: $code})
                        SET rt.label = $label,
                            rt.domain_types = $domain_types,
                            rt.range_types = $range_types,
                            rt.transitive = $transitive,
                            rt.sort_order = $sort_order,
                            rt.created_at = datetime(), rt.updated_at = datetime()
                        """,
                        code=row.code,
                        label=row.label,
                        domain_types=[],
                        range_types=[],
                        transitive=False,
                        sort_order=getattr(row, "sort_order", 100) or 100,
                    )
                    stats["relation_types"] += 1
                except Exception as exc:
                    logger.error("Relation type migration failed: %s — %s", row.code, exc)
                    stats["errors"] += 1

            # 3. 迁移实体 → Entity
            logger.info("Migrating entities...")
            rows = pg_session.execute(text("SELECT * FROM kg_entities")).fetchall()
            for row in rows:
                try:
                    type_code = "doc"
                    type_row = pg_session.execute(
                        text("SELECT code FROM kg_entity_types WHERE id = :tid"),
                        {"tid": row.type_id},
                    ).fetchone()
                    if type_row:
                        type_code = type_row[0]

                    await neo4j_session.run(
                        """
                        CREATE (e:Entity {
                            id: $id, type_code: $type_code, name: $name,
                            description: $description, owner_id: $owner_id,
                            properties: $properties,
                            source_type: $source_type, source_document_id: $source_document_id,
                            created_by: $created_by,
                            created_at: datetime(), updated_at: datetime()
                        })
                        """,
                        id=str(row.id),
                        type_code=type_code,
                        name=(row.name or "").strip()[:256],
                        description=getattr(row, "description", "") or "",
                        owner_id=str(row.owner_id),
                        properties=row.properties or {},
                        source_type="migration",
                        source_document_id="",
                        created_by=str(getattr(row, "created_by", row.owner_id)),
                    )
                    stats["entities"] += 1
                except Exception as exc:
                    logger.error("Entity migration failed: %s — %s", row.id, exc)
                    stats["errors"] += 1

            # 4. 迁移关系 → RELATES
            logger.info("Migrating relations...")
            rows = pg_session.execute(
                text("""
                    SELECT r.*, ft.code AS from_type_code, tt.code AS to_type_code
                    FROM kg_relations r
                    LEFT JOIN kg_entities fe ON r.from_entity_id = fe.id
                    LEFT JOIN kg_entities te ON r.to_entity_id = te.id
                    LEFT JOIN kg_entity_types ft ON fe.type_id = ft.id
                    LEFT JOIN kg_entity_types tt ON te.type_id = tt.id
                """)
            ).fetchall()
            for row in rows:
                try:
                    type_code = "references"
                    type_row = pg_session.execute(
                        text("SELECT code FROM kg_relation_types WHERE id = :tid"),
                        {"tid": row.type_id},
                    ).fetchone()
                    if type_row:
                        type_code = type_row[0]

                    await neo4j_session.run(
                        """
                        MATCH (a:Entity {id: $from_id})
                        MATCH (b:Entity {id: $to_id})
                        CREATE (a)-[r:RELATES {
                            id: $id, type_code: $type_code,
                            description: $description, inferred: false,
                            owner_id: $owner_id, created_at: datetime()
                        }]->(b)
                        """,
                        id=str(uuid.uuid4()),
                        from_id=str(row.from_entity_id),
                        to_id=str(row.to_entity_id),
                        type_code=type_code,
                        description=getattr(row, "description", "") or "",
                        owner_id=str(row.owner_id),
                    )
                    stats["relations"] += 1
                except Exception as exc:
                    logger.error("Relation migration failed: from=%s to=%s — %s",
                                 row.from_entity_id, row.to_entity_id, exc)
                    stats["errors"] += 1

    finally:
        await driver.close()
        pg_session.close()

    logger.info("Migration complete. Stats: %s", stats)


if __name__ == "__main__":
    asyncio.run(migrate())
