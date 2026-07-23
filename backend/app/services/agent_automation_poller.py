"""自动化任务到期轮询：提示词驱动本析智能执行。"""

from __future__ import annotations

import asyncio
import logging

from app.database import SessionLocal
from app.services.agent_automation_service import execute_automation, list_due_automations

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SEC = 30


async def run_due_automations_once() -> int:
    db = SessionLocal()
    try:
        due = list_due_automations(db)
        ids = [row.id for row in due]
    finally:
        db.close()

    if not ids:
        return 0

    done = 0
    for aid in ids:
        try:
            result = await execute_automation(aid)
            if result.get("ok") or result.get("status"):
                done += 1
        except Exception:
            logger.exception("automation poll execute failed id=%s", aid)
    return done


async def _poll_loop() -> None:
    await asyncio.sleep(15)
    while True:
        try:
            n = await run_due_automations_once()
            if n:
                logger.info("automation poll executed %s task(s)", n)
        except Exception:
            logger.exception("automation poll loop error")
        await asyncio.sleep(_CHECK_INTERVAL_SEC)


def start_automation_poller() -> asyncio.Task:
    return asyncio.create_task(_poll_loop(), name="agent-automation-poller")
