"""Neo4j session helpers (platform core)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, Record

logger = logging.getLogger(__name__)

UnavailableFactory = Callable[[str, BaseException], BaseException]


def _default_unavailable(message: str, cause: BaseException) -> BaseException:
    err = RuntimeError(message)
    err.__cause__ = cause
    return err


class Neo4jBaseService:
    """Neo4j session helpers. Host may inject ``unavailable`` for AppError mapping."""

    def __init__(
        self,
        driver: AsyncDriver,
        *,
        unavailable: UnavailableFactory | None = None,
    ) -> None:
        self._driver = driver
        self._unavailable = unavailable or _default_unavailable

    def _raise_if_neo4j_down(self, exc: BaseException) -> None:
        from neo4j.exceptions import DriverError, ServiceUnavailable

        if isinstance(exc, ServiceUnavailable):
            logger.error("Neo4j unavailable")
            raise self._unavailable("Neo4j graph database is temporarily unavailable", exc)
        if isinstance(exc, DriverError):
            logger.exception("Neo4j driver error")
            raise self._unavailable("Neo4j graph database is temporarily unavailable", exc)

    async def run(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[Record]:
        try:
            async with self._driver.session(database=database) as session:
                result = await session.run(query, params or {})
                return [record async for record in result]
        except Exception as exc:
            self._raise_if_neo4j_down(exc)
            raise

    async def run_single(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> Record | None:
        try:
            async with self._driver.session(database=database) as session:
                result = await session.run(query, params or {})
                return await result.single()
        except Exception as exc:
            self._raise_if_neo4j_down(exc)
            raise

    async def run_and_collect(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        records = await self.run(query, params, database=database)
        return [dict(r) for r in records]

    async def execute_write(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> Record | None:
        try:
            async with self._driver.session(database=database) as session:
                result = await session.run(query, params or {})
                return await result.single()
        except Exception as exc:
            self._raise_if_neo4j_down(exc)
            raise

    async def count_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> int:
        record = await self.run_single(query, params, database=database)
        if record is None:
            return 0
        return record.get("cnt") or 0
