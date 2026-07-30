"""GraphDB 连接与 SPARQL 客户端 — 全局本体（TBox）存储。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: GraphDbClient | None = None


class GraphDbClient:
    """Ontotext GraphDB REST/SPARQL 异步客户端。"""

    def __init__(
        self,
        base_url: str,
        repository: str,
        *,
        user: str = "",
        password: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._repository = repository
        self._auth = (user, password) if user else None
        self._timeout = timeout

    @property
    def repository_url(self) -> str:
        return f"{self._base}/repositories/{self._repository}"

    async def query(self, sparql: str) -> list[dict[str, Any]]:
        """执行 SPARQL SELECT，返回 bindings 字典列表。"""
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.post(
                self.repository_url,
                content=sparql,
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/sparql-query",
                },
                auth=self._auth,
            )
            resp.raise_for_status()
            payload = resp.json()
        rows: list[dict[str, Any]] = []
        for binding in payload.get("results", {}).get("bindings", []):
            row: dict[str, Any] = {}
            for key, val in binding.items():
                row[key] = val.get("value")
            rows.append(row)
        return rows

    async def update(self, sparql: str) -> None:
        """执行 SPARQL UPDATE。"""
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.post(
                f"{self.repository_url}/statements",
                content=sparql,
                headers={"Content-Type": "application/sparql-update"},
                auth=self._auth,
            )
            resp.raise_for_status()

    async def ask(self, sparql: str) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.post(
                self.repository_url,
                content=sparql,
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/sparql-query",
                },
                auth=self._auth,
            )
            resp.raise_for_status()
            return bool(resp.json().get("boolean"))

    async def count_triples(self) -> int:
        rows = await self.query("SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }")
        if not rows:
            return 0
        try:
            return int(rows[0].get("c") or 0)
        except (TypeError, ValueError):
            return 0

    async def repository_exists(self) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.get(
                f"{self._base}/rest/repositories/{self._repository}",
                auth=self._auth,
            )
            return resp.status_code == 200

    async def ensure_repository(self) -> None:
        if await self.repository_exists():
            return
        # GraphDB 官方创建方式：multipart 上传 Turtle 仓库配置
        config_ttl = f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>.
@prefix rep: <http://www.openrdf.org/config/repository#>.
@prefix sr: <http://www.openrdf.org/config/repository/sail#>.
@prefix sail: <http://www.openrdf.org/config/sail#>.
@prefix graphdb: <http://www.ontotext.com/config/graphdb#>.

[] a rep:Repository ;
   rep:repositoryID "{self._repository}" ;
   rdfs:label "Benxi Ontology" ;
   rep:repositoryImpl [
     rep:repositoryType "graphdb:SailRepository" ;
     sr:sailImpl [
       sail:sailType "graphdb:Sail" ;
       graphdb:ruleset "owl-horst-optimized" ;
       graphdb:disable-sameAs "true" ;
       graphdb:read-only "false" ;
     ]
   ].
"""
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.post(
                f"{self._base}/rest/repositories",
                files={"config": ("config.ttl", config_ttl.encode("utf-8"), "text/turtle")},
                auth=self._auth,
            )
            if resp.status_code in (200, 201):
                logger.info("GraphDB repository created: %s", self._repository)
                return
            # 并发创建或已存在时 GraphDB 可能返回 4xx/5xx；再确认一次
            if await self.repository_exists():
                logger.info("GraphDB repository already present: %s", self._repository)
                return
            resp.raise_for_status()
        logger.info("GraphDB repository created: %s", self._repository)


def get_graphdb_client() -> GraphDbClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = GraphDbClient(
            settings.graphdb_url,
            settings.graphdb_repository,
            user=settings.graphdb_user,
            password=settings.graphdb_password,
        )
    return _client


async def init_graphdb() -> None:
    """启动时确保 GraphDB 仓库存在，并从 Neo4j 迁移遗留 TBox（如有）。"""
    settings = get_settings()
    if not (settings.graphdb_url or "").strip():
        logger.warning("GRAPHDB_URL 未配置，本体功能将不可用")
        return
    client = get_graphdb_client()
    try:
        await client.ensure_repository()
    except Exception:
        logger.exception("GraphDB 仓库初始化失败")
        raise

    try:
        from app.ontology.migrate_from_neo4j import migrate_neo4j_tbox_if_needed

        await migrate_neo4j_tbox_if_needed(client)
    except Exception:
        logger.exception("Neo4j → GraphDB 本体迁移失败（不影响启动）")

    try:
        rows = await client.query(
            """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX bxmeta: <http://benxi.ai/ontology/meta#>
SELECT (COUNT(?c) AS ?cnt) WHERE { ?c a owl:Class ; bxmeta:code ?code . }
"""
        )
        count = int(rows[0].get("cnt") or 0) if rows else 0
        if count == 0:
            from app.core.neo4j import get_neo4j
            from app.services.ontology_service import OntologyService

            svc = OntologyService(client, await get_neo4j())
            await svc.seed_defaults()
            logger.info("GraphDB 默认本体已初始化")
    except Exception:
        logger.exception("GraphDB 默认本体种子失败（不影响启动）")


async def graphdb_health_check() -> dict[str, Any]:
    try:
        client = get_graphdb_client()
        ok = await client.repository_exists()
        if not ok:
            return {"status": "error", "connected": False, "detail": "repository_missing"}
        count = await client.count_triples()
        return {"status": "ok", "connected": True, "triple_count": count}
    except Exception as exc:
        return {"status": "error", "connected": False, "detail": str(exc)}
