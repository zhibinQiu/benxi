"""Neo4j 异步查询基元（KG 包内私有，不暴露给 Agent）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


class Neo4jOps:
    """轻量 Neo4j 操作封装。"""

    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver

    async def collect(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        async with self.driver.session() as session:
            cursor = await session.run(query, params or {})
            return [dict(record) async for record in cursor]

    async def count(self, query: str, params: dict[str, Any] | None = None) -> int:
        rows = await self.collect(query, params)
        if not rows:
            return 0
        row = rows[0]
        for v in row.values():
            if isinstance(v, int):
                return v
        return 0
