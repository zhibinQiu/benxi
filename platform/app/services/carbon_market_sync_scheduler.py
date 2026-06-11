"""碳市场日行情定时同步（收盘后每日一次：CEA + CCER）。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.services.carbon_market_ccer_service import sync_ccer_history_from_official
from app.services.carbon_market_history_service import sync_cea_history_from_cneeex

logger = logging.getLogger(__name__)

_SH_TZ = ZoneInfo("Asia/Shanghai")


def _seconds_until_next_run() -> float:
    settings = get_settings()
    now = datetime.now(_SH_TZ)
    target = now.replace(
        hour=settings.carbon_market_history_sync_hour,
        minute=settings.carbon_market_history_sync_minute,
        second=0,
        microsecond=0,
    )
    if now >= target:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def _ran_sync_today(model) -> bool:
    from sqlalchemy import func, select

    from app.database import SessionLocal

    today = date.today()
    db = SessionLocal()
    try:
        stmt = select(func.max(model.fetched_at))
        latest = db.scalar(stmt)
        if not latest:
            return False
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=_SH_TZ)
        return latest.astimezone(_SH_TZ).date() >= today
    finally:
        db.close()


def _sync_all_market_history() -> None:
    sync_cea_history_from_cneeex()
    sync_ccer_history_from_official()


async def _market_history_sync_loop() -> None:
    from app.models.carbon_market import CcerDailyQuote, CeaDailyQuote

    await asyncio.sleep(3)
    if not _ran_sync_today(CeaDailyQuote) or not _ran_sync_today(CcerDailyQuote):
        try:
            await asyncio.to_thread(_sync_all_market_history)
        except Exception:
            logger.exception("启动时碳市场历史补同步失败")

    while True:
        delay = _seconds_until_next_run()
        logger.info("下次碳市场历史同步将在 %.0f 秒后执行", delay)
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(_sync_all_market_history)
        except Exception:
            logger.exception("定时碳市场历史同步失败")


def start_cea_history_scheduler() -> asyncio.Task:
    return asyncio.create_task(_market_history_sync_loop(), name="carbon-market-history-sync")
