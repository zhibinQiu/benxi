"""Neo4j 连接池管理器 — 应用生命周期全局单例。

通过异步驱动程序连接 Neo4j 图数据库，提供连接获取/关闭/模式初始化的统一入口。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


async def get_neo4j() -> AsyncDriver:
    """获取全局 Neo4j 异步驱动实例（单例）。

    Returns:
        AsyncDriver: Neo4j 异步驱动实例
    """
    global _driver
    if _driver is None:
        from neo4j import AsyncGraphDatabase

        settings = get_settings()
        uri = settings.neo4j_uri
        user = settings.neo4j_user
        password = settings.neo4j_password
        if not password:
            logger.warning("NEO4J_PASSWORD 未设置，尝试无认证连接")
            auth = None
        else:
            auth = (user, password)
        _driver = AsyncGraphDatabase.driver(
            uri,
            auth=auth,
            max_connection_pool_size=10,
            connection_acquisition_timeout=30.0,
        )
        logger.info("Neo4j driver created: %s", uri)
    return _driver


async def close_neo4j() -> None:
    """关闭全局 Neo4j 驱动程序，释放连接池资源。"""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")


async def get_neo4j_session(database: str | None = None) -> AsyncSession:
    """便捷方法：获取一次性的 Neo4j 会话。

    注意：大部分场景应直接使用 get_neo4j() 返回的 driver 自行管理 session。

    Args:
        database: 数据库名，默认 None 使用配置的 neo4j_database

    Returns:
        AsyncSession: Neo4j 异步会话
    """
    from app.config import get_settings

    driver = await get_neo4j()
    db = database or get_settings().neo4j_database
    return driver.session(database=db)


async def init_neo4j_schema() -> None:
    """初始化 Neo4j 模式：创建必要的索引和约束。

    在应用启动时调用，确保图数据库查询性能。
    连接失败时自动重置 _driver，以便后续调用重新尝试。
    """
    global _driver
    try:
        driver = await get_neo4j()
    except Exception:
        _driver = None
        raise

    settings = get_settings()
    statements = [
        # Entity 节点索引
        "CREATE INDEX entity_type_code IF NOT EXISTS FOR (n:Entity) ON (n.type_code)",
        "CREATE INDEX entity_owner IF NOT EXISTS FOR (n:Entity) ON (n.owner_id)",
        "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
        # RELATES 关系索引
        "CREATE INDEX relates_type IF NOT EXISTS FOR ()-[r:RELATES]-() ON (r.type_code)",
        # 唯一约束（unique constraint 自动创建索引，不再单独建同名属性索引）
        "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT oet_code_unique IF NOT EXISTS FOR (n:OntologyEntityType) REQUIRE n.code IS UNIQUE",
        "CREATE CONSTRAINT ort_code_unique IF NOT EXISTS FOR (n:OntologyRelationType) REQUIRE n.code IS UNIQUE",
        "CREATE CONSTRAINT oa_name_unique IF NOT EXISTS FOR (n:OntologyAxiom) REQUIRE n.name IS UNIQUE",
    ]
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            for stmt in statements:
                try:
                    await session.run(stmt)
                    logger.debug("Neo4j schema: %s", stmt[:80])
                except Exception as exc:
                    logger.warning("Neo4j schema statement failed (may be expected): %s — %s", stmt[:80], exc)
        logger.info("Neo4j schema initialization complete")
    except Exception:
        _driver = None
        raise


async def neo4j_health_check() -> dict[str, Any]:
    """Neo4j 健康检查。

    Returns:
        dict: 包含连接状态和服务器信息的字典
    """
    try:
        driver = await get_neo4j()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            if record and record["ok"] == 1:
                return {"status": "ok", "connected": True}
        return {"status": "error", "connected": False, "detail": "query_failed"}
    except Exception as exc:
        return {"status": "error", "connected": False, "detail": str(exc)}


async def run_cypher(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """执行 Cypher 查询并返回结果列表。

    Args:
        query: Cypher 查询语句
        params: 查询参数

    Returns:
        list[dict]: 查询结果记录列表
    """
    driver = await get_neo4j()
    settings = get_settings()
    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(query, params or {})
        records = []
        async for record in result:
            records.append(dict(record))
        return records
