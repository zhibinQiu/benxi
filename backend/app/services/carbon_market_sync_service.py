"""碳行情后台自动同步（按 integrations.market_sync_period）。"""

from __future__ import annotations

import asyncio
import logging

from app.database import SessionLocal
from app.services import carbon_compliance_service as ccs

logger = logging.getLogger(__name__)

# 轮询间隔：每小时检查一次是否到期同步
_CHECK_INTERVAL_SEC = 3600


async def run_market_sync_once() -> dict | None:
    db = SessionLocal()
    try:
        settings = ccs.get_settings(db)
        if not ccs.should_auto_sync_market(settings):
            return None
        result = await ccs.sync_market_quotes(db)
        logger.info(
            "carbon market sync ok=%s cea=%s ccer=%s",
            result.get("ok"),
            (result.get("written") or {}).get("cea"),
            (result.get("written") or {}).get("ccer"),
        )
        return result
    except Exception:
        logger.exception("carbon market sync failed")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


async def _sync_loop() -> None:
    await asyncio.sleep(20)
    while True:
        try:
            await run_market_sync_once()
        except Exception:
            logger.exception("carbon market sync loop error")
        await asyncio.sleep(_CHECK_INTERVAL_SEC)


def start_carbon_market_sync() -> asyncio.Task:
    return asyncio.create_task(_sync_loop(), name="carbon-market-sync")
