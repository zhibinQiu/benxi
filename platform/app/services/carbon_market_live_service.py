"""碳市场行情 — 上海环交所 CEA 官方发布 + 可配置 JSON 补充。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import httpx

from app.config import get_settings
from app.schemas.carbon_asset import AssetCode, CarbonMarketQuote
from app.services.carbon_market_ccer_service import (
    compute_live_change_pct,
    fetch_ccer_latest,
    load_ccer_cache_dict,
)
from app.services.carbon_market_series_util import get_last_cea_quote_row

logger = logging.getLogger(__name__)

_ASSET_NAMES: dict[AssetCode, str] = {
    "CEA": "全国碳排放配额（CEA）",
    "CCER": "国家核证自愿减排量（CCER）",
}

_DEMO_BASE: dict[AssetCode, dict[str, float]] = {
    "CEA": {"last": 72.5, "change": 1.2, "high": 73.8, "low": 71.2, "vol": 128_400},
    "CCER": {"last": 58.0, "change": -0.6, "high": 59.1, "low": 57.4, "vol": 42_600},
}

_UA = (
    "Mozilla/5.0 (compatible; ZhitanAI-CarbonMarket/1.0; +https://github.com/)"
)

_CEA_ARTICLE_RE = re.compile(
    r"综合价格行情为[:：]\s*"
    r"开盘价([\d.]+)元/吨，最高价([\d.]+)元/吨，最低价([\d.]+)元/吨，"
    r"收盘价([\d.]+)元/吨，收盘价较前一日(上涨|下跌)([\d.]+)%",
    re.S,
)
_CEA_VOLUME_RE = re.compile(r"(?:总成交量|全国碳排放配额总成交量)([\d,]+)吨")
_ARTICLE_LINK_RE = re.compile(r'href="(/c/(\d{4}-\d{2}-\d{2})/[^"]+\.s?html)"', re.I)

_cache_lock = Lock()
_cache: dict[str, Any] = {"expires": 0.0, "snapshot": None}


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    quotes: list[CarbonMarketQuote]
    live_count: int
    fetched_at: datetime
    hint: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_volume(text: str) -> float:
    m = _CEA_VOLUME_RE.search(text)
    if not m:
        return 0.0
    return float(m.group(1).replace(",", ""))


def _parse_cea_article(html: str, trade_date: str) -> dict[str, Any] | None:
    m = _CEA_ARTICLE_RE.search(html)
    if not m:
        return None
    open_p, high, low, close, direction, chg = m.groups()
    change_pct = float(chg)
    if direction == "下跌":
        change_pct = -change_pct
    return {
        "trade_date": trade_date,
        "open": float(open_p),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "change_pct": change_pct,
        "volume": _parse_volume(html),
    }


def _fetch_text(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, headers={"User-Agent": _UA})
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning("carbon market fetch failed %s: %s", url, e)
        return None


def _find_latest_cea_article_url(client: httpx.Client, base: str) -> tuple[str, str] | None:
    """返回 (article_url, trade_date)。"""
    year = date.today().year
    candidates: list[tuple[str, str]] = []
    for path in (f"/qgtpfqjy/mrgk/{year}n/", "/qgtpfqjy/mrgk/", "/"):
        html = _fetch_text(client, f"{base.rstrip('/')}{path}")
        if not html:
            continue
        for rel, d in _ARTICLE_LINK_RE.findall(html):
            candidates.append((d, rel))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    trade_date, rel = candidates[0]
    return f"{base.rstrip('/')}{rel}", trade_date


def fetch_cneeex_cea() -> dict[str, Any] | None:
    """从上海环境能源交易所官网解析最近交易日 CEA 综合价。"""
    settings = get_settings()
    if not settings.carbon_market_live_enabled:
        return None
    bases = [settings.carbon_market_cneeex_base_url.strip(), "https://www.cneeex.com"]
    timeout = settings.carbon_market_fetch_timeout_seconds
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for base in bases:
            if not base:
                continue
            found = _find_latest_cea_article_url(client, base)
            if not found:
                continue
            article_url, trade_date = found
            html = _fetch_text(client, article_url)
            if not html:
                continue
            parsed = _parse_cea_article(html, trade_date)
            if parsed:
                parsed["source"] = "cneeex"
                parsed["source_url"] = article_url
                return parsed
    return None


def _load_custom_json() -> list[dict[str, Any]] | None:
    url = (get_settings().carbon_market_quotes_json_url or "").strip()
    if not url:
        return None
    try:
        with httpx.Client(timeout=get_settings().carbon_market_fetch_timeout_seconds) as client:
            r = client.get(url, headers={"User-Agent": _UA})
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        logger.warning("custom carbon quotes json failed: %s", e)
        return None
    if isinstance(payload, dict) and "quotes" in payload:
        items = payload["quotes"]
    elif isinstance(payload, list):
        items = payload
    else:
        return None
    return [x for x in items if isinstance(x, dict)]


def _quote_from_demo(code: AssetCode, *, ts: datetime) -> CarbonMarketQuote:
    m = _DEMO_BASE[code]
    return CarbonMarketQuote(
        asset_code=code,
        asset_name=_ASSET_NAMES[code],
        last_price_cny=m["last"],
        change_pct=m["change"],
        high_cny=m["high"],
        low_cny=m["low"],
        volume_tco2=m["vol"],
        updated_at=ts,
        source="demo",
        trade_date=None,
        live=False,
    )


def _quote_from_ccer_row(row: dict[str, Any], ts: datetime) -> CarbonMarketQuote:
    trade_date = str(row.get("trade_date") or "")
    data = load_ccer_cache_dict()
    raw_close = row.get("close")
    if raw_close is None:
        raw_close = row.get("display_close")
    if raw_close is None:
        close = 0.0
    else:
        close = float(raw_close)
    chg = compute_live_change_pct(data, trade_date) if trade_date else 0.0
    vol = float(row.get("volume") or 0)
    return CarbonMarketQuote(
        asset_code="CCER",
        asset_name=_ASSET_NAMES["CCER"],
        last_price_cny=close,
        change_pct=chg,
        high_cny=close,
        low_cny=close,
        volume_tco2=vol,
        updated_at=ts,
        source=row.get("source", "ccer.com.cn"),
        trade_date=trade_date or None,
        live=True,
    )


def _quote_from_cea_row(row: dict[str, Any], ts: datetime) -> CarbonMarketQuote:
    return CarbonMarketQuote(
        asset_code="CEA",
        asset_name=_ASSET_NAMES["CEA"],
        last_price_cny=row["close"],
        change_pct=row["change_pct"],
        high_cny=row["high"],
        low_cny=row["low"],
        volume_tco2=row.get("volume") or 0.0,
        updated_at=ts,
        source=row.get("source", "cneeex"),
        trade_date=row.get("trade_date"),
        live=True,
    )


def _build_snapshot() -> MarketSnapshot:
    settings = get_settings()
    ts = _now()
    by_code: dict[AssetCode, CarbonMarketQuote] = {}
    hints: list[str] = []

    for item in _load_custom_json() or []:
        code = str(item.get("asset_code", "")).upper()
        if code not in _ASSET_NAMES:
            continue
        try:
            by_code[code] = CarbonMarketQuote(
                asset_code=code,  # type: ignore[arg-type]
                asset_name=str(item.get("asset_name") or _ASSET_NAMES[code]),  # type: ignore
                last_price_cny=float(item["last_price_cny"]),
                change_pct=float(item.get("change_pct", 0)),
                high_cny=float(item.get("high_cny", item["last_price_cny"])),
                low_cny=float(item.get("low_cny", item["last_price_cny"])),
                volume_tco2=float(item.get("volume_tco2", 0)),
                updated_at=ts,
                source=str(item.get("source", "custom")),
                trade_date=item.get("trade_date"),
                live=bool(item.get("live", True)),
            )
        except (KeyError, TypeError, ValueError):
            continue

    cea_row = fetch_cneeex_cea()
    if not cea_row:
        cea_row = get_last_cea_quote_row()
    if cea_row:
        by_code["CEA"] = _quote_from_cea_row(cea_row, ts)
        src = cea_row.get("source", "cneeex")
        if src == "cneeex":
            hints.append(f"CEA 行情来自上海环交所（交易日 {cea_row.get('trade_date')}）")
        else:
            hints.append(
                f"CEA 实时抓取失败，展示库中最近有效行情（交易日 {cea_row.get('trade_date')}）"
            )
    elif settings.carbon_market_live_enabled:
        hints.append("未能连接上海环交所，CEA 显示为演示价（请检查服务器外网或配置 CARBON_MARKET_QUOTES_JSON_URL）")

    ccer_row = fetch_ccer_latest()
    if ccer_row and (ccer_row.get("close") is not None or ccer_row.get("display_close") is not None):
        by_code["CCER"] = _quote_from_ccer_row(ccer_row, ts)
        hints.append(
            f"CCER 行情来自全国温室气体自愿减排交易系统（交易日 {ccer_row.get('trade_date')}）"
        )
    elif "CEA" in by_code and "CCER" not in by_code:
        ratio = settings.carbon_market_ccer_cea_ratio
        if ratio and ratio > 0:
            cea = by_code["CEA"]
            est = round(cea.last_price_cny * ratio, 2)
            by_code["CCER"] = CarbonMarketQuote(
                asset_code="CCER",
                asset_name=_ASSET_NAMES["CCER"],
                last_price_cny=est,
                change_pct=cea.change_pct,
                high_cny=round(cea.high_cny * ratio, 2),
                low_cny=round(cea.low_cny * ratio, 2),
                volume_tco2=0.0,
                updated_at=ts,
                source="estimated",
                trade_date=cea.trade_date,
                live=False,
            )
            hints.append("CCER 为按 CEA 收盘价比例估算，非官方 CCER 挂牌价")
    elif settings.carbon_market_live_enabled and "CCER" not in by_code:
        hints.append("未能连接 CCER 交易系统官网，CCER 显示为演示价")

    for code in ("CEA", "CCER"):
        if code not in by_code:
            by_code[code] = _quote_from_demo(code, ts=ts)

    quotes = [by_code[c] for c in ("CEA", "CCER")]
    live_count = sum(1 for q in quotes if q.live)
    hint = "；".join(hints) if hints else None
    return MarketSnapshot(
        quotes=quotes, live_count=live_count, fetched_at=ts, hint=hint
    )


def get_market_snapshot(*, force_refresh: bool = False) -> MarketSnapshot:
    settings = get_settings()
    ttl = max(60, settings.carbon_market_cache_ttl_seconds)
    now_ts = _now().timestamp()
    with _cache_lock:
        if (
            not force_refresh
            and _cache.get("snapshot") is not None
            and now_ts < float(_cache.get("expires", 0))
        ):
            return _cache["snapshot"]
    snap = _build_snapshot()
    with _cache_lock:
        _cache["snapshot"] = snap
        _cache["expires"] = now_ts + ttl
    return snap


def get_live_price(asset_code: AssetCode) -> float:
    snap = get_market_snapshot()
    for q in snap.quotes:
        if q.asset_code == asset_code:
            return q.last_price_cny
    return _DEMO_BASE[asset_code]["last"]
