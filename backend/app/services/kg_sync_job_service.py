"""知识图谱同步后台任务：组织 / 智能体 / 记忆 / 文档抽取 / 全量。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus, JobType
from app.models.org import User
from app.services.job_service import create_job, update_job_status

logger = logging.getLogger(__name__)

SCOPE_ORG = "org"
SCOPE_AGENTS = "agents"
SCOPE_MEMORY = "memory"
SCOPE_EXTRACT = "extract"
SCOPE_ALL = "all"

_SCOPE_LABELS = {
    SCOPE_ORG: "组织数据",
    SCOPE_AGENTS: "智能体数据",
    SCOPE_MEMORY: "智能体记忆",
    SCOPE_EXTRACT: "文档内容抽取",
    SCOPE_ALL: "全量平台数据",
}

_VALID_SCOPES = set(_SCOPE_LABELS)


def scope_label(scope: str) -> str:
    return _SCOPE_LABELS.get(scope, scope)


def enqueue_kg_sync_job(
    db: Session,
    user: User,
    *,
    scope: str,
    max_docs: int = 20,
    force: bool = False,
    discover_ontology: bool = True,
) -> Job:
    """创建 KG 同步 Job，并在 commit 后调度后台执行。"""
    scope = (scope or "").strip().lower()
    if scope not in _VALID_SCOPES:
        raise ValueError(f"无效同步范围: {scope}")

    label = scope_label(scope)
    job = create_job(
        db,
        job_type=JobType.kg_sync.value,
        created_by=user.id,
        payload={
            "scope": scope,
            "scope_label": label,
            "document_title": f"知识图谱同步 · {label}",
            "max_docs": max(1, min(int(max_docs or 20), 100)),
            "force": bool(force),
            "discover_ontology": bool(discover_ontology),
        },
        commit=False,
    )
    from app.core.db_after_commit import run_after_commit

    job_id = job.id
    run_after_commit(db, lambda: _dispatch(job_id))
    db.commit()
    db.refresh(job)
    return job


def _dispatch(job_id: uuid.UUID) -> None:
    from app.services.background_job_dispatch import dispatch_kg_sync_job

    dispatch_kg_sync_job(job_id)


def run_kg_sync_job(job_id: uuid.UUID) -> None:
    """执行知识图谱同步（同步线程 / Celery worker 入口）。"""
    import time

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        job = None
        for attempt in range(8):
            job = db.get(Job, job_id)
            if job:
                break
            if attempt < 7:
                db.close()
                time.sleep(0.25 * (attempt + 1))
                db = SessionLocal()
        if not job:
            logger.warning("KG 同步任务不存在 job=%s", job_id)
            return
        if job.status not in (JobStatus.pending.value, JobStatus.running.value):
            return

        payload = job.payload if isinstance(job.payload, dict) else {}
        scope = str(payload.get("scope") or SCOPE_ALL)
        user = db.get(User, job.created_by)
        if not user:
            update_job_status(
                db, job_id, JobStatus.failed.value, error_message="用户不存在"
            )
            return

        update_job_status(db, job_id, JobStatus.running.value, progress=5)
        try:
            stats = _run_scopes(
                db,
                user,
                scope=scope,
                max_docs=int(payload.get("max_docs") or 20),
                force=bool(payload.get("force")),
                discover_ontology=bool(payload.get("discover_ontology", True)),
                job_id=job_id,
            )
        except Exception as exc:
            logger.exception("KG 同步失败 job=%s", job_id)
            update_job_status(
                db,
                job_id,
                JobStatus.failed.value,
                error_message=str(exc)[:500],
            )
            _notify(
                db,
                user.id,
                title="知识图谱同步失败",
                body=f"「{scope_label(scope)}」同步失败：{str(exc)[:120]}",
            )
            return

        # 写回结果摘要
        job = db.get(Job, job_id)
        if job:
            merged = dict(job.payload or {})
            merged["result"] = stats
            job.payload = merged
            db.flush()
        update_job_status(db, job_id, JobStatus.done.value, progress=100)
        _notify(
            db,
            user.id,
            title="知识图谱同步完成",
            body=_result_summary(scope, stats),
            link="/system/ontology?tab=kg",
        )
        logger.info("KG 同步完成 job=%s scope=%s stats=%s", job_id, scope, stats)
    finally:
        db.close()


def _run_scopes(
    db: Session,
    user: User,
    *,
    scope: str,
    max_docs: int,
    force: bool,
    discover_ontology: bool,
    job_id: uuid.UUID,
) -> dict[str, Any]:
    stats: dict[str, Any] = {}

    async def _async_body() -> dict[str, Any]:
        from app.core.neo4j import get_neo4j
        from app.services.kg_service import KgService

        driver = await get_neo4j()
        svc = KgService(driver)
        out: dict[str, Any] = {}
        uid = str(user.id)

        steps: list[tuple[str, Any]] = []
        if scope in (SCOPE_ORG, SCOPE_ALL):
            steps.append((SCOPE_ORG, lambda: svc.sync_platform_org(db, uid)))
        if scope in (SCOPE_AGENTS, SCOPE_ALL):
            steps.append((SCOPE_AGENTS, lambda: svc.sync_platform_agents(db, uid)))
        if scope in (SCOPE_MEMORY, SCOPE_ALL):
            steps.append((SCOPE_MEMORY, lambda: svc.sync_agent_memory_to_kg(uid)))
        if scope in (SCOPE_EXTRACT, SCOPE_ALL):
            steps.append(
                (
                    SCOPE_EXTRACT,
                    lambda: svc.batch_extract_documents_from_content(
                        db,
                        uid,
                        max_docs=max_docs,
                        force=force,
                        discover_ontology=discover_ontology,
                    ),
                )
            )

        total = max(1, len(steps))
        for idx, (name, coro_factory) in enumerate(steps):
            update_job_status(
                db,
                job_id,
                JobStatus.running.value,
                progress=min(90, 10 + int(80 * idx / total)),
            )
            try:
                part = await coro_factory()
                if isinstance(part, dict):
                    if scope == SCOPE_ALL:
                        out.update({f"{name}_{k}": v for k, v in part.items()})
                    else:
                        out.update(part)
                else:
                    out[name] = part
            except Exception as exc:
                logger.warning("KG 同步子步骤失败 scope=%s step=%s: %s", scope, name, exc)
                out[f"{name}_error"] = str(exc)[:200]
                if scope != SCOPE_ALL:
                    raise
        return out

    try:
        return asyncio.run(_async_body())
    except RuntimeError:
        # 已有事件循环（少见）：丢到线程里再跑
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _async_body()).result(timeout=600)


def _result_summary(scope: str, stats: dict[str, Any]) -> str:
    label = scope_label(scope)
    parts: list[str] = []
    for key in (
        "entities_created",
        "relations_created",
        "processed",
        "users",
        "departments",
        "agents",
        "tools",
        "skills",
        "entities",
        "org_users",
        "org_departments",
        "agent_agents",
        "memory_entities",
    ):
        val = stats.get(key)
        if val:
            parts.append(f"{key}={val}")
    detail = "、".join(parts[:8]) if parts else "无变更"
    return f"「{label}」已同步：{detail}"


def _notify(
    db: Session,
    user_id: uuid.UUID,
    *,
    title: str,
    body: str,
    link: str | None = None,
) -> None:
    try:
        from app.services.notification_service import create_notification

        create_notification(
            db,
            user_id=user_id,
            title=title,
            body=body,
            link=link or "/system/ontology?tab=kg",
        )
    except Exception as exc:
        logger.debug("KG 同步通知跳过: %s", exc)
