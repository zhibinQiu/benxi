"""CCER 日行情 — 全国温室气体自愿减排交易系统（ccer.com.cn）。"""

from __future__ import annotations

import json
import logging
import re
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
from app.models.carbon_market import CcerDailyQuote

logger = logging.getLogger(__name__)

_CCER_ORIGIN = "https://www.ccer.com.cn"
_CCER_LIST_JSON = "/wcm/ccer/data/2502lshq.json"
_CCER_LIST_PAGE = "/wcm/ccer/html/2502lshq/index.html"
_CCER_HTML_PREFIX = "/wcm/ccer/html/"

_CCER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_ZOOM_RE = re.compile(r'id="zoom"[^>]*>(.*?)</div>', re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

_CCER_TRADE_RE = re.compile(
    r"核证自愿减排量成交量([\d,]+)吨，成交额([\d,]+\.?\d*)元，成交均价([\d.]+)元/吨"
)
_CCER_NO_TRADE_RE = re.compile(r"核证自愿减排量无成交")

_cache_lock = Lock()
_SH_TZ = ZoneInfo("Asia/Shanghai")
_ROOT = Path(__file__).resolve().parents[3]
_CACHE_FILE = _ROOT / ".run" / "carbon_market" / "ccer_history_cache.json"


def _ccer_headers() -> dict[str, str]:
    return {
        "User-Agent": _CCER_UA,
        "Referer": f"{_CCER_ORIGIN}{_CCER_LIST_PAGE}",
        "Accept": "application/json,text/html,*/*",
    }


def _cache_path() -> Path:
    p = _CACHE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_ccer_disk_cache() -> dict[str, dict[str, Any]]:
    path = _cache_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_ccer_disk_cache(data: dict[str, dict[str, Any]]) -> None:
    path = _cache_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")


def _row_to_cache_dict(row: CcerDailyQuote) -> dict[str, Any]:
    return {
        "trade_date": row.trade_date.isoformat(),
        "traded": row.traded,
        "close": row.close_cny,
        "volume": row.volume_tco2,
        "amount_cny": row.amount_cny,
        "source": "ccer.com.cn",
        "source_url": row.source_url,
    }


def load_ccer_cache_dict() -> dict[str, dict[str, Any]]:
    """优先从数据库读取 CCER 日行情（与旧 JSON 缓存结构兼容）。"""
    db = SessionLocal()
    try:
        stmt = select(CcerDailyQuote).order_by(CcerDailyQuote.trade_date.asc())
        rows = list(db.scalars(stmt).all())
        if rows:
            return {r.trade_date.isoformat(): _row_to_cache_dict(r) for r in rows}
    finally:
        db.close()
    return load_ccer_disk_cache()


def upsert_ccer_quote(db: Session, parsed: dict[str, Any]) -> None:
    td = parsed.get("trade_date")
    if not td:
        return
    try:
        trade_date = date.fromisoformat(str(td))
    except ValueError:
        return
    ts = datetime.now(_SH_TZ)
    existing = db.get(CcerDailyQuote, trade_date)
    close = parsed.get("close")
    if close is not None:
        close = float(close)
    vol = float(parsed.get("volume") or 0)
    amt = parsed.get("amount_cny")
    if amt is not None:
        amt = float(amt)
    if existing:
        existing.traded = bool(parsed.get("traded"))
        existing.close_cny = close
        existing.volume_tco2 = vol
        existing.amount_cny = amt
        existing.source_url = parsed.get("source_url")
        existing.fetched_at = ts
    else:
        db.add(
            CcerDailyQuote(
                trade_date=trade_date,
                traded=bool(parsed.get("traded")),
                close_cny=close,
                volume_tco2=vol,
                amount_cny=amt,
                source_url=parsed.get("source_url"),
                fetched_at=ts,
            )
        )


def import_legacy_ccer_cache_to_db(db: Session) -> int:
    data = load_ccer_disk_cache()
    added = 0
    for d_str, row in data.items():
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        if db.get(CcerDailyQuote, d):
            continue
        upsert_ccer_quote(db, {**row, "trade_date": d_str})
        added += 1
    if added:
        db.commit()
    return added


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_article_text(html: str) -> str:
    m = _ZOOM_RE.search(html)
    if not m:
        return ""
    return _TAG_RE.sub("", m.group(1)).replace("\xa0", " ").strip()


def parse_ccer_daily_text(text: str, trade_date: str) -> dict[str, Any] | None:
    """从行情正文解析当日成交量与成交均价；无成交日 volume=0。"""
    if not text.strip():
        return None
    if _CCER_NO_TRADE_RE.search(text):
        return {
            "trade_date": trade_date,
            "traded": False,
            "volume": 0.0,
            "amount_cny": 0.0,
            "close": None,
        }
    m = _CCER_TRADE_RE.search(text)
    if not m:
        return None
    vol_s, amt_s, price_s = m.groups()
    return {
        "trade_date": trade_date,
        "traded": True,
        "volume": _num(vol_s),
        "amount_cny": _num(amt_s),
        "close": _num(price_s),
    }


def parse_ccer_article(html: str, trade_date: str) -> dict[str, Any] | None:
    return parse_ccer_daily_text(extract_article_text(html), trade_date)


def _trade_date_from_row(row: dict[str, Any]) -> str | None:
    pt = row.get("publishedTime")
    if isinstance(pt, str) and len(pt) >= 10:
        return pt[:10]
    url = str(row.get("url") or "")
    m = re.search(r"/(\d{8})/", url)
    if m:
        s = m.group(1)
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def fetch_ccer_list_rows(client: httpx.Client) -> list[dict[str, Any]]:
    settings = get_settings()
    base = (settings.carbon_market_ccer_base_url or _CCER_ORIGIN).rstrip("/")
    url = f"{base}{_CCER_LIST_JSON}"
    r = client.get(url, headers=_ccer_headers())
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [x for x in rows if isinstance(x, dict)]


def _article_url(base: str, rel: str) -> str:
    rel = rel.lstrip("/")
    return f"{base}{_CCER_HTML_PREFIX}{rel}"


def _fetch_article(
    client: httpx.Client, base: str, row: dict[str, Any]
) -> dict[str, Any] | None:
    trade_date = _trade_date_from_row(row)
    rel = row.get("url")
    if not trade_date or not rel:
        return None
    url = _article_url(base, str(rel))
    try:
        r = client.get(url, headers=_ccer_headers())
        r.raise_for_status()
    except Exception as e:
        logger.debug("ccer article %s: %s", url, e)
        return None
    parsed = parse_ccer_article(r.text, trade_date)
    if not parsed:
        text = extract_article_text(r.text)
        if text and get_settings().carbon_market_ccer_use_llm_parse:
            parsed = _parse_ccer_with_llm(text, trade_date)
    if parsed:
        parsed["source"] = "ccer.com.cn"
        parsed["source_url"] = url
    return parsed


def _parse_ccer_with_llm(text: str, trade_date: str) -> dict[str, Any] | None:
    try:
        from app.integrations.deepseek_client import is_configured, resolve_credentials
    except ImportError:
        return None
    if not is_configured():
        return None
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return None
    prompt = (
        "从以下 CCER 每日行情正文中提取当日核证自愿减排量交易数据。"
        "仅输出一行 JSON，字段：traded(bool), volume(float吨), amount_cny(float元), "
        "close(float|null 成交均价元/吨，无成交为null)。无成交时 traded=false volume=0。\n\n"
        f"{text[:4000]}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你只输出合法 JSON，不要其它文字。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            r.raise_for_status()
            content = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        raw = content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return {
            "trade_date": trade_date,
            "traded": bool(data.get("traded")),
            "volume": float(data.get("volume") or 0),
            "amount_cny": float(data.get("amount_cny") or 0),
            "close": float(data["close"]) if data.get("close") is not None else None,
        }
    except Exception as e:
        logger.debug("ccer llm parse failed: %s", e)
        return None


def sync_ccer_history_from_official(
    *, days: int = 365, force_recent_days: int = 7
) -> int:
    """从 CCER 官网抓取日行情并写入数据库。返回本次写入/更新条数。"""
    settings = get_settings()
    if not settings.carbon_market_live_enabled:
        logger.info("CCER 历史同步已跳过（carbon_market_live_enabled=false）")
        return 0

    max_fetch = max(5, settings.carbon_market_history_max_fetch)
    with _cache_lock:
        db = SessionLocal()
        try:
            import_legacy_ccer_cache_to_db(db)
            existing_dates = {
                r.isoformat()
                for r in db.scalars(select(CcerDailyQuote.trade_date)).all()
            }
            updated = 0
            base = (settings.carbon_market_ccer_base_url or _CCER_ORIGIN).rstrip("/")
            timeout = settings.carbon_market_fetch_timeout_seconds
            cutoff = (date.today() - timedelta(days=max(days + 14, 30))).isoformat()
            force_cutoff = (
                date.today() - timedelta(days=max(force_recent_days, 1))
            ).isoformat()

            to_fetch: list[dict[str, Any]] = []
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                try:
                    rows = fetch_ccer_list_rows(client)
                except Exception as e:
                    logger.warning("ccer list json failed: %s", e)
                    rows = []

                for row in rows:
                    td = _trade_date_from_row(row)
                    if not td or td < cutoff:
                        continue
                    if td in existing_dates and td < force_cutoff:
                        continue
                    to_fetch.append(row)

                to_fetch.sort(
                    key=lambda r: _trade_date_from_row(r) or "",
                    reverse=True,
                )
                batch = max_fetch
                if len(existing_dates) < 15:
                    batch = min(max(max_fetch, 60), 120)
                to_fetch = to_fetch[:batch]

                for row in reversed(to_fetch):
                    parsed = _fetch_article(client, base, row)
                    if not parsed:
                        continue
                    td = str(parsed["trade_date"])
                    before = db.get(CcerDailyQuote, date.fromisoformat(td))
                    upsert_ccer_quote(db, parsed)
                    if not before:
                        updated += 1
                    else:
                        updated += 1

            db.commit()
            logger.info("CCER 历史同步完成，本次处理 %s 条", updated)
            return updated
        except Exception:
            db.rollback()
            logger.exception("CCER 历史同步失败")
            raise
        finally:
            db.close()


def refresh_ccer_cache(*, days: int, max_fetch: int) -> dict[str, dict[str, Any]]:
    sync_ccer_history_from_official(days=days, force_recent_days=0)
    return load_ccer_cache_dict()


def _enrich_display_price(row: dict[str, Any], data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """无成交日沿用上一笔成交均价作为展示价。"""
    out = dict(row)
    if out.get("close") is not None:
        return out
    td = str(out.get("trade_date") or "")
    prev = _last_close_before(data, td) if td else None
    if prev is not None:
        out["display_close"] = prev
    return out


def fetch_ccer_latest() -> dict[str, Any] | None:
    """最近一条已解析的 CCER 日行情（优先数据库，否则拉取最新一篇）。"""
    data = load_ccer_cache_dict()
    if data:
        latest_date = max(data.keys())
        row = _enrich_display_price(dict(data[latest_date]), data)
        row.setdefault("source", "ccer.com.cn")
        return row

    settings = get_settings()
    if not settings.carbon_market_live_enabled:
        return None
    sync_ccer_history_from_official(days=30, force_recent_days=14)
    data = load_ccer_cache_dict()
    if not data:
        return None
    latest_date = max(data.keys())
    return _enrich_display_price(dict(data[latest_date]), data)


def _last_close_before(data: dict[str, dict[str, Any]], trade_date: str) -> float | None:
    best: float | None = None
    for d in sorted(data.keys()):
        if d >= trade_date:
            break
        row = data[d]
        if row.get("close") is not None:
            best = float(row["close"])
    return best


def ccer_rows_to_history_points(
    data: dict[str, dict[str, Any]], *, days: int
) -> list[dict[str, Any]]:
    """转为历史点 dict 列表（含无成交日与缺失自然日补全）。"""
    from app.services.carbon_market_series_util import (
        ccer_sparse_history_points,
        fill_history_continuous,
    )

    filled = fill_history_continuous(ccer_sparse_history_points(data, days=days), days=days)
    return [
        {
            "trade_date": p.trade_date,
            "close": p.close_cny,
            "open": p.open_cny,
            "high": p.high_cny,
            "low": p.low_cny,
            "change_pct": p.change_pct,
            "volume": p.volume_tco2,
        }
        for p in filled
    ]


def compute_live_change_pct(data: dict[str, dict[str, Any]], trade_date: str) -> float:
    dates = sorted(data.keys(), reverse=True)
    cur = data.get(trade_date)
    if not cur or cur.get("close") is None:
        return 0.0
    cur_close = float(cur["close"])
    for d in dates:
        if d >= trade_date:
            continue
        prev = data[d]
        if prev.get("close") is not None:
            p = float(prev["close"])
            if p > 0:
                return round((cur_close - p) / p * 100, 2)
    return 0.0
