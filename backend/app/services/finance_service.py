"""金融数据聚合服务 — A股/基金/虚拟币行情数据。

数据来源：
  - A股实时：腾讯财经 qt.gtimg.cn
  - A股 K 线：新浪财经 money.finance.sina.com.cn
  - 基金：天天基金 fundgz.1234567.com.cn / fund.eastmoney.com
  - 虚拟币：CoinGecko api.coingecko.com
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, DecimalException

import httpx
from sqlalchemy.orm import Session

from app.models.finance_watchlist import FinanceWatchlistItem

logger = logging.getLogger(__name__)

# ── 简易内存缓存 ──────────────────────────────────────────────
_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 30  # 秒，实时数据缓存 30 秒
_KLINE_CACHE_TTL = 300  # 5 分钟
_COINGECKO_CACHE_TTL = 60  # 1 分钟


def _cached(key: str, ttl: float = _CACHE_TTL):
    def _wrapper(fn):
        async def _inner(*args, **kwargs):
            now = time.time()
            entry = _cache.get(key)
            if entry and now - entry[0] < ttl:
                return entry[1]
            result = await fn(*args, **kwargs)
            _cache[key] = (now, result)
            return result
        return _inner
    return _wrapper


def _clear_cache_prefix(prefix: str) -> None:
    for k in list(_cache.keys()):
        if k.startswith(prefix):
            del _cache[k]


def _decode_unicode_escapes(s: str) -> str:
    """解码形如 \u8d35\u5dde\u8305\u53f0 的字面转义序列为实际汉字。"""
    def replacer(m):
        return chr(int(m.group(1), 16))
    return re.sub(r'\\u([0-9a-fA-F]{4})', replacer, s)


async def _fetch_text(url: str, **kwargs) -> str:
    async with httpx.AsyncClient(timeout=10, verify=False) as client:
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text


async def _fetch_json(url: str, **kwargs) -> dict | list:
    async with httpx.AsyncClient(timeout=10, verify=False) as client:
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()


# ═══════════════════════════════════════════════════════════════
#  A 股
# ═══════════════════════════════════════════════════════════════

# 常用指数代码
MARKET_INDEX_CODES = [
    "sh000001",  # 上证指数
    "sz399001",  # 深证成指
    "sz399006",  # 创业板指
    "sh000688",  # 科创 50
    "sh000300",  # 沪深 300
    "sh000016",  # 上证 50
    "sz399852",  # 中证 1000
]

_STOCK_QUOTE_CACHE_KEY = "stock:quote"
_STOCK_KLINE_CACHE_PREFIX = "stock:kline:"


async def search_stocks(query: str) -> list[dict]:
    """模糊搜索 A 股（代码或名称）。"""
    query = query.strip().upper()
    if not query:
        return []

    url = f"https://smartbox.gtimg.cn/s3/?v=3&q={query}&t=all"
    text = await _fetch_text(url)

    results = []
    # 返回格式: v_hint="sh~600519~贵州茅台~gzmt~GP-A"
    # smartbox 返回的汉字采用 \uXXXX 字面转义，需额外解码
    for line in text.strip().split("\n"):
        start = line.find('"')
        end = line.rfind('"')
        if start == -1 or end <= start:
            continue
        payload = line[start + 1:end]
        parts = payload.split("~")
        if len(parts) >= 3 and parts[0] in ("sh", "sz", "bj"):
            code = parts[1].strip()
            name = parts[2].strip()
            # 解码 smartbox 返回的 \uXXXX 字面序列
            name = _decode_unicode_escapes(name)
            results.append({"code": code, "name": name})
    return results[:20]


async def get_stock_quotes(codes: list[str]) -> list[dict]:
    """批量获取 A 股实时行情。"""
    if not codes:
        return []

    codes_str = ",".join(codes)
    url = f"https://qt.gtimg.cn/q={codes_str}"
    text = await _fetch_text(url, headers={"Referer": "https://qt.gtimg.cn"})

    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        try:
            raw = line.split("=", 1)[1].strip('"').strip(";").strip('"')
            fields = raw.split("~")
            if len(fields) < 46:
                continue
            results.append({
                "code": fields[2],
                "name": fields[1],
                "price": _to_float(fields[3]),
                "change": _to_float(fields[31]),  # 涨跌额
                "change_pct": _to_float(fields[32]),  # 涨跌幅 %
                "open": _to_float(fields[5]),
                "high": _to_float(fields[33]),
                "low": _to_float(fields[34]),
                "prev_close": _to_float(fields[4]),
                "volume": _to_int(fields[6]),  # 手
                "turnover": _to_float(fields[37]),  # 成交额（万）
                "pe": _to_float(fields[39]),  # 市盈率
                "amplitude": _to_float(fields[43]),  # 振幅 %
                "market_cap": _to_float(fields[44]),  # 流通市值（万）
                "total_market_cap": _to_float(fields[45]),  # 总市值（万）
            })
        except (IndexError, ValueError) as e:
            logger.warning("parse stock quote failed: %s", e)
    return results


async def get_stock_kline(code: str, ktype: str = "day") -> list[dict]:
    """获取 A 股 K 线数据。

    ktype: day / week / month
    """
    type_map = {"day": "101", "week": "102", "month": "103"}
    t = type_map.get(ktype, "101")
    # 新浪 K 线接口：code 需格式化，如 sh600519, sz000001
    if code.startswith("6"):
        secid = f"1.{code}"
    elif code.startswith("0") or code.startswith("3"):
        secid = f"0.{code}"
    elif code.startswith("68"):
        secid = f"1.{code}"
    else:
        secid = f"1.{code}"

    url = (
        f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"IP_MoneyMinute.getKLineJSON?symbol={code}&datalen=120&type={t}"
    )
    try:
        data = await _fetch_json(url)
        rows = []
        for item in (data or []):
            rows.append({
                "date": item.get("date") or item.get("day", ""),
                "open": _to_float(item.get("open")),
                "high": _to_float(item.get("high")),
                "low": _to_float(item.get("low")),
                "close": _to_float(item.get("close")),
                "volume": _to_float(item.get("volume", 0)),
            })
        return rows
    except Exception as e:
        logger.warning("fetch kline failed for %s: %s", code, e)
        return []


async def get_market_indices() -> list[dict]:
    """获取主要市场指数行情。"""
    return await get_stock_quotes(MARKET_INDEX_CODES)


# ═══════════════════════════════════════════════════════════════
#  基金
# ═══════════════════════════════════════════════════════════════

_FUND_SEARCH_CACHE_KEY = "fund:search"
_FUND_QUOTE_CACHE_KEY = "fund:quote"


async def search_funds(query: str) -> list[dict]:
    """搜索公募基金（代码或名称）。"""
    query = query.strip()
    if not query:
        return []

    url = (
        f"https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?"
        f"m=1&key={query}&token=webb"
    )
    data = await _fetch_json(url)
    results = []
    for item in (data.get("Data", []) or []):
        results.append({
            "code": item.get("Code", ""),
            "name": item.get("Name", ""),
            "type": item.get("Type", ""),
            "pinyin": item.get("PyName", ""),
        })
    return results[:20]


async def get_fund_quote(code: str) -> dict | None:
    """获取基金实时估值（仅盘中）。"""
    url = f"https://fundgz.1234567.com.cn/js/{code}.js"
    try:
        text = await _fetch_text(url)
        # 返回 jsonpgz({"fundcode":"...", ...});
        m = re.search(r"jsonpgz\((.+)\)", text)
        if m:
            data = _safe_json(m.group(1))
            if data:
                return {
                    "code": data.get("fundcode", code),
                    "name": data.get("name", ""),
                    "nav": _to_float(data.get("dwjz")),        # 单位净值
                    "estimated_nav": _to_float(data.get("gsz")),  # 估算净值
                    "estimated_change_pct": _to_float(data.get("gszzl")),  # 估算涨跌幅
                    "nav_date": data.get("jzrq", ""),          # 净值日期
                    "estimated_time": data.get("gztime", ""),  # 估算时间
                }
    except Exception as e:
        logger.warning("fetch fund quote failed for %s: %s", code, e)

    # 如果盘中估值失败，从东方财富获取最新净值
    return await _get_fund_nav_detail(code)


async def _get_fund_nav_detail(code: str) -> dict | None:
    """获取基金详细资料（含最新净值、收益率等）。"""
    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
    try:
        text = await _fetch_text(url)
        nav_data = _extract_var(text, "Data_netWorthTrend")
        if nav_data:
            latest = nav_data[-1]
            return {
                "code": code,
                "name": _extract_var_str(text, "fS_name") or "",
                "nav": _to_float(latest.get("y")),
                "nav_date": _to_date_str(latest.get("x")),
                "estimated_nav": None,
                "estimated_change_pct": None,
                "estimated_time": None,
            }
    except Exception as e:
        logger.warning("fetch fund detail failed for %s: %s", code, e)
    return None


async def get_fund_history(code: str, period: str = "3m") -> list[dict]:
    """获取基金历史净值。

    period: 1m / 3m / 6m / 1y / all
    """
    limit_map = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "all": 1095}
    limit = limit_map.get(period, 90)
    url = f"https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode={code}&pageIndex=1&pageSize={limit}"
    try:
        text = await _fetch_text(url, headers={"Referer": "https://fund.eastmoney.com/"})
        m = re.search(r"jQuery\((.+)\)", text)
        if not m:
            return []
        data = _safe_json(m.group(1))
        rows = []
        for item in (data.get("Data", {}).get("LSJZList", []) or []):
            nav = _to_float(item.get("DWJZ"))
            if nav is None:
                continue
            rows.append({
                "date": item.get("FSRQ", ""),
                "nav": nav,
                "acc_nav": _to_float(item.get("LJJZ")),
                "change_pct": _to_float(item.get("JZZZL")),
            })
        return rows
    except Exception as e:
        logger.warning("fetch fund history failed for %s: %s", code, e)
        return []


# ═══════════════════════════════════════════════════════════════
#  虚拟币
# ═══════════════════════════════════════════════════════════════

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


async def list_crypto(per_page: int = 50) -> list[dict]:
    """获取 Top 虚拟币行情。"""
    url = (
        f"{_COINGECKO_BASE}/coins/markets"
        f"?vs_currency=cny&order=market_cap_desc"
        f"&per_page={per_page}&page=1"
        f"&sparkline=true&price_change_percentage=1h%2C24h%2C7d"
    )
    data = await _fetch_json(url)
    results = []
    for coin in (data or []):
        results.append({
            "id": coin.get("id", ""),
            "symbol": coin.get("symbol", "").upper(),
            "name": coin.get("name", ""),
            "image": coin.get("image", ""),
            "current_price": coin.get("current_price"),
            "market_cap": coin.get("market_cap"),
            "market_cap_rank": coin.get("market_cap_rank"),
            "fully_diluted_valuation": coin.get("fully_diluted_valuation"),
            "total_volume": coin.get("total_volume"),
            "high_24h": coin.get("high_24h"),
            "low_24h": coin.get("low_24h"),
            "price_change_1h": coin.get("price_change_percentage_1h_in_currency"),
            "price_change_24h": coin.get("price_change_percentage_24h"),
            "price_change_7d": coin.get("price_change_percentage_7d_in_currency"),
            "circulating_supply": coin.get("circulating_supply"),
            "total_supply": coin.get("total_supply"),
            "ath": coin.get("ath"),
            "ath_date": coin.get("ath_date"),
            "sparkline_7d": (coin.get("sparkline_in_7d") or {}).get("price", []),
        })
    return results


async def get_crypto_quote(coin_id: str) -> dict | None:
    """获取单个虚拟币详情。"""
    url = (
        f"{_COINGECKO_BASE}/coins/{coin_id}"
        f"?localization=false&tickers=false&community_data=false"
        f"&developer_data=false&sparkline=true"
    )
    data = await _fetch_json(url)
    if not data:
        return None
    mcap = (data.get("market_data") or {})
    return {
        "id": data.get("id", ""),
        "symbol": data.get("symbol", "").upper(),
        "name": data.get("name", ""),
        "image": (data.get("image") or {}).get("large", ""),
        "current_price": mcap.get("current_price", {}).get("cny"),
        "market_cap": mcap.get("market_cap", {}).get("cny"),
        "market_cap_rank": data.get("market_cap_rank"),
        "total_volume": mcap.get("total_volume", {}).get("cny"),
        "high_24h": mcap.get("high_24h", {}).get("cny"),
        "low_24h": mcap.get("low_24h", {}).get("cny"),
        "price_change_1h": mcap.get("price_change_percentage_1h_in_currency"),
        "price_change_24h": mcap.get("price_change_percentage_24h_in_currency"),
        "price_change_7d": mcap.get("price_change_percentage_7d_in_currency"),
        "price_change_30d": mcap.get("price_change_percentage_30d_in_currency"),
        "circulating_supply": mcap.get("circulating_supply"),
        "total_supply": mcap.get("total_supply"),
        "max_supply": mcap.get("max_supply"),
        "ath": mcap.get("ath", {}).get("cny"),
        "ath_date": mcap.get("ath_date", {}).get("cny"),
        "sparkline_7d": (mcap.get("sparkline_7d") or {}).get("price", []),
        "description": (data.get("description") or {}).get("zh", ""),
    }


async def get_crypto_history(coin_id: str, days: int = 7) -> dict:
    """获取虚拟币历史价格（用于图表）。"""
    url = (
        f"{_COINGECKO_BASE}/coins/{coin_id}/market_chart"
        f"?vs_currency=cny&days={days}"
    )
    data = await _fetch_json(url)
    prices = []
    for p in (data.get("prices", []) or []):
        if len(p) >= 2:
            prices.append({
                "timestamp": int(p[0]),
                "price": p[1],
            })
    return {"prices": prices, "coin_id": coin_id}


# ═══════════════════════════════════════════════════════════════
#  理财报告（后台任务）
# ═══════════════════════════════════════════════════════════════

_REPORT_TASK_QUEUE: dict[uuid.UUID, asyncio.Task] = {}


def new_share_token() -> str:
    """生成公开分享令牌（URL-safe）。"""
    import secrets

    return secrets.token_urlsafe(32)


def ensure_share_token(db: Session, report) -> str:
    """确保报告有 share_token，缺失则补齐。"""
    if report.share_token:
        return report.share_token
    report.share_token = new_share_token()
    db.commit()
    db.refresh(report)
    return report.share_token or ""


def regenerate_share_token(db: Session, report) -> str:
    """重新生成分享令牌（覆盖旧链接）。"""
    report.share_token = new_share_token()
    db.commit()
    db.refresh(report)
    return report.share_token or ""


def revoke_share_token(db: Session, report) -> None:
    """撤销公开分享链接。"""
    report.share_token = None
    db.commit()
    db.refresh(report)


def create_report(
    db: Session,
    user_id: uuid.UUID,
    *,
    stock_code: str,
    stock_name: str,
    report_type: str,
    roundtable_type: str | None = None,
    research_direction: str | None = None,
    ai_context: str = "",
) -> FinanceReport:
    """创建报告任务记录（初始状态 pending）。"""
    from app.models.finance_report import FinanceReport

    report = FinanceReport(
        user_id=user_id,
        stock_code=stock_code,
        stock_name=stock_name,
        report_type=report_type,
        roundtable_type=roundtable_type,
        research_direction=research_direction,
        ai_context=ai_context,
        status="pending",
        share_token=None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def get_user_reports(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[FinanceReport]:
    """获取用户报告列表。"""
    from app.models.finance_report import FinanceReport
    from sqlalchemy import select

    stmt = select(FinanceReport).where(FinanceReport.user_id == user_id)
    if status:
        stmt = stmt.where(FinanceReport.status == status)
    stmt = stmt.order_by(FinanceReport.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


def get_report(db: Session, report_id: uuid.UUID) -> FinanceReport | None:
    """根据 ID 获取报告。"""
    from app.models.finance_report import FinanceReport

    return db.get(FinanceReport, report_id)


def get_report_by_share_token(db: Session, share_token: str) -> FinanceReport | None:
    """根据公开分享令牌获取已完成报告。"""
    from sqlalchemy import select

    from app.models.finance_report import FinanceReport

    token = (share_token or "").strip()
    if not token:
        return None
    return db.scalars(
        select(FinanceReport).where(FinanceReport.share_token == token)
    ).first()


def cancel_report_task(
    db: Session,
    user_id: uuid.UUID,
    report_id: uuid.UUID,
) -> FinanceReport:
    """取消后台报告任务。"""
    from app.models.finance_report import FinanceReport
    from app.models.job import Job

    report = db.get(FinanceReport, report_id)
    if not report or report.user_id != user_id:
        raise ValueError("报告不存在")
    if report.status in ("completed", "failed", "cancelled"):
        raise ValueError(f"报告状态为「{report.status}」，无法取消")

    # 标记为取消
    report.status = "cancelled"
    db.commit()
    db.refresh(report)

    # 取消关联的系统 Job
    if report.system_job_id:
        from app.services.job_service import cancel_job as cancel_system_job

        try:
            sys_job = db.get(Job, report.system_job_id)
            if sys_job:
                cancel_system_job(db, sys_job, reason="报告任务已取消")
        except (ValueError, ImportError):
            pass

    # 尝试取消正在运行的 asyncio task
    task = _REPORT_TASK_QUEUE.pop(report_id, None)
    if task and not task.done():
        task.cancel()

    return report


def _report_document_title(report) -> str:
    """生成导入文档库时的标题。"""
    title = f"「{report.stock_name} ({report.stock_code})」"
    if report.report_type == "roundtable":
        direction = "基本面" if report.research_direction == "fundamental" else "短线"
        kind = "辩论版" if report.roundtable_type == "debate" else "专业研究"
        return f"{title}{direction}圆桌 · {kind}"
    if report.report_type == "ai":
        return f"{title}AI 深度解读"
    if report.report_type == "vpa":
        return f"{title}量价会诊"
    return title


def import_report_to_library(
    db: Session,
    user,
    report_id: uuid.UUID,
    *,
    sync_knowflow: bool = True,
) -> dict:
    """将已完成理财报告导出为 Word，写入个人级文档库（未分类）。"""
    from app.core.exceptions import bad_request, not_found
    from app.models.finance_report import FinanceReport
    from app.services.report_generation_service import (
        import_report_to_library as import_markdown_to_library,
    )

    report = db.get(FinanceReport, report_id)
    if not report or report.user_id != user.id:
        raise not_found("报告不存在")
    if report.status != "completed" or not (report.content or "").strip():
        raise bad_request("报告尚未完成或内容为空")

    return import_markdown_to_library(
        db,
        user,
        title=_report_document_title(report),
        markdown=report.content,
        sync_knowflow=sync_knowflow,
        description="由理财助手导入",
    )


def delete_report(
    db: Session,
    user_id: uuid.UUID,
    report_id: uuid.UUID,
) -> bool:
    """删除报告（物理删除）。"""
    from app.models.finance_report import FinanceReport

    report = db.get(FinanceReport, report_id)
    if not report or report.user_id != user_id:
        return False

    # 如果任务还在运行，先取消
    if report.status in ("pending", "running"):
        task = _REPORT_TASK_QUEUE.pop(report_id, None)
        if task and not task.done():
            task.cancel()

    db.delete(report)
    db.commit()
    return True


def _update_report_progress(db: Session, report: FinanceReport, progress: int, step_msg: str = "") -> None:
    """更新报告进度，同时写入关联的系统 Job。"""
    report.progress = progress
    if step_msg:
        report.error_message = step_msg
    db.commit()

    if report.system_job_id:
        from app.services.job_service import update_job_status

        try:
            update_job_status(
                db,
                report.system_job_id,
                status="running" if progress < 100 else "done",
                progress=progress,
                error_message=step_msg if step_msg else None,
            )
        except ValueError:
            pass  # job 可能已被删除


async def _run_report_task(report_id: uuid.UUID) -> None:
    """后台执行报告生成 — 调用股市分析 Agent 的对应技能。"""
    from app.database import SessionLocal
    from app.models.finance_report import FinanceReport
    from app.models.org import User
    from app.services.notification_service import create_notification

    db = SessionLocal()
    try:
        report = db.get(FinanceReport, report_id)
        if not report:
            return

        if report.status == "cancelled":
            return

        user = db.get(User, report.user_id)
        if not user:
            report.status = "failed"
            report.error_message = "用户不存在"
            db.commit()
            return

        report.status = "running"
        _update_report_progress(db, report, 5, "正在准备分析...")

        db.refresh(report)
        if report.status == "cancelled":
            # 取消系统 Job
            if report.system_job_id:
                from app.services.job_service import update_job_status
                try:
                    update_job_status(db, report.system_job_id, "cancelled", progress=0, error_message="用户已取消")
                except ValueError:
                    pass
            return

        stock_display = f"{report.stock_name}({report.stock_code})"

        # 构建 skill 调用参数
        skill_name, tool_name, params = _resolve_skill_params(report)
        logger.warning("_run_report_task[%s]: resolved skill=%s tool=%s params=%s",
                     report_id, skill_name, tool_name, params)
        if not skill_name:
            report.status = "failed"
            report.error_message = "不支持的报告类型"
            db.commit()
            if report.system_job_id:
                from app.services.job_service import update_job_status
                try:
                    update_job_status(db, report.system_job_id, "failed", progress=0, error_message="不支持的报告类型")
                except ValueError:
                    pass
            return

        _update_report_progress(db, report, 15, "正在配置分析模型...")

        from app.skills.executor import invoke_skill_tool
        from app.skills.types import SkillInvocationContext

        # 进度回调：handler 内部可调用此函数更新报告进度（同步）
        def _progress_cb(progress: int, msg: str) -> None:
            _update_report_progress(db, report, progress, msg)

        ctx = SkillInvocationContext(
            db=db,
            user=user,
            conversation_id=str(report.id),
            progress_callback=_progress_cb,
        )

        # 附加股票中文名，供报告标题使用
        params["stock_name"] = report.stock_name

        # 对于 AI 解读，附加上下文（如果有）
        if report.report_type == "ai" and report.ai_context:
            params["ai_context"] = report.ai_context

        # 根据报告类型设置不同的进度提示
        if report.report_type == "ai":
            _update_report_progress(db, report, 25, "正在联网搜集资料...")
        elif report.report_type == "roundtable":
            _update_report_progress(db, report, 25, "正在采集事实数据...")
        elif report.report_type == "vpa":
            _update_report_progress(db, report, 25, "正在获取行情数据...")

        # 圆桌报告：额外启动进度时钟，每 25 秒推进一步以显示辩论轮次
        if report.report_type == "roundtable":
            _round_phases = [
                (35, "第一轮辩论中..."),
                (48, "第二轮辩论中..."),
                (60, "第三轮辩论中..."),
                (70, "主持人收束中..."),
                (80, "生成报告..."),
            ]
            _ticker_index = [0]

            async def _progress_ticker():
                while _ticker_index[0] < len(_round_phases):
                    await asyncio.sleep(25)
                    idx = _ticker_index[0]
                    if idx < len(_round_phases):
                        pct, msg = _round_phases[idx]
                        _ticker_index[0] = idx + 1
                        try:
                            _update_report_progress(db, report, pct, msg)
                        except Exception:
                            pass

            ticker_task = asyncio.create_task(_progress_ticker())
            try:
                result = await invoke_skill_tool(
                    ctx,
                    skill_name=skill_name,
                    tool_name=tool_name,
                    params=params,
                )
            finally:
                ticker_task.cancel()
        else:
            result = await invoke_skill_tool(
                ctx,
                skill_name=skill_name,
                tool_name=tool_name,
                params=params,
            )

        logger.warning("_run_report_task[%s]: invoke_skill_tool returned ok=%s summary_len=%s error=%s",
                     report_id, result.ok, len(result.summary or ""), result.error)

        _update_report_progress(db, report, 90 if result.ok else 80, "分析完成，正在整理报告...")

        content = result.summary or ""

        logger.warning("_run_report_task[%s]: content length=%s, first 200 chars=%s",
                     report_id, len(content), content[:200].replace("\n", "\\n") if content else "EMPTY")

        if not content:
            err_msg = result.error or "Skill 返回空结果"
            logger.warning("report %s: skill returned empty content (ok=%s, error=%s)",
                          report_id, result.ok, result.error)
            report.status = "failed"
            report.error_message = err_msg
            db.commit()
            if report.system_job_id:
                from app.services.job_service import update_job_status
                try:
                    update_job_status(db, report.system_job_id, "failed", progress=0, error_message=err_msg[:200])
                except ValueError:
                    pass
            create_notification(
                db,
                user_id=report.user_id,
                title=f"{report.stock_name} 报告生成失败",
                body=f"「{stock_display}」的{_type_label(report)}生成失败：{err_msg[:200]}",
                link="/system/finance",
            )
            return

        report.content = content
        report.status = "completed"
        report.progress = 100
        report.error_message = "报告已生成"
        report.completed_at = datetime.now()
        db.commit()

        # 完成系统 Job
        if report.system_job_id:
            from app.services.job_service import update_job_status
            try:
                update_job_status(db, report.system_job_id, "done", progress=100)
            except ValueError:
                pass

        create_notification(
            db,
            user_id=report.user_id,
            title=f"{report.stock_name} {_type_label(report)} 已生成",
            body=f"「{stock_display}」的{_type_label(report)}已完成，可前往查看。",
            link="/system/finance",
        )
    except Exception as e:
        logger.exception("report task failed: %s", e)
        try:
            report = db.get(FinanceReport, report_id)
            if report:
                report.status = "failed"
                report.error_message = str(e)[:500]
                db.commit()

                # 标记系统 Job 失败
                if report.system_job_id:
                    from app.services.job_service import update_job_status
                    try:
                        update_job_status(db, report.system_job_id, "failed", progress=0, error_message=str(e)[:200])
                    except ValueError:
                        pass

                create_notification(
                    db,
                    user_id=report.user_id,
                    title=f"{report.stock_name} {_type_label(report)} 生成失败",
                    body=f"「{report.stock_name}({report.stock_code})」的{_type_label(report)}生成失败：{str(e)[:200]}",
                    link="/system/finance",
                )
        except Exception:
            pass
    finally:
        db.close()
        _REPORT_TASK_QUEUE.pop(report_id, None)


def _type_label(report) -> str:
    """获取报告类型的中文标签。"""
    mapping = {
        "ai": "AI 解读",
        "roundtable": "圆桌报告",
        "vpa": "量价会诊",
    }
    base = mapping.get(report.report_type, report.report_type)

    if report.report_type == "roundtable":
        rt = {"debate": "辩论圆桌", "research": "专业研究"}.get(
            report.roundtable_type or "", ""
        )
        dr = {"fundamental": "基本面", "shortterm": "短线"}.get(
            report.research_direction or "", ""
        )
        if rt and dr:
            base = f"{rt}·{dr}"
    return base


def _resolve_skill_params(report) -> tuple[str, str, dict]:
    """根据报告类型解析对应的 Skill name、tool name 和 params。"""
    stock = f"{report.stock_code}.SH" if report.stock_code.startswith("6") else f"{report.stock_code}.SZ"

    mapping: dict[str, tuple[str, str, dict]] = {
        "ai": (
            "stock-deep-analysis",
            "analyze",
            {"stock": stock, "dimensions": "财务,估值,行业,成长,风险"},
        ),
        "roundtable": _resolve_roundtable_skill(report, stock),
        "vpa": (
            "stock-volume-price",
            "diagnose",
            {"stock": stock},
        ),
    }
    return mapping.get(report.report_type, ("", "", {}))


def _resolve_roundtable_skill(report, stock: str) -> tuple[str, str, dict]:
    """解析圆桌/研究的 skill 和参数。"""
    rt = report.roundtable_type or "debate"
    dr = report.research_direction or "fundamental"

    skills = {
        ("debate", "fundamental"): "stock-roundtable-debate-fundamental",
        ("debate", "shortterm"): "stock-roundtable-debate-shortterm",
        ("research", "fundamental"): "stock-roundtable-research-fundamental",
        ("research", "shortterm"): "stock-roundtable-research-shortterm",
    }
    skill_name = skills.get((rt, dr), "stock-roundtable-debate-fundamental")
    tool_name = "debate" if rt == "debate" else "research"
    return (skill_name, tool_name, {"stock": stock})


async def submit_report_task(report: FinanceReport) -> None:
    """提交后台报告任务，同时注册到系统任务列表。"""
    from app.database import SessionLocal
    from app.services.job_service import create_job

    db = SessionLocal()
    try:
        system_job = create_job(
            db,
            job_type="finance_report",
            created_by=report.user_id,
            payload={
                "report_id": str(report.id),
                "stock_code": report.stock_code,
                "stock_name": report.stock_name,
                "report_type": report.report_type,
            },
        )
        # 在当前 session 中重新获取 report 再更新 system_job_id
        from app.models.finance_report import FinanceReport

        db_report = db.get(FinanceReport, report.id)
        if db_report:
            db_report.system_job_id = system_job.id
        db.commit()
    finally:
        db.close()

    task = asyncio.create_task(_run_report_task(report.id))
    _REPORT_TASK_QUEUE[report.id] = task


# ═══════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════

def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return round(float(Decimal(str(v)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)), 3)
    except (ValueError, TypeError, DecimalException):
        return None


def _to_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _to_date_str(ts) -> str:
    """将时间戳或日期字符串转为 YYYY-MM-DD。"""
    if not ts:
        return ""
    if isinstance(ts, (int, float)):
        from datetime import datetime
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts)[:10]


def _safe_json(text: str) -> dict | None:
    """安全解析可能包含 padding 的 JSON 片段。"""
    import json
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_var(text: str, var_name: str) -> list | None:
    """从 JavaScript 文件中提取变量值。"""
    import json
    m = re.search(rf"var {re.escape(var_name)}\s*=\s*(\[.+?\]);", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _extract_var_str(text: str, var_name: str) -> str | None:
    """从 JavaScript 文件中提取字符串变量。"""
    m = re.search(rf"var {re.escape(var_name)}\s*=\s*[\"'](.+?)[\"']\s*;", text)
    if m:
        return m.group(1)
    return None


# ═══════════════════════════════════════════════════════════════
#  用户自选清单（Watchlist）
# ═══════════════════════════════════════════════════════════════

def list_watchlist(db: Session, user_id: uuid.UUID) -> list[FinanceWatchlistItem]:
    """获取用户的所有自选项。"""
    from sqlalchemy import select

    stmt = (
        select(FinanceWatchlistItem)
        .where(FinanceWatchlistItem.user_id == user_id)
        .order_by(FinanceWatchlistItem.sort_order.asc(), FinanceWatchlistItem.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def add_watchlist(
    db: Session,
    user_id: uuid.UUID,
    *,
    asset_type: str,
    asset_code: str,
    asset_name: str,
) -> FinanceWatchlistItem:
    """添加自选（重复则静默返回已有记录）。"""
    from sqlalchemy import select

    existing = db.scalar(
        select(FinanceWatchlistItem).where(
            FinanceWatchlistItem.user_id == user_id,
            FinanceWatchlistItem.asset_type == asset_type,
            FinanceWatchlistItem.asset_code == asset_code,
        )
    )
    if existing:
        return existing

    existing_items = list_watchlist(db, user_id)
    max_order = max((i.sort_order for i in existing_items), default=-1)

    item = FinanceWatchlistItem(
        user_id=user_id,
        asset_type=asset_type,
        asset_code=asset_code,
        asset_name=asset_name,
        sort_order=max_order + 1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def remove_watchlist(db: Session, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
    """删除自选项。"""
    item = db.get(FinanceWatchlistItem, item_id)
    if not item or item.user_id != user_id:
        return False
    db.delete(item)
    db.commit()
    return True


# ── F10 基本面数据（AKshare 封装） ──────────────────────────


async def get_f10_report(
    code: str,
    target_date: str | None = None,
    start_range: str | None = None,
    end_range: str | None = None,
    keywords: list[str] | None = None,
) -> dict:
    """获取个股完整 F10 基本面数据报告。

    参数说明
    ----------
    code : str
        股票代码，如 "000682"、"600519"
    target_date : str, optional
        估值截止日期，格式 "2026-07-17"
    start_range / end_range : str, optional
        区间涨跌幅计算的起止日期
    keywords : list[str], optional
        互动易问答关键词筛选

    返回
    -------
    dict
        包含 company_info, main_business, financial_abstract,
        profit_indicators, kline_range, fund_flow, forecast,
        holder_count, northbound, announcements, qa, summary_md
    """
    from app.services import finance_f10 as f10

    return await f10.get_full_report(
        code=code,
        target_date=target_date,
        start_range=start_range,
        end_range=end_range,
        keywords=keywords,
    )
