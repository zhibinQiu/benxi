#!/usr/bin/env python3
"""平台 API 吞吐量 / 压力测试（含文档解析入队）。

用法（在 platform 目录）:
  python scripts/stress_test_throughput.py
  python scripts/stress_test_throughput.py --concurrency 200 --parse-jobs 200

测试结束后自动删除带 __stress_test__ 前缀的文档及相关数据。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# 允许从 platform/ 根目录导入 app 配置（PG 连接统计）
_PLATFORM_ROOT = Path(__file__).resolve().parent.parent
if str(_PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLATFORM_ROOT))

STRESS_TITLE_PREFIX = "__stress_test__"
DEFAULT_BASE = os.environ.get("STRESS_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_ACCOUNT = os.environ.get("STRESS_ACCOUNT", "admin")
DEFAULT_PASSWORD = os.environ.get("STRESS_PASSWORD", "admin123")


@dataclass
class RequestResult:
    status: int
    elapsed_ms: float
    error: str = ""


@dataclass
class ScenarioReport:
    name: str
    total: int = 0
    ok: int = 0
    status_503: int = 0
    other_errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, r: RequestResult) -> None:
        self.total += 1
        self.latencies_ms.append(r.elapsed_ms)
        if 200 <= r.status < 300:
            self.ok += 1
        elif r.status == 503:
            self.status_503 += 1
        else:
            self.other_errors += 1

    def summary(self) -> dict[str, Any]:
        lat = sorted(self.latencies_ms)
        pct = lambda p: lat[int(len(lat) * p / 100)] if lat else 0.0
        return {
            "name": self.name,
            "total": self.total,
            "ok": self.ok,
            "ok_rate": round(self.ok / self.total * 100, 2) if self.total else 0,
            "status_503": self.status_503,
            "other_errors": self.other_errors,
            "p50_ms": round(pct(50), 1),
            "p95_ms": round(pct(95), 1),
            "p99_ms": round(pct(99), 1),
            "max_ms": round(max(lat), 1) if lat else 0,
            "notes": self.notes,
        }


def pg_connection_stats() -> dict[str, Any]:
    """查询 PostgreSQL 当前连接数（与 API 进程池无关，反映 DB 侧压力）。"""
    try:
        from sqlalchemy import text

        from app.config import get_settings
        from app.database import engine

        settings = get_settings()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                      count(*) FILTER (WHERE state = 'active') AS active,
                      count(*) FILTER (WHERE state = 'idle') AS idle,
                      count(*) AS total
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    """
                )
            ).one()
        pool = engine.pool
        return {
            "pg_active": int(row.active),
            "pg_idle": int(row.idle),
            "pg_total": int(row.total),
            "pool_size": pool.size(),
            "pool_checked_in": pool.checkedin(),
            "pool_checked_out": pool.checkedout(),
            "pool_overflow": pool.overflow(),
            "db_pool_config": {
                "size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "timeout": settings.db_pool_timeout,
            },
        }
    except Exception as exc:
        return {"error": str(exc)}


async def login(client: httpx.AsyncClient, account: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"account": account, "password": password},
    )
    resp.raise_for_status()
    token = resp.json().get("data", {}).get("access_token")
    if not token:
        raise RuntimeError(f"登录失败: {resp.text[:200]}")
    return token


async def _one_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
    content: bytes | None = None,
) -> RequestResult:
    started = time.perf_counter()
    try:
        resp = await client.request(
            method,
            path,
            headers=headers,
            json=json_body,
            content=content,
        )
        elapsed = (time.perf_counter() - started) * 1000
        return RequestResult(status=resp.status_code, elapsed_ms=elapsed)
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return RequestResult(status=0, elapsed_ms=elapsed, error=str(exc))


async def run_concurrent_requests(
    client: httpx.AsyncClient,
    specs: list[tuple[str, str, dict[str, str] | None, dict | None, bytes | None]],
    concurrency: int,
    report: ScenarioReport,
) -> None:
    sem = asyncio.Semaphore(concurrency)

    async def worker(spec: tuple) -> None:
        method, path, headers, body, content = spec
        async with sem:
            report.add(await _one_request(client, method, path, headers=headers, json_body=body, content=content))

    await asyncio.gather(*(worker(s) for s in specs))


