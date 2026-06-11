"""碳市场行情历史序列（CEA 存库，每日收盘后定时同步；接口只读库）。"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.carbon_market import CcerDailyQuote, CeaDailyQuote
from app.schemas.carbon_asset import AssetCode, CarbonHistoryPoint, CarbonHistorySeries
from app.services.carbon_market_ccer_service import load_ccer_cache_dict
from app.services.carbon_market_live_service import (
    _ARTICLE_LINK_RE,
    _UA,
    _parse_cea_article,
    fetch_cneeex_cea,
)
from app.services.carbon_market_series_util import (
    ccer_sparse_history_points,
    fill_history_continuous,
)

logger = logging.getLogger(__name__)

_SH_TZ = ZoneInfo("Asia/Shanghai")

_ASSET_NAMES: dict[AssetCode, str] = {
    "CEA": "全国碳排放配额（CEA）",
    "CCER": "国家核证自愿减排量（CCER）",
}

_FILL_HINT = "缺失或未抓取到的交易日沿用最近有效收盘价，保证日期连续"

_sync_lock = Lock()

_ROOT = Path(__file__).resolve().parents[3]
_LEGACY_CACHE_FILE = _ROOT / ".run" / "carbon_market" / "cea_history_cache.json"


def _legacy_cache_path() -> Path:
    p = _LEGACY_CACHE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_legacy_disk_cache() -> dict[str, dict[str, Any]]:
    path = _legacy_cache_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _row_to_point(trade_date: str | date, row: dict[str, Any]) -> CarbonHistoryPoint:
    d = trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)
    return CarbonHistoryPoint(
        trade_date=d,
        open_cny=row.get("open"),
        high_cny=row.get("high"),
        low_cny=row.get("low"),
        close_cny=row["close"],
        change_pct=row.get("change_pct"),
        volume_tco2=row.get("volume"),
    )


def _quote_from_orm(row: CeaDailyQuote) -> CarbonHistoryPoint:
    return CarbonHistoryPoint(
        trade_date=row.trade_date.isoformat(),
        open_cny=row.open_cny,
        high_cny=row.high_cny,
        low_cny=row.low_cny,
        close_cny=row.close_cny,
        change_pct=row.change_pct,
        volume_tco2=row.volume_tco2,
    )


def _dict_to_orm(trade_date: date, row: dict[str, Any], *, fetched_at: datetime | None = None) -> CeaDailyQuote:
    ts = fetched_at or datetime.now(_SH_TZ)
    return CeaDailyQuote(
        trade_date=trade_date,
        open_cny=row.get("open"),
        high_cny=row.get("high"),
        low_cny=row.get("low"),
        close_cny=float(row["close"]),
        change_pct=row.get("change_pct"),
        volume_tco2=row.get("volume"),
        fetched_at=ts,
    )


def upsert_cea_quote(db: Session, trade_date: date, row: dict[str, Any]) -> None:
    if "close" not in row:
        return
    existing = db.get(CeaDailyQuote, trade_date)
    ts = datetime.now(_SH_TZ)
    if existing:
        existing.open_cny = row.get("open")
        existing.high_cny = row.get("high")
        existing.low_cny = row.get("low")
        existing.close_cny = float(row["close"])
        existing.change_pct = row.get("change_pct")
        existing.volume_tco2 = row.get("volume")
        existing.fetched_at = ts
    else:
        db.add(_dict_to_orm(trade_date, row, fetched_at=ts))


def import_legacy_cache_to_db(db: Session) -> int:
    """将旧 JSON 缓存导入数据库（仅补缺，不覆盖已有行）。"""
    data = _load_legacy_disk_cache()
    added = 0
    for d_str, row in data.items():
        if "close" not in row:
            continue
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        if db.get(CeaDailyQuote, d):
            continue
        db.add(_dict_to_orm(d, row))
        added += 1
    if added:
        db.commit()
    return added


def list_cea_quotes(db: Session, *, days: int) -> list[CeaDailyQuote]:
    cutoff = date.today() - timedelta(days=days)
    stmt = (
        select(CeaDailyQuote)
        .where(CeaDailyQuote.trade_date >= cutoff)
        .order_by(CeaDailyQuote.trade_date.asc())
    )
    return list(db.scalars(stmt).all())


def _fetch_text(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, headers={"User-Agent": _UA})
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.debug("history fetch %s: %s", url, e)
        return None


def _collect_article_urls(client: httpx.Client, base: str, years: list[int]) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for year in years:
        for path in (f"/qgtpfqjy/mrgk/{year}n/", f"/qgtpfqjy/mrgk/{year}/"):
            html = _fetch_text(client, f"{base.rstrip('/')}{path}")
            if not html:
                continue
            for rel, d in _ARTICLE_LINK_RE.findall(html):
                if d not in found:
                    found[d] = rel
    return sorted(found.items(), key=lambda x: x[0], reverse=True)


def _existing_dates(db: Session, since: date) -> set[date]:
    stmt = select(CeaDailyQuote.trade_date).where(CeaDailyQuote.trade_date >= since)
    return set(db.scalars(stmt).all())


def sync_cea_history_from_cneeex(*, days: int = 365) -> int:
    """从环交所抓取缺失日行情并写入数据库。返回本次新增/更新条数。"""
    settings = get_settings()
    if not settings.carbon_market_live_enabled:
        logger.info("CEA 历史同步已跳过（carbon_market_live_enabled=false）")
        return 0

    with _sync_lock:
        db = SessionLocal()
        try:
            import_legacy_cache_to_db(db)
            added = 0
            latest = fetch_cneeex_cea()
            if latest and latest.get("trade_date"):
                d = date.fromisoformat(str(latest["trade_date"]))
                before = db.get(CeaDailyQuote, d)
                upsert_cea_quote(db, d, latest)
                if not before:
                    added += 1
            db.commit()

            max_fetch = max(5, settings.carbon_market_history_max_fetch)
            today = date.today()
            years = [today.year, today.year - 1]
            if today.month <= 3:
                years.append(today.year - 2)
            cutoff = today - timedelta(days=max(days + 7, 30))
            existing = _existing_dates(db, cutoff)

            base = settings.carbon_market_cneeex_base_url.strip() or "https://www.cneeex.com"
            timeout = settings.carbon_market_fetch_timeout_seconds
            to_fetch: list[tuple[str, str]] = []

            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                links = _collect_article_urls(client, base, years)
                for trade_date, rel in links:
                    if trade_date < cutoff.isoformat():
                        continue
                    try:
                        d = date.fromisoformat(trade_date)
                    except ValueError:
                        continue
                    if d in existing:
                        continue
                    to_fetch.append((trade_date, rel))
                    if len(to_fetch) >= max_fetch:
                        break

                for trade_date, rel in reversed(to_fetch):
                    url = f"{base.rstrip('/')}{rel}"
                    html = _fetch_text(client, url)
                    if not html:
                        continue
                    row = _parse_cea_article(html, trade_date)
                    if not row:
                        continue
                    d = date.fromisoformat(trade_date)
                    before = db.get(CeaDailyQuote, d)
                    upsert_cea_quote(db, d, row)
                    if not before:
                        added += 1

            db.commit()
            logger.info("CEA 历史同步完成，本次新增 %s 条", added)
            return added
        except Exception:
            db.rollback()
            logger.exception("CEA 历史同步失败")
            raise
        finally:
            db.close()


def _demo_history(asset_code: AssetCode, days: int) -> list[CarbonHistoryPoint]:
    settings = get_settings()
    base = 72.0 if asset_code == "CEA" else 58.0
    if asset_code == "CCER" and settings.carbon_market_ccer_cea_ratio:
        base = 72.0 * settings.carbon_market_ccer_cea_ratio
    points: list[CarbonHistoryPoint] = []
    today = date.today()
    price = base
    for i in range(days, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        drift = ((i % 7) - 3) * 0.15
        price = max(10.0, price + drift)
        points.append(
            CarbonHistoryPoint(
                trade_date=d,
                open_cny=round(price - 0.2, 2),
                high_cny=round(price + 0.5, 2),
                low_cny=round(price - 0.6, 2),
                close_cny=round(price, 2),
                change_pct=round(drift / max(price, 1) * 100, 2),
                volume_tco2=50_000 + (i % 5) * 10_000,
            )
        )
    return points


def _cea_series_meta(rows: list[CeaDailyQuote]) -> tuple[str | None, datetime | None]:
    if not rows:
        return None, None
    return rows[-1].trade_date.isoformat(), rows[-1].fetched_at


def get_history_series(asset_code: AssetCode, *, days: int = 90) -> CarbonHistorySeries:
    """只读数据库中的历史序列，不触发外网抓取。"""
    settings = get_settings()
    days = max(7, min(days, 365))

    if asset_code == "CEA":
        db = SessionLocal()
        try:
            rows = list_cea_quotes(db, days=days)
        finally:
            db.close()
        sparse = [_quote_from_orm(r) for r in rows]
        sparse_count = len(sparse)
        points = fill_history_continuous(sparse, days=days) if sparse else []
        data_through, last_synced_at = _cea_series_meta(rows)
        source = "cneeex" if sparse else "demo"
        hint = None
        if not sparse:
            points = _demo_history("CEA", days)
            hint = "暂无环交所历史数据，请等待每日收盘后自动同步"
        else:
            if sparse_count < len(points):
                hint = _FILL_HINT
            if sparse_count < days // 2:
                extra = "历史数据仍在积累中，每日收盘后将自动补全"
                hint = f"{hint}；{extra}" if hint else extra
        return CarbonHistorySeries(
            asset_code="CEA",
            asset_name=_ASSET_NAMES["CEA"],
            source=source,
            points=points,
            hint=hint,
            data_through=data_through,
            last_synced_at=last_synced_at,
        )

    if asset_code == "CCER":
        data = load_ccer_cache_dict()
        sparse = ccer_sparse_history_points(data, days=days)
        sparse_count = len(sparse)
        points = fill_history_continuous(sparse, days=days) if sparse else []
        db = SessionLocal()
        try:
            rows = list(
                db.scalars(
                    select(CcerDailyQuote)
                    .where(
                        CcerDailyQuote.trade_date
                        >= date.today() - timedelta(days=days)
                    )
                    .order_by(CcerDailyQuote.trade_date.desc())
                ).all()
            )
        finally:
            db.close()
        data_through = rows[0].trade_date.isoformat() if rows else None
        last_synced_at = rows[0].fetched_at if rows else None
        source = "ccer.com.cn" if sparse else "demo"
        hint = None
        if not sparse:
            cea = get_history_series("CEA", days=days)
            ratio = settings.carbon_market_ccer_cea_ratio or 0.8
            points = [
                CarbonHistoryPoint(
                    trade_date=p.trade_date,
                    open_cny=round(p.open_cny * ratio, 2) if p.open_cny else None,
                    high_cny=round(p.high_cny * ratio, 2) if p.high_cny else None,
                    low_cny=round(p.low_cny * ratio, 2) if p.low_cny else None,
                    close_cny=round(p.close_cny * ratio, 2),
                    change_pct=p.change_pct,
                    volume_tco2=p.volume_tco2,
                )
                for p in cea.points
            ]
            source = "estimated"
            hint = "暂无 CCER 官方历史，当前为按 CEA 比例估算；请等待每日收盘后自动同步"
            data_through = cea.data_through
            last_synced_at = cea.last_synced_at
        else:
            if sparse_count < len(points):
                hint = _FILL_HINT
            if sparse_count < days // 2:
                extra = "CCER 历史数据仍在积累中，每日收盘后将自动补全"
                hint = f"{hint}；{extra}" if hint else extra
        return CarbonHistorySeries(
            asset_code="CCER",
            asset_name=_ASSET_NAMES["CCER"],
            source=source,
            points=points,
            hint=hint,
            data_through=data_through,
            last_synced_at=last_synced_at,
        )
