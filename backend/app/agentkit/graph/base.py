"""Neo4j 基础服务 — 消除 kg/ontology 服务的重复异步 session 管理。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, Record
    from neo4j.exceptions import DriverError, ServiceUnavailable

from app.core.exceptions import service_unavailable

logger = logging.getLogger(__name__)


def _raise_if_neo4j_down(exc: BaseException) -> None:
    """如果异常来自 Neo4j 连接失败，转为 service_unavailable 的 AppError。"""
    from neo4j.exceptions import DriverError, ServiceUnavailable

    if isinstance(exc, ServiceUnavailable):
        logger.error("Neo4j 服务不可用，请确认图数据库已启动")
        raise service_unavailable("知识图谱（Neo4j）服务暂不可用，请稍后重试") from exc
    if isinstance(exc, DriverError):
        logger.exception("Neo4j 驱动错误")
        raise service_unavailable("知识图谱（Neo4j）服务暂不可用，请稍后重试") from exc


class Neo4jBaseService:
    """Neo4j 基础服务类。

    提供统一的 session 管理、查询执行和结果提取，减少 KgService 和
    OntologyService 中重复的 ``async with self._driver.session() as s:`` 模式。
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    # ── 查询执行基元 ──────────────────────────────────────────

    async def run(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[Record]:
        """执行 Cypher 查询，返回所有结果记录。

        Args:
            query: Cypher 查询语句。
            params: 命名参数。
            database: 目标数据库（None 使用默认）。

        Returns:
            记录列表。每条记录可通过 key 或下标访问。

        Raises:
            AppError(503): Neo4j 不可用时。
        """
        try:
            async with self._driver.session(database=database) as session:
                result = await session.run(query, params or {})
                return [record async for record in result]
        except Exception as exc:
            _raise_if_neo4j_down(exc)
            raise

    async def run_single(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> Record | None:
        """执行 Cypher 查询，返回第一条记录或 None。"""
        try:
            async with self._driver.session(database=database) as session:
                result = await session.run(query, params or {})
                return await result.single()
        except Exception as exc:
            _raise_if_neo4j_down(exc)
            raise

    async def run_and_collect(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """执行查询并格式化为字典列表。"""
        records = await self.run(query, params, database=database)
        return [dict(r) for r in records]

    async def execute_write(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> Record | None:
        """执行写入查询，在写入事务中运行。

        对于 CREATE / SET / DELETE 等写操作，使用此方法替代 run，
        以利用 Neo4j 的写入事务。
        """
        try:
            async with self._driver.session(database=database) as session:
                result = await session.run(query, params or {})
                return await result.single()
        except Exception as exc:
            _raise_if_neo4j_down(exc)
            raise

    async def count_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> int:
        """执行 COUNT 查询并返回整数结果。

        查询须以 ``RETURN count(...) AS cnt`` 结尾。
        """
        record = await self.run_single(query, params, database=database)
        if record is None:
            return 0
        return record.get("cnt") or 0
