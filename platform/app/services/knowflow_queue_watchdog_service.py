"""KnowFlow 解析队列看门狗：积压且 executor 长时间未消费时告警或执行恢复命令。"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from typing import Any

from app.config import get_settings
from app.services.knowflow_queue_service import collect_knowflow_queue_metrics

logger = logging.getLogger(__name__)

_stuck_since: float | None = None
_last_recovery_at: float = 0.0


def is_knowflow_queue_stuck(metrics: dict[str, Any]) -> bool:
    """积压存在但 executor 未活跃（与系统监控标签一致）。"""
    if not metrics.get("enabled") or not metrics.get("available"):
        return False
    if metrics.get("executor_active"):
        return False
    pending = int(metrics.get("pending_tasks") or 0)
    queue_lag = int(metrics.get("queue_lag") or 0)
    parsing = int(metrics.get("parsing_documents") or 0)
    min_pending = int(get_settings().knowflow_queue_watchdog_min_pending)
    if pending >= min_pending:
        return True
    return queue_lag > 0 or parsing > 0


def evaluate_knowflow_queue_watchdog(
    metrics: dict[str, Any] | None = None,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """单次评估；返回 stuck 状态与是否触发恢复。"""
    global _stuck_since, _last_recovery_at

    settings = get_settings()
    ts = now if now is not None else time.time()
    if metrics is None:
        metrics = collect_knowflow_queue_metrics()

    out: dict[str, Any] = {
        "stuck": False,
        "stuck_minutes": 0.0,
        "recovered": False,
        "action": None,
        "metrics": metrics,
    }
    if not settings.knowflow_enabled or not settings.knowflow_queue_watchdog_enabled:
        _stuck_since = None
        return out

    if not is_knowflow_queue_stuck(metrics):
        _stuck_since = None
        return out

    if _stuck_since is None:
        _stuck_since = ts
    stuck_minutes = (ts - _stuck_since) / 60.0
    out["stuck"] = True
    out["stuck_minutes"] = round(stuck_minutes, 1)

    threshold = max(1, int(settings.knowflow_queue_watchdog_stuck_minutes))
    if stuck_minutes < threshold:
        return out

    cooldown = max(60, int(settings.knowflow_queue_watchdog_recovery_cooldown_sec))
    if _last_recovery_at > 0 and ts - _last_recovery_at < cooldown:
        logger.warning(
            "KnowFlow 队列仍卡住（%.1f 分钟），恢复冷却中（%ds）pending=%s lag=%s",
            stuck_minutes,
            int(cooldown - (ts - _last_recovery_at)),
            metrics.get("pending_tasks"),
            metrics.get("queue_lag"),
        )
        return out

    cmd = (settings.knowflow_queue_watchdog_cmd or "").strip()
    internal = bool(settings.knowflow_queue_watchdog_internal_recovery)
    if internal:
        try:
            from app.services.knowflow_parse_guard import recover_knowflow_stuck_queue

            recovery = recover_knowflow_stuck_queue()
            out["action"] = "internal_recovery"
            out["recovery"] = recovery
            logger.warning(
                "KnowFlow 队列卡住 %.1f 分钟，已执行内部恢复 pending_removed=%s documents_reset=%s",
                stuck_minutes,
                recovery.get("pending_removed"),
                recovery.get("documents_reset"),
            )
            fresh = collect_knowflow_queue_metrics()
            out["metrics"] = fresh
            if not is_knowflow_queue_stuck(fresh):
                out["recovered"] = True
                _last_recovery_at = ts
                _stuck_since = None
                logger.info("KnowFlow 队列内部恢复后已恢复消费")
                return out
        except Exception as exc:
            logger.exception("KnowFlow 队列内部恢复失败: %s", exc)

    if not cmd:
        logger.error(
            "KnowFlow 队列卡住 %.1f 分钟：pending=%s lag=%s parsing=%s，"
            "内部恢复后仍异常；可配置 KNOWFLOW_QUEUE_WATCHDOG_CMD 或执行 queue-reset",
            stuck_minutes,
            metrics.get("pending_tasks"),
            metrics.get("queue_lag"),
            metrics.get("parsing_documents"),
        )
        _stuck_since = ts
        return out

    logger.warning(
        "KnowFlow 队列卡住 %.1f 分钟，执行恢复命令：%s",
        stuck_minutes,
        cmd,
    )
    try:
        subprocess.run(
            cmd,
            shell=True,
            check=True,
            timeout=max(60, int(settings.knowflow_queue_watchdog_cmd_timeout_sec)),
        )
        out["recovered"] = True
        out["action"] = "cmd"
        _last_recovery_at = ts
        _stuck_since = None
        logger.info("KnowFlow 队列恢复命令执行成功")
    except Exception as exc:
        logger.exception("KnowFlow 队列恢复命令失败: %s", exc)
        _stuck_since = ts
    return out


async def _watchdog_loop() -> None:
    await asyncio.sleep(30)
    while True:
        settings = get_settings()
        interval = max(30, int(settings.knowflow_queue_watchdog_interval_sec))
        try:
            if settings.knowflow_enabled and settings.knowflow_queue_watchdog_enabled:
                await asyncio.to_thread(evaluate_knowflow_queue_watchdog)
        except Exception:
            logger.exception("KnowFlow 队列看门狗检查失败")
        await asyncio.sleep(interval)


def start_knowflow_queue_watchdog() -> asyncio.Task:
    return asyncio.create_task(_watchdog_loop(), name="knowflow-queue-watchdog")
