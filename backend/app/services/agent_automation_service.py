"""用户自动化任务：CRUD、到期执行（提示词驱动本析智能）、执行记录。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_automation import AgentAutomation, AgentAutomationRun
from app.models.org import User
from app.models.scheduled_notification import ScheduledNotification
from app.schemas.agent_automation import (
    AutomationCreate,
    AutomationOut,
    AutomationOverviewOut,
    AutomationRunOut,
    AutomationUpdate,
    ScheduledReminderOut,
)

_logger = logging.getLogger(__name__)

_FREQ_DELTAS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_next_run_at(
    frequency: str,
    *,
    from_dt: datetime | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    after_run: bool = False,
) -> datetime | None:
    """计算下次执行时间；超出 ends_at 或 once 已执行则返回 None。"""
    now = _as_utc(from_dt) or _utcnow()
    start = _as_utc(starts_at)
    end = _as_utc(ends_at)
    freq = (frequency or "daily").strip().lower()

    if freq == "once":
        if after_run:
            return None
        candidate = start or now
        if end is not None and candidate > end:
            return None
        return candidate

    delta = _FREQ_DELTAS.get(freq, _FREQ_DELTAS["daily"])
    if after_run:
        candidate = now + delta
    elif start is not None and start > now:
        candidate = start
    else:
        candidate = now

    if end is not None and candidate > end:
        return None
    return candidate


def serialize_automation(row: AgentAutomation) -> AutomationOut:
    return AutomationOut(
        id=row.id,
        name=row.name,
        prompt=row.prompt,
        frequency=row.frequency,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        enabled=bool(row.enabled),
        cancelled_at=row.cancelled_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def serialize_run(row: AgentAutomationRun, *, automation_name: str = "") -> AutomationRunOut:
    return AutomationRunOut(
        id=row.id,
        automation_id=row.automation_id,
        automation_name=automation_name,
        status=row.status,
        result_summary=row.result_summary,
        error=row.error,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )


def list_automations(db: Session, user_id: uuid.UUID) -> list[AgentAutomation]:
    return list(
        db.scalars(
            select(AgentAutomation)
            .where(
                AgentAutomation.user_id == user_id,
                AgentAutomation.cancelled_at.is_(None),
            )
            .order_by(AgentAutomation.created_at.desc())
        ).all()
    )


def list_runs(
    db: Session,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
) -> list[tuple[AgentAutomationRun, str]]:
    rows = db.execute(
        select(AgentAutomationRun, AgentAutomation.name)
        .join(AgentAutomation, AgentAutomation.id == AgentAutomationRun.automation_id)
        .where(AgentAutomationRun.user_id == user_id)
        .order_by(AgentAutomationRun.created_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    return [(run, name or "") for run, name in rows]


def list_reminders(db: Session, user_id: uuid.UUID, *, limit: int = 50) -> list[ScheduledNotification]:
    return list(
        db.scalars(
            select(ScheduledNotification)
            .where(ScheduledNotification.user_id == user_id)
            .order_by(ScheduledNotification.scheduled_at.desc())
            .limit(max(1, min(limit, 200)))
        ).all()
    )


def get_overview(db: Session, user_id: uuid.UUID) -> AutomationOverviewOut:
    autos = list_automations(db, user_id)
    runs = list_runs(db, user_id)
    reminders = list_reminders(db, user_id)
    return AutomationOverviewOut(
        automations=[serialize_automation(r) for r in autos],
        runs=[serialize_run(r, automation_name=name) for r, name in runs],
        reminders=[
            ScheduledReminderOut(
                id=r.id,
                title=r.title,
                body=r.body or "",
                scheduled_at=r.scheduled_at,
                sent_at=r.sent_at,
                cancelled_at=r.cancelled_at,
                created_at=r.created_at,
            )
            for r in reminders
        ],
    )


def create_automation(
    db: Session,
    user: User,
    body: AutomationCreate,
) -> AgentAutomation:
    starts = _as_utc(body.starts_at)
    ends = _as_utc(body.ends_at)
    if starts and ends and ends < starts:
        from app.core.exceptions import bad_request

        raise bad_request("结束时间不能早于开始时间")
    next_run = compute_next_run_at(
        body.frequency,
        starts_at=starts,
        ends_at=ends,
        after_run=False,
    )
    row = AgentAutomation(
        user_id=user.id,
        name=body.name.strip(),
        prompt=body.prompt.strip(),
        frequency=body.frequency,
        starts_at=starts,
        ends_at=ends,
        next_run_at=next_run if body.enabled else None,
        enabled=bool(body.enabled),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_automation(
    db: Session,
    user: User,
    automation_id: uuid.UUID,
    body: AutomationUpdate,
) -> AgentAutomation:
    row = db.get(AgentAutomation, automation_id)
    if not row or row.user_id != user.id or row.cancelled_at is not None:
        from app.core.exceptions import not_found

        raise not_found("定时任务不存在")

    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = str(data["name"]).strip()
    if "prompt" in data and data["prompt"] is not None:
        row.prompt = str(data["prompt"]).strip()
    if "frequency" in data and data["frequency"] is not None:
        row.frequency = data["frequency"]
    if "starts_at" in data:
        row.starts_at = _as_utc(data["starts_at"])
    if "ends_at" in data:
        row.ends_at = _as_utc(data["ends_at"])
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])

    starts = _as_utc(row.starts_at)
    ends = _as_utc(row.ends_at)
    if starts and ends and ends < starts:
        from app.core.exceptions import bad_request

        raise bad_request("结束时间不能早于开始时间")

    if row.enabled:
        row.next_run_at = compute_next_run_at(
            row.frequency,
            starts_at=starts,
            ends_at=ends,
            after_run=False,
        )
    else:
        row.next_run_at = None

    db.commit()
    db.refresh(row)
    return row


def delete_automation(db: Session, user: User, automation_id: uuid.UUID) -> None:
    row = db.get(AgentAutomation, automation_id)
    if not row or row.user_id != user.id or row.cancelled_at is not None:
        from app.core.exceptions import not_found

        raise not_found("定时任务不存在")
    row.cancelled_at = _utcnow()
    row.enabled = False
    row.next_run_at = None
    db.commit()


def list_due_automations(db: Session, *, now: datetime | None = None) -> list[AgentAutomation]:
    ts = _as_utc(now) or _utcnow()
    return list(
        db.scalars(
            select(AgentAutomation).where(
                AgentAutomation.enabled.is_(True),
                AgentAutomation.cancelled_at.is_(None),
                AgentAutomation.next_run_at.is_not(None),
                AgentAutomation.next_run_at <= ts,
            )
        ).all()
    )


async def execute_automation(
    automation_id: uuid.UUID,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """执行一条自动化：提示词原样走本析智能（与 /chat 同一套提示词与编排），结果推通知。

    force=True 时跳过 enabled 检查（手动「立即执行」）。
    调用 chat 前关闭 Session，只传 user_id，避免 detached User。
    """
    from app.database import SessionLocal
    from app.services.ai_chat_service import chat_with_ai_agent
    from app.services.notification_service import create_notification

    prompt: str
    user_id: uuid.UUID
    auto_name: str
    run_id: uuid.UUID

    db = SessionLocal()
    try:
        row = db.get(AgentAutomation, automation_id)
        if not row:
            return {"ok": False, "reason": "not_found"}
        if row.cancelled_at is not None:
            return {"ok": False, "reason": "disabled"}
        if not force and not row.enabled:
            return {"ok": False, "reason": "disabled"}

        now = _utcnow()
        if row.ends_at is not None and _as_utc(row.ends_at) < now:
            row.enabled = False
            row.next_run_at = None
            db.commit()
            return {"ok": False, "reason": "expired"}

        if db.get(User, row.user_id) is None:
            return {"ok": False, "reason": "user_missing"}

        prompt = (row.prompt or "").strip()
        if not prompt:
            return {"ok": False, "reason": "empty_prompt"}

        run = AgentAutomationRun(
            automation_id=row.id,
            user_id=row.user_id,
            status="running",
            started_at=now,
        )
        db.add(run)
        # 先推进 next_run，避免并发重复触发
        row.last_run_at = now
        if row.enabled:
            row.next_run_at = compute_next_run_at(
                row.frequency,
                from_dt=now,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
                after_run=True,
            )
            if row.frequency == "once" or row.next_run_at is None:
                row.enabled = False
                row.next_run_at = None
        db.commit()
        db.refresh(run)

        user_id = row.user_id
        auto_name = row.name
        run_id = run.id
    except Exception:
        db.rollback()
        _logger.exception("automation execute error id=%s", automation_id)
        raise
    finally:
        db.close()

    try:
        # 与 ai_home_chat 同一入口：相同提示词层、路由与编排；仅交付改为通知。
        result = await chat_with_ai_agent(
            message=prompt,
            history=[],
            db=None,
            user=user_id,
            conversation_id=None,
            persist_conversation=False,
            write_memory=False,
        )
        reply = str((result or {}).get("reply") or "").strip()
        if reply:
            summary = reply[:2000]
            status = "succeeded"
            error = None
        else:
            summary = None
            status = "failed"
            error = "智能体未能生成有效回复"
    except Exception as exc:
        _logger.exception("automation execute failed id=%s", automation_id)
        summary = None
        status = "failed"
        error = str(exc)[:1000]

    db2 = SessionLocal()
    try:
        run2 = db2.get(AgentAutomationRun, run_id)
        if run2:
            run2.status = status
            run2.result_summary = summary
            run2.error = error
            run2.finished_at = _utcnow()
        title = f"定时任务「{auto_name}」{'完成' if status == 'succeeded' else '失败'}"
        body = (summary or error or "")[:2000]
        create_notification(
            db2,
            user_id=user_id,
            title=title,
            body=body,
            link="/automation",
        )
        db2.commit()
    finally:
        db2.close()

    return {"ok": status == "succeeded", "run_id": str(run_id), "status": status}