async def scenario_health_burst(
    client: httpx.AsyncClient, *, total: int, concurrency: int
) -> ScenarioReport:
    report = ScenarioReport(name="health_burst")
    specs = [("GET", "/health", None, None, None)] * (total // 2)
    specs += [("GET", "/health/ready", None, None, None)] * (total - total // 2)
    await run_concurrent_requests(client, specs, concurrency, report)
    return report


async def scenario_mixed_reads(
    client: httpx.AsyncClient,
    token: str,
    *,
    virtual_users: int,
    concurrency: int,
) -> ScenarioReport:
    """模拟多人在线：文档列表 / 库结构 / 概览 / 监控。"""
    report = ScenarioReport(name="mixed_reads_online")
    headers = {"Authorization": f"Bearer {token}"}
    paths = [
        ("GET", "/api/v1/documents?scope=personal&page=1&page_size=20", None, None),
        ("GET", "/api/v1/documents/library", None, None),
        ("GET", "/api/v1/documents/overview?scope=personal", None, None),
        ("GET", "/api/v1/monitor/metrics", None, None),
        ("GET", "/health/ready", None, None),
    ]
    specs: list[tuple] = []
    for i in range(virtual_users):
        method, path, body, content = paths[i % len(paths)]
        specs.append((method, path, headers, body, content))
    await run_concurrent_requests(client, specs, concurrency, report)
    return report


async def scenario_sustained_reads(
    client: httpx.AsyncClient,
    token: str,
    *,
    duration_sec: float,
    concurrency: int,
) -> ScenarioReport:
    """持续读压：在 duration 内维持 concurrency 并发。"""
    report = ScenarioReport(name="sustained_reads")
    headers = {"Authorization": f"Bearer {token}"}
    paths = [
        "/api/v1/documents?scope=personal&page=1&page_size=20",
        "/api/v1/documents/library",
        "/health/ready",
    ]
    stop_at = time.monotonic() + duration_sec
    idx = 0

    async def worker() -> None:
        nonlocal idx
        while time.monotonic() < stop_at:
            path = paths[idx % len(paths)]
            idx += 1
            report.add(
                await _one_request(client, "GET", path, headers=headers)
            )

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    report.notes.append(f"duration_sec={duration_sec}")
    return report


async def create_and_upload_document(
    client: httpx.AsyncClient,
    token: str,
    *,
    suffix: str,
) -> tuple[str | None, str]:
    """创建文档 → prepare → blob → complete。返回 (doc_id, error)。"""
    headers = {"Authorization": f"Bearer {token}"}
    title = f"{STRESS_TITLE_PREFIX}{suffix}"
    content = (
        f"Stress test document {suffix}\n"
        "Lorem ipsum dolor sit amet.\n" * 20
    ).encode("utf-8")

    try:
        resp = await client.post(
            "/api/v1/documents",
            headers=headers,
            json={"title": title, "scope": "personal", "description": "stress test"},
        )
        if resp.status_code != 200:
            return None, f"create {resp.status_code}"
        doc_id = str(resp.json()["data"]["id"])

        resp = await client.post(
            f"/api/v1/documents/{doc_id}/upload/prepare",
            headers=headers,
            params={"file_name": f"{suffix}.txt", "mime_type": "text/plain"},
        )
        if resp.status_code != 200:
            return doc_id, f"prepare {resp.status_code}"
        prep = resp.json()["data"]
        version_id = prep["version_id"]

        resp = await client.put(
            f"/api/v1/documents/{doc_id}/upload/{version_id}/blob",
            headers={**headers, "Content-Type": "text/plain"},
            content=content,
        )
        if resp.status_code != 204:
            return doc_id, f"blob {resp.status_code}"

        resp = await client.post(
            f"/api/v1/documents/{doc_id}/upload/complete",
            headers=headers,
            json={
                "version_id": str(version_id),
                "file_size": len(content),
                "checksum": "",
                "change_description": "stress test upload",
            },
        )
        if resp.status_code != 200:
            return doc_id, f"complete {resp.status_code}"
        return doc_id, ""
    except Exception as exc:
        return None, str(exc)


async def scenario_parse_enqueue_burst(
    client: httpx.AsyncClient,
    token: str,
    *,
    parse_jobs: int,
    concurrency: int,
) -> tuple[ScenarioReport, list[str]]:
    """并发创建文档并触发解析入队（模拟多人同时上传/解析）。"""
    report = ScenarioReport(name="parse_enqueue_burst")
    doc_ids: list[str] = []
    headers = {"Authorization": f"Bearer {token}"}
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()

    async def one_job(i: int) -> None:
        async with sem:
            started = time.perf_counter()
            doc_id, err = await create_and_upload_document(
                client, token, suffix=f"{int(time.time())}_{i}_{uuid.uuid4().hex[:8]}"
            )
            elapsed = (time.perf_counter() - started) * 1000
            status = 200 if doc_id and not err else (500 if doc_id else 400)
            report.add(RequestResult(status=status, elapsed_ms=elapsed, error=err))
            if doc_id:
                async with lock:
                    doc_ids.append(doc_id)
                # 触发 reindex / 解析入队
                r = await _one_request(
                    client,
                    "POST",
                    f"/api/v1/knowledge/documents/{doc_id}/reindex",
                    headers=headers,
                    json_body={"resync": True},
                )
                report.add(r)

    await asyncio.gather(*(one_job(i) for i in range(parse_jobs)))
    report.notes.append(f"parse_jobs={parse_jobs}, docs_created={len(doc_ids)}")
    return report, doc_ids


async def cleanup_stress_documents(
    client: httpx.AsyncClient, token: str, doc_ids: list[str]
) -> dict[str, Any]:
    """批量删除压测文档。"""
    headers = {"Authorization": f"Bearer {token}"}
    deleted: list[str] = []
    failed: list[dict] = []
    unique = list(dict.fromkeys(doc_ids))
    for i in range(0, len(unique), 100):
        chunk = unique[i : i + 100]
        resp = await client.post(
            "/api/v1/documents/batch-delete",
            headers=headers,
            json={"document_ids": chunk, "permanent": True},
        )
        if resp.status_code != 200:
            failed.append({"batch": i, "status": resp.status_code, "body": resp.text[:200]})
            continue
        data = resp.json().get("data") or {}
        deleted.extend(data.get("deleted") or [])
        failed.extend(data.get("failed") or [])
    return {"deleted_count": len(deleted), "failed": failed}


async def find_orphan_stress_docs(client: httpx.AsyncClient, token: str) -> list[str]:
    """扫描个人库，清理遗留压测文档。"""
    headers = {"Authorization": f"Bearer {token}"}
    found: list[str] = []
    page = 1
    while page <= 20:
        resp = await client.get(
            f"/api/v1/documents?scope=personal&page={page}&page_size=100&keyword={STRESS_TITLE_PREFIX}",
            headers=headers,
        )
        if resp.status_code != 200:
            break
        items = (resp.json().get("data") or {}).get("items") or []
        if not items:
            break
        for item in items:
            title = (item.get("title") or "")
            if title.startswith(STRESS_TITLE_PREFIX):
                found.append(str(item["id"]))
        if len(items) < 100:
            break
        page += 1
    return found


def print_report(reports: list[ScenarioReport], pg_before: dict, pg_after: dict) -> None:
    print("\n" + "=" * 72)
    print("压力测试报告")
    print("=" * 72)
    print("\n[PostgreSQL / 连接池]")
    print(json.dumps({"before": pg_before, "after": pg_after}, ensure_ascii=False, indent=2))
    print("\n[场景结果]")
    for rep in reports:
        print(json.dumps(rep.summary(), ensure_ascii=False, indent=2))
    print("=" * 72)

    # 简单判定
    pool_exhausted = any(r.status_503 > 0 for r in reports)
    low_ok = any(r.ok / r.total < 0.95 for r in reports if r.total > 0)
    if pool_exhausted:
        print("\n⚠ 检测到 503（可能为连接池耗尽或熔断），建议增大 DB_POOL_SIZE/OVERFLOW 或检查长占连接。")
    elif low_ok:
        print("\n⚠ 部分场景成功率 < 95%，请查看 other_errors 与 p99 延迟。")
    else:
        print("\n✓ 各场景成功率 ≥ 95%，未观察到连接池 503。")


async def async_main(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    timeout = httpx.Timeout(args.timeout, connect=10.0)
    limits = httpx.Limits(max_connections=args.concurrency + 20, max_keepalive_connections=50)

    pg_before = pg_connection_stats()
    reports: list[ScenarioReport] = []
    created_doc_ids: list[str] = []

    async with httpx.AsyncClient(base_url=base, timeout=timeout, limits=limits) as client:
        print(f"目标: {base}")
        token = await login(client, args.account, args.password)
        print("登录成功")

        # 1. 健康检查 burst
        print(f"\n[1/4] health burst: {args.health_requests} 请求, 并发 {args.concurrency}")
        reports.append(
            await scenario_health_burst(
                client, total=args.health_requests, concurrency=args.concurrency
            )
        )

        # 2. 混合读（模拟在线用户）
        print(f"\n[2/4] mixed reads: {args.concurrency} 虚拟用户")
        reports.append(
            await scenario_mixed_reads(
                client, token, virtual_users=args.concurrency, concurrency=args.concurrency
            )
        )

        # 3. 持续读压
        print(f"\n[3/4] sustained reads: {args.sustain_sec}s @ 并发 {args.concurrency}")
        reports.append(
            await scenario_sustained_reads(
                client, token, duration_sec=args.sustain_sec, concurrency=args.concurrency
            )
        )

        # 4. 解析入队 burst
        if not args.skip_parse and args.parse_jobs > 0:
            print(
                f"\n[4/4] parse enqueue: {args.parse_jobs} 文档, 并发 {args.parse_concurrency}"
            )
            parse_report, doc_ids = await scenario_parse_enqueue_burst(
                client,
                token,
                parse_jobs=args.parse_jobs,
                concurrency=args.parse_concurrency,
            )
            reports.append(parse_report)
            created_doc_ids.extend(doc_ids)
        else:
            print("\n[4/4] 跳过解析入队 (--skip-parse 或 --parse-jobs 0)")

        pg_mid = pg_connection_stats()

        # 清理
        print("\n清理压测数据...")
        orphan = await find_orphan_stress_docs(client, token)
        all_ids = list(dict.fromkeys(created_doc_ids + orphan))
        cleanup = await cleanup_stress_documents(client, token, all_ids)
        print(
            f"已删除 {cleanup['deleted_count']} 个压测文档"
            + (f"，失败 {len(cleanup['failed'])}" if cleanup["failed"] else "")
        )

    pg_after = pg_connection_stats()
    print_report(reports, pg_before, pg_after)
    if pg_mid.get("pool_checked_out", 0) > pg_before.get("db_pool_config", {}).get("size", 15):
        print(
            f"\n注: 压测峰值 checked_out={pg_mid.get('pool_checked_out')} "
            f"(脚本进程独立连接池，仅供参考)"
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="平台 API 吞吐量 / 压力测试")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=200,
        help="模拟同时在线用户数（读场景）",
    )
    parser.add_argument(
        "--parse-jobs",
        type=int,
        default=200,
        help="并发创建并触发解析的文档数",
    )
    parser.add_argument(
        "--parse-concurrency",
        type=int,
        default=50,
        help="解析入队场景并发上限（避免本地 MinIO/KnowFlow 瞬间打满）",
    )
    parser.add_argument("--health-requests", type=int, default=1000)
    parser.add_argument("--sustain-sec", type=float, default=15.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--skip-parse", action="store_true")
    args = parser.parse_args()

    try:
        raise SystemExit(asyncio.run(async_main(args)))
    except KeyboardInterrupt:
        print("\n中断")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
