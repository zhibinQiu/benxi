"""东方财富 F10 金融数据 — 通过 AKshare + 直连 API 获取。

数据来源优先级：AKshare → 直连 API 兜底。
所有方法均为 async，内部用 asyncio.to_thread 包装同步 AKshare 调用。

用法：
    from app.services import finance_f10 as f10
    report = await f10.get_full_report("000682")
    print(report["summary_md"])   # Markdown 格式摘要
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import traceback
from datetime import datetime
from typing import Any, Callable

import httpx
import pandas as pd

try:
    import akshare as ak  # type: ignore
except ImportError:  # 本地/精简环境可无 akshare，走直连 HTTP 兜底
    ak = None  # type: ignore

logger = logging.getLogger(__name__)


def _ak_fn(name: str) -> Callable | None:
    """安全取 AKshare 接口；未安装或无该函数时返回 None。"""
    if ak is None:
        return None
    return getattr(ak, name, None)

# ── 缓存 ─────────────────────────────────────────────────────
_cache: dict[str, tuple[float, Any]] = {}
_F10_CACHE_TTL = 3600  # 1 小时

# ── HTTP 客户端（直连 API 兜底用） ──────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://emweb.eastmoney.com/",
}


async def _get(url: str, params: dict | None = None) -> dict | None:
    """GET 请求 + 统一错误处理（直连 API 兜底用）。"""
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                if data.get("success") and data.get("code") == 0:
                    return data
                if data.get("code") == 0 and "data" in data:
                    return data
            return None
    except Exception as e:
        logger.debug("direct API _get failed: %s %s", url, e)
        return None


def _cached(key: str, ttl: float):
    def _wrap(fn: Callable) -> Callable:
        async def _inner(*args, **kwargs):
            cache_key = f"{key}:{args}:{kwargs}"
            now = time.time()
            entry = _cache.get(cache_key)
            if entry and now - entry[0] < ttl:
                return entry[1]
            result = await fn(*args, **kwargs)
            _cache[cache_key] = (now, result)
            return result
        return _inner
    return _wrap


async def _run_sync(fn: Callable, *args, **kwargs) -> Any:
    """在线程中执行同步 AKshare 调用，避免阻塞事件循环。"""
    if fn is None:
        raise RuntimeError("akshare function unavailable")
    return await asyncio.to_thread(fn, *args, **kwargs)


def _fmt(val: Any) -> str:
    """格式化数值。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "待获取"
    try:
        v = float(val)
        if abs(v) >= 1e8:
            return f"{v / 1e8:.2f}亿"
        if abs(v) >= 1e4:
            return f"{v / 1e4:.2f}万"
        return f"{v:.2f}"
    except (ValueError, TypeError):
        return str(val)


def _pct(val: Any) -> str:
    """格式化百分比。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "--"
    try:
        v = float(val)
        # AKshare 返回的百分比有的是 0.XX（小数）有的是 XX（已乘100）
        if abs(v) < 1 and v != 0:
            v = v * 100
        return f"{v:.2f}%"
    except (ValueError, TypeError):
        return str(val)


# ═════════════════════════════════════════════════════════════════
#  1. 公司基础信息
# ═════════════════════════════════════════════════════════════════

@_cached("stock_info", _F10_CACHE_TTL)
async def get_company_info(code: str) -> dict:
    """获取公司基础信息。"""
    try:
        df = await _run_sync(ak.stock_individual_info_em, symbol=code)
        info = {}
        for _, row in df.iterrows():
            info[row["item"]] = row["value"]
        return {
            "company_name": info.get("股票简称", ""),
            "full_name": info.get("公司名称", ""),
            "industry": info.get("行业", ""),
            "total_shares": str(info.get("总股本", "")),
            "circulating_shares": str(info.get("流通股", "")),
        }
    except Exception:
        logger.debug("akshare stock_individual_info_em failed, using direct API")
        return await _get_company_info_direct(code)


async def _get_company_info_direct(code: str) -> dict:
    """直连 API 兜底获取公司信息。"""
    params = {
        "reportName": "RPT_F10_ORG_BASICINFO",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1, "pageSize": 1, "client": "WEB",
    }
    raw = await _get("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    if not raw:
        return {}
    result = raw.get("result") or raw
    items = result.get("data", []) if isinstance(result, dict) else []
    if not items:
        return {}
    item = items[0]
    return {
        "company_name": item.get("SECURITY_NAME_ABBR", ""),
        "full_name": item.get("ORG_NAME", ""),
        "industry": (item.get("EM2016") or "").split("-")[0] if item.get("EM2016") else "",
        "total_shares": "",
        "circulating_shares": "",
    }


# ═════════════════════════════════════════════════════════════════
#  2. 主营构成
# ═════════════════════════════════════════════════════════════════

@_cached("main_biz", _F10_CACHE_TTL)
async def get_main_business(code: str) -> list[dict]:
    """获取主营构成（分产品营收与毛利率）。"""
    try:
        df = await _run_sync(ak.stock_zygc_em, symbol=code)
        df_2025 = df[df["报告期"].str.contains("2025年报", na=False)].copy()
        if df_2025.empty:
            df_2025 = df.head(10)
        result = []
        for _, row in df_2025.iterrows():
            result.append({
                "business_name": row.get("产品名称", ""),
                "revenue": _fmt(row.get("营业收入")),
                "revenue_pct": _pct(row.get("收入比例")),
                "gross_margin": _pct(row.get("毛利率")),
            })
        return result
    except Exception:
        logger.debug("akshare stock_zygc_em failed, using direct API")
        return await _get_main_business_direct(code)


async def _get_main_business_direct(code: str) -> list[dict]:
    """直连 API 兜底获取主营构成。"""
    params = {
        "reportName": "RPT_HS_MAINOP_PRODUCT",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1, "pageSize": 10,
        "sortTypes": -1, "sortColumns": "MAIN_BUSINESS_INCOME",
        "client": "WEB",
    }
    raw = await _get("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    if not raw:
        return []
    result = raw.get("result") or raw
    items = result.get("data", []) if isinstance(result, dict) else []
    result_list = []
    for item in items:
        revenue = item.get("MAIN_BUSINESS_INCOME")
        profit = item.get("MAIN_BUSINESS_RPOFIT")
        margin = (profit / revenue * 100) if (profit and revenue) else None
        result_list.append({
            "business_name": item.get("STD_PRODUCT_NAME", ""),
            "revenue": _fmt(revenue),
            "revenue_pct": "",
            "gross_margin": f"{margin:.2f}%" if margin is not None else "--",
        })
    return result_list


# ═════════════════════════════════════════════════════════════════
#  3. 财务摘要（营收、归母净利、EPS、同比）
# ═════════════════════════════════════════════════════════════════

@_cached("fin_abstract", _F10_CACHE_TTL)
async def get_financial_abstract(code: str) -> list[dict]:
    """获取财务摘要（季度/年报营收、净利润、EPS、同比）。"""
    try:
        df = await _run_sync(ak.stock_financial_abstract_ths, symbol=code)
        result = []
        for _, row in df.iterrows():
            result.append({
                "report_date": row.get("报告期", ""),
                "revenue": _fmt(row.get("营业总收入")),
                "parent_netprofit": _fmt(row.get("归母净利润")),
                "netprofit_yoy": _pct(row.get("净利润同比增长率")),
                "deducted_netprofit": _fmt(row.get("扣非净利润")),
                "basic_eps": row.get("基本每股收益"),
            })
        return result
    except Exception as e:
        logger.debug("akshare stock_financial_abstract_ths failed: %s", e)
        return []


# ═════════════════════════════════════════════════════════════════
#  4. 盈利能力指标（ROE、毛利率、净利率）
# ═════════════════════════════════════════════════════════════════

@_cached("profit_ind", _F10_CACHE_TTL)
async def get_profit_indicators(code: str) -> list[dict]:
    """获取盈利能力指标（ROE/毛利率/净利率）。"""
    try:
        df = await _run_sync(ak.stock_financial_analysis_indicator, symbol=code)
        if df is not None and not df.empty:
            result = []
            # 兼容不同版本列名
            ocf_keys = ("经营活动产生的现金流量净额", "经营现金流量净额", "经营现金流")
            for _, row in df.iterrows():
                ocf = None
                for k in ocf_keys:
                    if k in row and pd.notna(row.get(k)):
                        ocf = _fmt(row.get(k))
                        break
                result.append({
                    "report_date": row.get("报告期", ""),
                    "roe": _pct(row.get("净资产收益率")),
                    "gross_margin": _pct(row.get("销售毛利率")),
                    "net_margin": _pct(row.get("销售净利率")),
                    "basic_eps": row.get("基本每股收益"),
                    "operate_cashflow": ocf,
                })
            return result
    except Exception:
        logger.debug("akshare stock_financial_analysis_indicator failed")
    return await _get_profit_indicators_direct(code)


async def _get_profit_indicators_direct(code: str) -> list[dict]:
    """直连 API 兜底获取盈利指标。"""
    params = {
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1, "pageSize": 6,
        "sortTypes": -1, "sortColumns": "NOTICE_DATE",
        "client": "WEB",
    }
    raw = await _get("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    if not raw:
        return []
    result = raw.get("result") or raw
    items = result.get("data", []) if isinstance(result, dict) else []
    result_list = []
    for item in items:
        roe = item.get("WEIGHTAVG_ROE")
        ocf = item.get("MGJYXJJE") or item.get("OPERATE_CASH_FLOW") or item.get("NETCASH_OPERATE")
        result_list.append({
            "report_date": str(item.get("REPORTDATE", ""))[:10],
            "roe": f"{roe:.2f}%" if roe is not None else "--",
            "gross_margin": _pct(item.get("XSMLL")),
            "net_margin": _pct(item.get("XSJLL")),
            "basic_eps": item.get("BASIC_EPS"),
            "operate_cashflow": _fmt(ocf) if ocf is not None else None,
        })
    return result_list


# ═════════════════════════════════════════════════════════════════
#  5. 日线行情 & 区间涨跌幅
# ═════════════════════════════════════════════════════════════════

@_cached("kline", _F10_CACHE_TTL)
async def get_kline_range(code: str, start: str, end: str) -> dict:
    """获取区间行情与涨跌幅。"""
    try:
        df = await _run_sync(ak.stock_zh_a_hist, symbol=code, period="daily", adjust="")
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        df_range = df[(df["日期"] >= start) & (df["日期"] <= end)]
        if df_range.empty:
            return {"start_date": start, "end_date": end, "change_pct": "--", "klines": []}

        start_close = df_range.iloc[0]["收盘"]
        end_close = df_range.iloc[-1]["收盘"]
        change_pct = (end_close / start_close - 1) * 100

        klines = []
        for _, row in df_range.iterrows():
            klines.append({
                "date": row["日期"],
                "open": float(row["开盘"]),
                "close": float(row["收盘"]),
                "high": float(row["最高"]),
                "low": float(row["最低"]),
                "volume": float(row["成交量"]),
                "amount": float(row["成交额"]),
                "change_pct": float(row["涨跌幅"]),
            })

        return {
            "start_date": start,
            "end_date": end,
            "start_close": float(start_close),
            "end_close": float(end_close),
            "change_pct": f"{change_pct:.2f}%",
            "klines": klines,
        }
    except Exception as e:
        logger.debug("akshare stock_zh_a_hist failed: %s", e)
        return {"start_date": start, "end_date": end, "change_pct": "--", "klines": []}


# ═════════════════════════════════════════════════════════════════
#  6. 每日估值（PE/PB/总市值/换手率）
# ═════════════════════════════════════════════════════════════════

def _secid(code: str) -> str:
    """东财 secid：沪市 1.xxxxxx，深市/创业板 0.xxxxxx。"""
    c = (code or "").split(".")[0].strip()
    if c.startswith(("5", "6", "9")):
        return f"1.{c}"
    return f"0.{c}"


def _sec_code_prefix(code: str) -> str:
    c = (code or "").split(".")[0].strip()
    return f"SH{c}" if c.startswith(("5", "6", "9")) else f"SZ{c}"


def _tencent_symbol(code: str) -> str:
    pure = (code or "").split(".")[0].strip()
    return f"sh{pure}" if pure.startswith(("5", "6", "9")) else f"sz{pure}"


async def _quote_from_tencent(code: str) -> dict:
    """腾讯财经 qt.gtimg.cn 实时快照（push2 不可用时的稳定兜底）。"""
    pure = (code or "").split(".")[0].strip()
    url = f"https://qt.gtimg.cn/q={_tencent_symbol(pure)}"
    headers = {**_HEADERS, "Referer": "https://qt.gtimg.cn"}
    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        resp = await client.get(url)
        text = resp.text or ""
    line = text.strip().split("\n")[0] if text.strip() else ""
    if "=" not in line:
        return {}
    raw = line.split("=", 1)[1].strip().strip(";").strip('"')
    fields = raw.split("~")
    if len(fields) < 46:
        return {}

    def _f(i: int):
        try:
            v = fields[i]
            if v in ("", "-", None):
                return None
            return float(v)
        except (IndexError, TypeError, ValueError):
            return None

    # 腾讯：成交额单位万；总/流通市值单位亿元
    amount_wan = _f(37)
    total_mv_yi = _f(45)
    float_mv_yi = _f(44)
    return {
        "code": fields[2] if len(fields) > 2 else pure,
        "name": fields[1] if len(fields) > 1 else "",
        "price": _f(3),
        "change": _f(31),
        "change_pct": _f(32),
        "open": _f(5),
        "high": _f(33),
        "low": _f(34),
        "prev_close": _f(4),
        "volume": _f(6),  # 手
        "amount": (amount_wan * 1e4) if amount_wan is not None else None,
        "turnover": None,  # 腾讯字段无稳定换手，留给 push2
        "volume_ratio": None,
        "amplitude": _f(43),
        "pe_dynamic": _f(39),
        "pe_ttm": _f(39),
        "pb": None,
        "ps_ttm": None,
        "total_mv": _fmt(total_mv_yi * 1e8) if total_mv_yi is not None else "",
        "float_mv": _fmt(float_mv_yi * 1e8) if float_mv_yi is not None else "",
        "trade_date": (fields[30][:8] + " " + fields[30][8:]) if len(fields) > 30 and len(fields[30]) >= 12 else "最新",
        "source": "tencent",
    }


async def _quote_from_push2(code: str) -> dict:
    """东财 push2 实时快照。"""
    secid = _secid(code)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "invt": "2",
        "fltt": "2",
        # 价量 + 涨跌 + 换手 + 市值估值 + 量比/外盘内盘（若有）
        "fields": (
            "f43,f57,f58,f169,f170,f46,f44,f45,f168,f47,f48,f60,"
            "f116,f117,f162,f167,f163,f164,f92,f71,f50,f161,f171"
        ),
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {
        "User-Agent": _HEADERS["User-Agent"],
        "Referer": "https://quote.eastmoney.com/",
    }
    async with httpx.AsyncClient(timeout=8, headers=headers) as client:
        resp = await client.get(url, params=params)
        raw = resp.json()
    data = (raw or {}).get("data") or {}
    if not data:
        return {}

    def _num(key: str):
        v = data.get(key)
        if v is None or v == "-" or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _mv(key: str) -> str:
        v = _num(key)
        if v is None:
            return ""
        return _fmt(v)

    return {
        "code": str(data.get("f57") or code),
        "name": str(data.get("f58") or ""),
        "price": _num("f43"),
        "change": _num("f169"),
        "change_pct": _num("f170"),
        "open": _num("f46"),
        "high": _num("f44"),
        "low": _num("f45"),
        "prev_close": _num("f60"),
        "volume": _num("f47"),  # 手
        "amount": _num("f48"),  # 元
        "turnover": _num("f168"),
        "volume_ratio": _num("f50"),
        "amplitude": _num("f171"),
        "pe_dynamic": _num("f162"),
        "pe_ttm": _num("f163"),
        "pb": _num("f167"),
        "ps_ttm": None,
        "total_mv": _mv("f116"),
        "float_mv": _mv("f117"),
        "trade_date": "最新交易日",
        "source": "push2",
    }


async def _quote_from_ak_indicator(code: str) -> dict:
    """AKshare stock_a_indicator_lg 兜底估值序列（取最新一行）。"""
    fn = _ak_fn("stock_a_indicator_lg")
    if fn is None:
        return {}
    df = await _run_sync(fn, symbol=code)
    if df is None or getattr(df, "empty", True):
        return {}
    row = df.iloc[-1]
    def _g(*keys):
        for k in keys:
            if k in row and pd.notna(row.get(k)):
                try:
                    return float(row.get(k))
                except (TypeError, ValueError):
                    return row.get(k)
        return None
    return {
        "code": code,
        "name": "",
        "price": _g("close", "收盘"),
        "change_pct": None,
        "turnover": _g("turnover", "换手率"),
        "pe_dynamic": _g("pe", "pe_ttm", "市盈率"),
        "pe_ttm": _g("pe_ttm", "市盈率TTM"),
        "pb": _g("pb", "市净率"),
        "ps_ttm": _g("ps", "ps_ttm", "市销率"),
        "total_mv": _fmt(_g("total_mv", "总市值")) if _g("total_mv", "总市值") is not None else "",
        "float_mv": "",
        "trade_date": str(row.get("trade_date") or row.get("日期") or "最新")[:10],
        "source": "ak_indicator",
    }


async def _quote_from_hist_and_info(code: str) -> dict:
    """日线末行 + 个股信息拼装弱估值兜底。"""
    out: dict[str, Any] = {"code": code, "source": "hist+info"}
    try:
        df = await _run_sync(ak.stock_zh_a_hist, symbol=code, period="daily", adjust="")
        if df is not None and not df.empty:
            row = df.sort_values("日期").iloc[-1]
            out["price"] = float(row.get("收盘", 0) or 0) or None
            out["change_pct"] = float(row.get("涨跌幅", 0) or 0) if pd.notna(row.get("涨跌幅")) else None
            out["turnover"] = float(row.get("换手率", 0) or 0) if pd.notna(row.get("换手率")) else None
            out["trade_date"] = str(row.get("日期", ""))[:10]
    except Exception as e:
        logger.debug("quote hist fallback failed: %s", e)
    try:
        info = await get_company_info(code)
        # individual_info 常含「总市值」字段（若直连路径补上）
        for k in ("total_mv", "总市值", "market_cap"):
            if info.get(k):
                out["total_mv"] = str(info.get(k))
                break
        out["name"] = info.get("company_name") or ""
    except Exception:
        pass
    return out if out.get("price") is not None or out.get("total_mv") else {}


@_cached("quote_snap", 300)
async def get_quote_snapshot(code: str) -> dict:
    """估值快照：push2 → 腾讯行情 → AKshare indicator → 日线+个股信息。"""
    for fn in (_quote_from_push2, _quote_from_tencent, _quote_from_ak_indicator, _quote_from_hist_and_info):
        try:
            data = await fn(code)
            if data and (data.get("price") is not None or data.get("pe_dynamic") is not None or data.get("total_mv")):
                return data
        except Exception as e:
            logger.debug("get_quote_snapshot via %s failed: %s", getattr(fn, "__name__", fn), e)
    return {}


def _parse_company_survey_payload(raw: dict) -> dict:
    root = raw or {}
    result = root.get("Result") if isinstance(root.get("Result"), dict) else root
    jbzl = result.get("jbzl") if isinstance(result.get("jbzl"), dict) else {}
    if not jbzl and isinstance(result, dict):
        jbzl = result
    profile = (
        jbzl.get("gsjj")
        or jbzl.get("COMPSCOPE")
        or jbzl.get("JYFW")
        or jbzl.get("BUSINESSSCOPE")
        or jbzl.get("business_scope")
        or ""
    )
    market_position = (
        jbzl.get("COMPNAME")
        or jbzl.get("ORG_NAME_ABBR")
        or jbzl.get("SECURITY_NAME_ABBR")
        or jbzl.get("securityShortName")
        or ""
    )
    industry = (
        jbzl.get("INDUSTRYCSRC1")
        or jbzl.get("EM2016")
        or jbzl.get("HY")
        or jbzl.get("industry")
        or ""
    )
    if not profile and not market_position and not industry:
        return {}
    return {
        "profile": str(profile or "")[:800],
        "market_position": str(market_position or "")[:200],
        "business_scope": str(jbzl.get("JYFW") or jbzl.get("BUSINESSSCOPE") or profile or "")[:800],
        "industry": str(industry or "")[:120],
        "comp_name": str(jbzl.get("ORG_NAME") or jbzl.get("gsmc") or jbzl.get("companyName") or "")[:200],
        "raw_keys": list(jbzl.keys())[:40],
        "source": "company_survey",
    }


@_cached("company_survey", _F10_CACHE_TTL)
async def get_company_survey(code: str) -> dict:
    """公司概况：东财 CompanySurvey → 个股基础信息拼装。"""
    em_code = _sec_code_prefix(code)
    url = (
        "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
        f"?code={em_code}"
    )
    headers = {
        "User-Agent": _HEADERS["User-Agent"],
        "Referer": f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/Index?type=web&code={em_code}",
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await client.get(url)
            parsed = _parse_company_survey_payload(resp.json())
            if parsed:
                return parsed
    except Exception as e:
        logger.debug("get_company_survey ajax failed: %s", e)

    # 兜底：用个股信息拼「定位」文案，避免空着
    try:
        info = await get_company_info(code)
        if not info:
            return {}
        name = info.get("company_name") or info.get("full_name") or code
        industry = info.get("industry") or "—"
        return {
            "profile": (
                f"{name}（{code}）所属行业：{industry}；"
                f"总股本 {info.get('total_shares') or '—'}，流通股 {info.get('circulating_shares') or '—'}。"
            ),
            "market_position": name,
            "business_scope": f"行业：{industry}",
            "industry": industry,
            "comp_name": info.get("full_name") or name,
            "raw_keys": [],
            "source": "company_info_fallback",
        }
    except Exception as e:
        logger.debug("get_company_survey info fallback failed: %s", e)
        return {}


@_cached("valuation", _F10_CACHE_TTL)
async def get_valuation(code: str, target_date: str = "") -> list[dict]:
    """近 60 日行情序列（含换手）；PE/PB 请用 get_quote_snapshot。"""
    try:
        df = await _run_sync(ak.stock_zh_a_hist, symbol=code, period="daily", adjust="")
        df = df.sort_values("日期", ascending=False).head(60)
        result = []
        for _, row in df.iterrows():
            result.append({
                "date": str(row.get("日期", ""))[:10],
                "close": float(row.get("收盘", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
                "volume": float(row.get("成交量", 0)),
                "amount": float(row.get("成交额", 0)),
                "turnover": float(row.get("换手率", 0)) if pd.notna(row.get("换手率")) else 0,
            })
        return result
    except Exception as e:
        logger.debug("get_valuation failed: %s", e)
        return []


# ═════════════════════════════════════════════════════════════════
#  7. 主力资金流向
# ═════════════════════════════════════════════════════════════════

@_cached("fund_flow", _F10_CACHE_TTL)
async def get_fund_flow(code: str, days: int = 10) -> list[dict]:
    """获取个股主力资金流向（近 N 日）。"""
    try:
        df = await _run_sync(ak.stock_individual_fund_flow, stock=code)
        result = []
        for _, row in df.head(days).iterrows():
            result.append({
                "date": str(row.get("日期", ""))[:10],
                "main_net": _fmt(row.get("主力净流入-净额")),
                "main_net_pct": _pct(row.get("主力净流入-净占比")),
                "super_large_net": _fmt(row.get("超大户净流入-净额")),
                "large_net": _fmt(row.get("大户净流入-净额")),
                "mid_net": _fmt(row.get("中单净流入-净额")),
                "small_net": _fmt(row.get("小单净流入-净额")),
            })
        return result
    except Exception:
        logger.debug("akshare stock_individual_fund_flow failed, using direct API")
        return await _get_fund_flow_direct(code, days)


async def _get_fund_flow_direct(code: str, days: int) -> list[dict]:
    """push2 直连 API 获取资金流向。"""
    secid = f"0.{code}" if code.startswith(("0", "3", "6")) else f"1.{code}"
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55"
        f"&klt=101&lmt={days}"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            resp = await client.get(url)
            raw = resp.json()
    except Exception as e:
        logger.debug("direct fund flow failed: %s", e)
        return []

    klines = raw.get("data", {}).get("klines", []) if raw else []
    result = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 5:
            def _f(v: str) -> str:
                try: return _fmt(float(v))
                except: return v
            result.append({
                "date": parts[0],
                "main_net": _f(parts[1]),
                "main_net_pct": "",
                "super_large_net": "",
                "large_net": "",
                "mid_net": _f(parts[3]),
                "small_net": _f(parts[2]),
            })
    return result


# ═════════════════════════════════════════════════════════════════
#  8. 业绩预告
# ═════════════════════════════════════════════════════════════════

@_cached("forecast", _F10_CACHE_TTL)
async def get_forecast(code: str) -> list[dict]:
    """获取业绩预告（直连 API）。"""
    params = {
        "reportName": "RPT_F10_PROFIT_BYCHANGE",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1, "pageSize": 5,
        "sortTypes": -1, "sortColumns": "REPORT_DATE",
        "client": "WEB",
    }
    raw = await _get("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    if not raw:
        return []
    result = raw.get("result") or raw
    items = result.get("data", []) if isinstance(result, dict) else []
    result_list = []
    for item in items:
        result_list.append({
            "report_date": str(item.get("REPORT_DATE", ""))[:10],
            "forecast_type": item.get("CHANGE_TYPE_NAME", ""),
            "lower": _fmt(item.get("LOWER") or item.get("FORECAST_LOWER")),
            "upper": _fmt(item.get("UPPER") or item.get("FORECAST_UPPER")),
            "change_lower": _pct(item.get("CHANGE_MIN")),
            "change_upper": _pct(item.get("CHANGE_MAX")),
            "reason": (item.get("CHANGE_REASON") or "")[:200],
        })
    return result_list


# ═════════════════════════════════════════════════════════════════
#  9. 股东户数
# ═════════════════════════════════════════════════════════════════

@_cached("holder", _F10_CACHE_TTL)
async def get_holder_count(code: str) -> list[dict]:
    """获取季度股东户数（直连 API，避免 AKshare 全量下载）。"""
    params = {
        "reportName": "RPT_HOLDERNUM_QUARTER",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1, "pageSize": 5,
        "sortTypes": -1, "sortColumns": "END_DATE",
        "client": "WEB",
    }
    raw = await _get("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    if not raw:
        return []
    result = raw.get("result") or raw
    items = result.get("data", []) if isinstance(result, dict) else []
    result_list = []
    for item in items:
        result_list.append({
            "report_date": str(item.get("END_DATE", ""))[:10],
            "holder_count": _fmt(item.get("HOLDER_NUM")),
        })
    return result_list


# ═════════════════════════════════════════════════════════════════
#  10. 北向资金持仓
# ═════════════════════════════════════════════════════════════════

@_cached("hsgt", _F10_CACHE_TTL)
async def get_northbound_holding(code: str) -> list[dict]:
    """获取沪深股通北向资金持仓（直连 API）。"""
    params = {
        "reportName": "RPT_HSGT_HOLD_DETAIL",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1, "pageSize": 5,
        "sortTypes": -1, "sortColumns": "DATE",
        "client": "WEB",
    }
    raw = await _get("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    if not raw:
        return []
    result = raw.get("result") or raw
    items = result.get("data", []) if isinstance(result, dict) else []
    result_list = []
    for item in items:
        result_list.append({
            "date": str(item.get("DATE", ""))[:10],
            "hold_shares": _fmt(item.get("HOLD_SHARES")),
            "hold_value": _fmt(item.get("HOLD_VALUE")),
            "hold_pct": _pct(item.get("HOLD_PCT")),
        })
    return result_list


# ═════════════════════════════════════════════════════════════════
#  11. 公告列表（含分红筛选）
# ═════════════════════════════════════════════════════════════════

@_cached("announce", _F10_CACHE_TTL)
async def get_announcements(code: str) -> list[dict]:
    """获取最近公告（直连公告 API）。"""
    market = "SZ" if code.startswith(("0", "3")) else "SH"
    secucode = f"{market}{code}"
    url = (
        "https://np-anotice-stock.eastmoney.com/api/security/announcement"
        f"?sr=-1&page_size=10&page_index=1&ann_type=A&stock_list={secucode}"
        "&f_node=0&s_node=0"
    )
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://emweb.eastmoney.com/",
    }
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            resp = await client.get(url)
            raw = resp.json()
    except Exception as e:
        logger.debug("announcement API failed: %s", e)
        return []
    items = raw.get("data", {}).get("list", []) if isinstance(raw, dict) else []
    result = []
    for item in items[:10]:
        result.append({
            "title": item.get("title", ""),
            "date": str(item.get("notice_date", ""))[:10],
        })
    return result


# ═════════════════════════════════════════════════════════════════
#  12. 互动易问答（关键词筛选）
# ═════════════════════════════════════════════════════════════════

@_cached("qa", _F10_CACHE_TTL)
async def get_qa(code: str, keywords: list[str] | None = None) -> list[dict]:
    """获取互动易问答，支持关键词筛选。"""
    try:
        df = await _run_sync(ak.stock_irm_cninfo, symbol=code)
        result = []
        for _, row in df.iterrows():
            q = str(row.get("提问内容", row.get("question", "")))
            a = str(row.get("回复内容", row.get("answer", "")))
            if keywords:
                matched = any(kw in q or kw in a for kw in keywords)
                if not matched:
                    continue
            result.append({
                "date": str(row.get("提问日期", row.get("date", "")))[:10],
                "question": q[:200],
                "answer": a[:300],
            })
        return result[:20]
    except Exception as e:
        logger.debug("akshare stock_irm_cninfo failed: %s", e)
        return []


# ═════════════════════════════════════════════════════════════════
#  13. 个股新闻 / 千股千评情绪 / 股吧热帖（证据等级低于公告财报）
# ═════════════════════════════════════════════════════════════════

def _strip_em_tags(text: str) -> str:
    s = str(text or "")
    return re.sub(r"</?em>", "", s).strip()


async def _news_via_eastmoney_search(keyword: str, limit: int = 12) -> list[dict]:
    """东财搜索 JSONP（关键词用简称通常比纯代码更稳）。"""
    import json as _json

    kw = (keyword or "").strip()
    if not kw:
        return []
    cbk = f"jQuery{int(time.time() * 1000)}"
    param_obj = {
        "uid": "",
        "keyword": kw,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": min(limit, 20),
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    from urllib.parse import quote

    url = "https://search-api-web.eastmoney.com/search/jsonp"
    headers = {
        **_HEADERS,
        # Referer 必须可 ascii 编码；中文关键词做 URL 编码
        "Referer": f"https://so.eastmoney.com/news/s?keyword={quote(kw)}",
    }
    async with httpx.AsyncClient(timeout=12, headers=headers) as client:
        resp = await client.get(
            url,
            params={"cb": cbk, "param": _json.dumps(param_obj, ensure_ascii=False)},
        )
        text = (resp.text or "").replace(cbk, "").strip().strip("()")
        data = _json.loads(text) if text else {}
    rows = ((data or {}).get("result") or {}).get("cmsArticleWebOld") or []
    out = []
    for item in rows[:limit]:
        code_id = str(item.get("code") or "")
        out.append({
            "title": _strip_em_tags(item.get("title", "")),
            "summary": _strip_em_tags(str(item.get("content", "") or item.get("digest", ""))[:220]),
            "date": str(item.get("date", ""))[:19],
            "source": str(item.get("mediaName", "") or "东财"),
            "url": f"https://finance.eastmoney.com/a/{code_id}.html" if code_id else "",
        })
    return out


def _filter_news_for_stock(rows: list[dict], *, code: str, name: str = "") -> list[dict]:
    """丢掉明显不相关的噪声（如仅因代码命中的 ETF 资讯）。"""
    pure = (code or "").split(".")[0].strip()
    name = (name or "").strip()
    if not rows:
        return []
    keep = []
    for n in rows:
        blob = f"{n.get('title', '')} {n.get('summary', '')}"
        if name and name in blob:
            keep.append(n)
            continue
        if pure and pure in blob and ("ETF" not in blob.upper()) and ("联接" not in blob):
            keep.append(n)
    return keep or []


@_cached("stock_news", 900)
async def get_stock_news(code: str, limit: int = 12) -> list[dict]:
    """个股新闻：AKshare → 东财搜索（优先简称）兜底。"""
    pure = (code or "").split(".")[0].strip()
    name = ""
    try:
        info = await get_company_info(pure)
        name = (info.get("company_name") or "").strip()
    except Exception:
        pass

    # 1) AKshare
    try:
        fn = _ak_fn("stock_news_em")
        if fn is not None:
            df = await _run_sync(fn, symbol=pure)
            if df is not None and not getattr(df, "empty", True):
                out = []
                for _, row in df.head(limit * 2).iterrows():
                    out.append({
                        "title": _strip_em_tags(row.get("新闻标题", row.get("title", ""))),
                        "summary": _strip_em_tags(
                            str(row.get("新闻内容", row.get("content", "")))[:220]
                        ),
                        "date": str(row.get("发布时间", row.get("date", "")))[:19],
                        "source": str(row.get("文章来源", row.get("mediaName", "")) or "东财"),
                        "url": str(row.get("新闻链接", row.get("url", "")) or ""),
                    })
                filtered = _filter_news_for_stock(out, code=pure, name=name)[:limit]
                if filtered:
                    return filtered
                if out:
                    return out[:limit]
    except Exception as e:
        logger.debug("akshare stock_news_em failed: %s", e)

    # 2) 东财搜索：优先简称（命中更准），代码仅作补充
    keywords = [k for k in (name, pure) if k]
    best: list[dict] = []
    for kw in keywords:
        try:
            out = await _news_via_eastmoney_search(kw, max(limit, 12))
            filtered = _filter_news_for_stock(out, code=pure, name=name or kw)[:limit]
            if filtered:
                return filtered
            if out and not best:
                best = out[:limit]
        except Exception as e:
            logger.debug("eastmoney news jsonp failed for %s: %s", kw, e)
    return best


async def _datacenter_rows(report_name: str, code: str, *, page_size: int = 8) -> list[dict]:
    """东财 datacenter-web 单票查询。"""
    pure = (code or "").split(".")[0].strip()
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{pure}")',
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    headers = {**_HEADERS, "Referer": "https://data.eastmoney.com/"}
    try:
        async with httpx.AsyncClient(timeout=12, headers=headers) as client:
            resp = await client.get(url, params=params)
            raw = resp.json()
        return list(((raw or {}).get("result") or {}).get("data") or [])
    except Exception as e:
        logger.debug("datacenter %s failed: %s", report_name, e)
        return []


@_cached("retail_sentiment", 900)
async def get_retail_sentiment(code: str) -> dict:
    """千股千评：关注指数 / 历史评分 / 机构参与度（情绪辅助，非硬证据）。"""
    pure = (code or "").split(".")[0].strip()
    out: dict[str, Any] = {"code": pure}

    focus_rows = await _datacenter_rows("RPT_STOCK_MARKETFOCUS", pure, page_size=5)
    if focus_rows:
        r0 = focus_rows[0]
        out["focus_index"] = r0.get("MARKET_FOCUS")
        out["focus_date"] = str(r0.get("TRADE_DATE", ""))[:10]

    score_rows = await _datacenter_rows("RPT_STOCK_HISTORYMARK", pure, page_size=5)
    if score_rows:
        # 按诊断日取最新
        r0 = max(
            score_rows,
            key=lambda r: str(r.get("DIAGNOSE_DATE") or r.get("TRADE_DATE") or ""),
        )
        out["total_score"] = r0.get("TOTAL_SCORE")
        out["score_date"] = str(r0.get("DIAGNOSE_DATE", ""))[:10]

    org_rows = await _datacenter_rows("RPT_DMSK_TS_STOCKEVALUATE", pure, page_size=5)
    if org_rows:
        r0 = org_rows[0]
        org = r0.get("ORG_PARTICIPATE")
        try:
            org_f = float(org) if org is not None else None
            if org_f is not None and org_f <= 1.5:
                org_f = org_f * 100
            out["org_participate"] = org_f
        except (TypeError, ValueError):
            out["org_participate"] = org
        out["org_date"] = str(r0.get("TRADE_DATE", ""))[:10]

    # AKshare 细节接口兜底
    if out.get("focus_index") is None:
        try:
            fn = _ak_fn("stock_comment_detail_scrd_focus_em")
            if fn is not None:
                df = await _run_sync(fn, symbol=pure)
                if df is not None and not df.empty:
                    row = df.iloc[-1]
                    out["focus_index"] = row.get("用户关注指数")
                    out["focus_date"] = str(row.get("交易日", ""))[:10]
        except Exception as e:
            logger.debug("stock_comment focus fallback failed: %s", e)

    return out if len(out) > 1 else {}


def _parse_guba_embedded_posts(html: str, limit: int = 10) -> list[dict]:
    """从股吧列表页内嵌 JSON 字段抽取帖子（API 403/空时的兜底）。"""
    import json as _json

    titles = re.findall(r'"post_title"\s*:\s*"((?:\\.|[^"\\])*)"', html or "")
    times = re.findall(r'"post_publish_time"\s*:\s*"([^"]+)"', html or "")
    reads = re.findall(r'"post_click_count"\s*:\s*(\d+)', html or "")
    cmts = re.findall(r'"post_comment_count"\s*:\s*(\d+)', html or "")
    out = []
    for i, title in enumerate(titles[:limit]):
        if "\\" in title:
            try:
                title = _json.loads(f'"{title}"')
            except Exception:
                pass
        out.append({
            "title": str(title)[:120],
            "date": (times[i] if i < len(times) else "")[:19],
            "read": int(reads[i]) if i < len(reads) else None,
            "comment": int(cmts[i]) if i < len(cmts) else None,
        })
    return out


@_cached("guba", 900)
async def get_guba_hot_posts(code: str, limit: int = 10) -> list[dict]:
    """股吧热帖标题（散户讨论样本，证据等级最低，仅作风向参考）。"""
    pure = (code or "").split(".")[0].strip()
    headers = {
        **_HEADERS,
        "Referer": f"https://guba.eastmoney.com/list,{pure}.html",
    }
    # 1) 列表页 HTML 内嵌字段（本地对 gbapi 常 403，此路径更稳）
    try:
        list_url = f"https://guba.eastmoney.com/list,{pure}.html"
        async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as client:
            resp = await client.get(list_url)
            out = _parse_guba_embedded_posts(resp.text or "", limit)
            if out:
                return out
    except Exception as e:
        logger.debug("guba html scrape failed: %s", e)

    # 2) 东财股吧 API（字段随版本可能变化）
    urls = [
        (
            "https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist",
            {
                "code": pure,
                "p": "1",
                "ps": str(min(limit, 15)),
                "type": "0",
                "sort": "0",
            },
        ),
    ]
    for url, params in urls:
        try:
            async with httpx.AsyncClient(timeout=12, headers=headers) as client:
                resp = await client.get(url, params=params)
                raw = resp.json()
            items = (
                raw.get("re")
                or raw.get("data")
                or raw.get("relist")
                or ((raw.get("result") or {}).get("list") if isinstance(raw.get("result"), dict) else None)
                or []
            )
            if isinstance(items, dict):
                items = items.get("list") or items.get("articles") or []
            out = []
            for it in (items or [])[:limit]:
                if not isinstance(it, dict):
                    continue
                title = (
                    it.get("title")
                    or it.get("post_title")
                    or it.get("Title")
                    or it.get("article_title")
                    or ""
                )
                if not title:
                    continue
                out.append({
                    "title": str(title)[:120],
                    "date": str(
                        it.get("post_publish_time")
                        or it.get("publish_time")
                        or it.get("ShowTime")
                        or it.get("date")
                        or ""
                    )[:19],
                    "read": it.get("post_click_count") or it.get("click") or it.get("ClickCount"),
                    "comment": it.get("post_comment_count") or it.get("reply") or it.get("ReplyCount"),
                })
            if out:
                return out
        except Exception as e:
            logger.debug("guba via %s failed: %s", url, e)
    return []


# ═════════════════════════════════════════════════════════════════
#  汇总：一次获取完整 F10 报告
# ═════════════════════════════════════════════════════════════════

async def get_full_report(
    code: str,
    target_date: str | None = None,
    start_range: str | None = None,
    end_range: str | None = None,
    keywords: list[str] | None = None,
) -> dict:
    """一次获取完整的 F10 基本面数据报告。

    返回包含所有数据的字典，其中 summary_md 为 Markdown 格式摘要。
    """
    import datetime as dt

    today = dt.date.today().isoformat()
    target_date = target_date or today
    end_range = end_range or today
    start_range = start_range or (dt.date.today() - dt.timedelta(days=15)).isoformat()

    # 并行获取所有数据（每项最多等 30 秒）
    async def _run_with_timeout(name: str, coro, empty: Any = None):
        if empty is None:
            empty = []
        try:
            return await asyncio.wait_for(coro, timeout=30)
        except asyncio.TimeoutError:
            logger.warning("get_full_report task %s timeout after 30s", name)
            return empty
        except Exception as e:
            logger.warning("get_full_report task %s error: %s", name, e)
            return empty

    # 互动易：默认拉全量近期问答（分析更有用）；关键词仅作二次高亮筛选时再用
    tasks = {
        "company_info": _run_with_timeout("company_info", get_company_info(code), {}),
        "main_business": _run_with_timeout("main_business", get_main_business(code)),
        "financial_abstract": _run_with_timeout("financial_abstract", get_financial_abstract(code)),
        "profit_indicators": _run_with_timeout("profit_indicators", get_profit_indicators(code)),
        "kline_range": _run_with_timeout("kline_range", get_kline_range(code, start_range, end_range), {}),
        "valuation": _run_with_timeout("valuation", get_valuation(code, target_date)),
        "fund_flow": _run_with_timeout("fund_flow", get_fund_flow(code, 10)),
        "forecast": _run_with_timeout("forecast", get_forecast(code)),
        "holder_count": _run_with_timeout("holder_count", get_holder_count(code)),
        "northbound": _run_with_timeout("northbound", get_northbound_holding(code)),
        "announcements": _run_with_timeout("announcements", get_announcements(code)),
        "qa": _run_with_timeout("qa", get_qa(code, None)),
        "news": _run_with_timeout("news", get_stock_news(code, 12)),
        "retail_sentiment": _run_with_timeout("retail_sentiment", get_retail_sentiment(code), {}),
        "guba_posts": _run_with_timeout("guba_posts", get_guba_hot_posts(code, 10)),
        "quote_live": _run_with_timeout("quote_live", get_quote_snapshot(code), {}),
    }

    dict_keys = {"company_info", "kline_range", "retail_sentiment", "quote_live"}
    results = {}
    for name, task in tasks.items():
        try:
            results[name] = await task
        except Exception as e:
            logger.warning("get_full_report %s failed: %s", name, e)
            results[name] = {} if name in dict_keys else []

    summary_md = _build_summary_md(code, results, target_date)
    results["code"] = code
    results["summary_md"] = summary_md
    return results


# ═════════════════════════════════════════════════════════════════
#  Markdown 摘要生成
# ═════════════════════════════════════════════════════════════════

def _build_summary_md(code: str, data: dict, target_date: str) -> str:
    """将 F10 数据构建为 Markdown 摘要。"""
    lines = []
    info = data.get("company_info", {})

    # 1. 公司概况
    if info:
        lines.append(f"**公司**：{info.get('company_name', '')}（{code}）")
        if info.get("industry"):
            lines.append(f"**行业**：{info['industry']}")
        lines.append("")

    # 2. 主营构成
    mb = data.get("main_business", [])
    if mb:
        lines.append("**主营构成（分产品）**：")
        lines.append("| 产品名称 | 营业收入 | 毛利率 |")
        lines.append("|---------|---------|-------|")
        for item in mb:
            lines.append(f"| {item['business_name']} | {item['revenue']} | {item['gross_margin']} |")
        lines.append("")

    # 3. 财务摘要
    fin = data.get("financial_abstract", [])
    if fin:
        # sort descending by report_date to get the latest
        fin_sorted = sorted(fin, key=lambda x: x.get("report_date", ""), reverse=True)
        latest = fin_sorted[0]
        lines.append("**财务摘要（最新报告期）**：")
        lines.append(f"- 报告期：{latest.get('report_date', '')}")
        lines.append(f"- 营业总收入：{latest.get('revenue', '--')}")
        lines.append(f"- 归母净利润：{latest.get('parent_netprofit', '--')}")
        lines.append(f"- 扣非净利润：{latest.get('deducted_netprofit', '--')}")
        if latest.get("netprofit_yoy"):
            lines.append(f"- 净利润同比：{latest['netprofit_yoy']}")
        if latest.get("basic_eps"):
            lines.append(f"- 基本每股收益：{latest['basic_eps']}")
        lines.append("")

    # 4. 盈利能力
    pi = data.get("profit_indicators", [])
    if pi:
        lines.append("**盈利能力（最近 4 期）**：")
        lines.append("| 报告期 | ROE | 毛利率 | 净利率 |")
        lines.append("|--------|-----|-------|-------|")
        for item in pi[:4]:
            lines.append(f"| {item['report_date']} | {item['roe']} | {item['gross_margin']} | {item['net_margin']} |")
        lines.append("")

    # 5. 区间涨跌幅
    kline = data.get("kline_range", {})
    if kline.get("change_pct") and kline["change_pct"] != "--":
        lines.append(f"**区间行情（{kline.get('start_date')} ~ {kline.get('end_date')}）**：")
        lines.append(f"- 起始价：{kline.get('start_close', '--')}")
        lines.append(f"- 收盘价：{kline.get('end_close', '--')}")
        lines.append(f"- 区间涨跌幅：{kline['change_pct']}")
        lines.append("")

    # 6. 资金流向
    ff = data.get("fund_flow", [])
    if ff:
        lines.append("**主力资金流向（近 5 日）**：")
        lines.append("| 日期 | 主力净流入 | 小单净流入 |")
        lines.append("|------|----------|----------|")
        for item in ff[:5]:
            lines.append(f"| {item['date']} | {item['main_net']} | {item['small_net']} |")
        lines.append("")

    # 7. 业绩预告
    fc = data.get("forecast", [])
    if fc:
        f = fc[0]
        lines.append(f"**业绩预告**：{f.get('forecast_type', '')}")
        if f.get("lower") and f.get("upper"):
            lines.append(f"- 净利润区间：{f['lower']} ~ {f['upper']}")
            lines.append(f"- 同比变动：{f.get('change_lower', '')} ~ {f.get('change_upper', '')}")
        lines.append("")

    # 8. 股东户数
    hc = data.get("holder_count", [])
    if hc:
        h = hc[0]
        lines.append(f"**股东户数（最新）**：{h.get('holder_count', '')} | 户均持股：{h.get('avg_holding', '')}")
        lines.append("")

    # 9. 北向资金
    nb = data.get("northbound", [])
    if nb:
        latest_nb = nb[-1]
        lines.append(f"**北向资金（最新）**：持股 {latest_nb.get('hold_pct', '')} | 市值 {latest_nb.get('hold_value', '')}")
        lines.append("")

    # 10. 公告
    ann = data.get("announcements", [])
    if ann:
        lines.append("**近期公告**：")
        for a in ann[:5]:
            lines.append(f"- {a['date']} {a['title'][:60]}")
        lines.append("")

    # 11. 互动易
    qa = data.get("qa", [])
    if qa:
        lines.append("**投资者互动（节选）**：")
        for q in qa[:3]:
            lines.append(f"- {q.get('date')} Q：{str(q.get('question', ''))[:60]}")
        lines.append("")

    # 12. 实时股价
    quote = data.get("quote_live") or {}
    if isinstance(quote, dict) and (quote.get("price") is not None or quote.get("total_mv")):
        ch = quote.get("change_pct")
        ch_s = f"（{ch:+.2f}%）" if isinstance(ch, (int, float)) else ""
        bits = [f"现价 {quote.get('price')} 元{ch_s}"]
        if quote.get("turnover") is not None:
            bits.append(f"换手 {quote['turnover']}%")
        if quote.get("volume_ratio") is not None:
            bits.append(f"量比 {quote['volume_ratio']}")
        if quote.get("amplitude") is not None:
            bits.append(f"振幅 {quote['amplitude']}%")
        lines.append("**实时股价**：" + "；".join(bits))
        lines.append("")

    # 13. 软证据：新闻 / 千股千评 / 股吧（不得单独定论）
    news = data.get("news") or []
    if news:
        lines.append("**个股新闻（软证据）**：")
        for n in news[:5]:
            lines.append(f"- {n.get('date', '')} 〔{n.get('source', '')}〕{str(n.get('title', ''))[:60]}")
        lines.append("")
    sent = data.get("retail_sentiment") or {}
    if isinstance(sent, dict) and len(sent) > 1:
        bits = []
        if sent.get("focus_index") is not None:
            bits.append(f"关注指数 {sent['focus_index']}")
        if sent.get("total_score") is not None:
            bits.append(f"综合评分 {sent['total_score']}")
        if sent.get("org_participate") is not None:
            bits.append(f"机构参与度 {sent['org_participate']}")
        if bits:
            lines.append("**市场情绪·千股千评（软证据）**：" + "；".join(bits))
            lines.append("")
    guba = data.get("guba_posts") or []
    if guba:
        lines.append("**股吧热帖（软证据，散户风向）**：")
        for p in guba[:5]:
            lines.append(f"- {p.get('date', '')} {str(p.get('title', ''))[:60]}")
        lines.append("")

    # 数据来源
    lines.append(
        f"> **数据来源**：东方财富 / AKshare（结构化优先）。"
        f"新闻/千股千评/股吧为软证据，须与公告财报交叉核验。截止 {target_date}。"
    )

    return "\n".join(lines)
