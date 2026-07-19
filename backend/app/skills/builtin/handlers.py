"""内置 Skill 工具 handler — 委托现有平台服务。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any

from app.skills.types import SkillHandler, SkillInvocationContext, SkillInvocationResult

logger = logging.getLogger(__name__)

# ── 报告 .md 文件路径 ──────────────────────────────────────
_REPORT_DIR = os.path.join(os.path.dirname(__file__), "../../../.run/reports")


def _report_md_path(report_id: str) -> str:
    os.makedirs(_REPORT_DIR, exist_ok=True)
    return os.path.join(_REPORT_DIR, f"{report_id}.md")


def _write_md(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _append_md(path: str, content: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def _read_md(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _pure_stock_code(stock: str) -> str:
    s = str(stock or "").strip()
    return s.split(".")[0] if "." in s else s


def _truncate_json(obj: Any, limit: int = 3500) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        text = str(obj)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


async def _collect_stock_facts(
    ctx: SkillInvocationContext,
    stock: str,
    stock_name: str,
    *,
    mode: str = "fundamental",
) -> dict[str, Any]:
    """统一采集事实底稿：factsheet（含新闻/情绪/股吧）+ web_search + 实时行情/K线。

    mode: fundamental | shortterm | vpa
    """
    from app.tool_center.skill_bridge import invoke_atomic_tool

    pure_code = _pure_stock_code(stock)
    name = (stock_name or "").strip() or pure_code

    # 共用：新闻 / 舆情；分模式再加深度检索
    common_queries = [
        f"{name} {pure_code} 最新新闻 重大事项 公告解读",
        f"{name} {pure_code} 股吧 雪球 投资者评论 情绪",
    ]
    if mode in ("shortterm", "vpa"):
        search_queries = common_queries + [
            f"{name} {pure_code} 日K线 走势 成交量 换手率 量比 异动",
            f"{name} {pure_code} 资金流向 主力净流入 北向 融资融券",
            f"{name} {pure_code} 技术分析 均线 MACD KDJ RSI",
        ]
        keywords = ["资金", "换手", "涨停", "跌停", "成交量", "均线", "订单"]
    else:
        search_queries = common_queries + [
            f"{name} {pure_code} 行业地位 市场份额 竞争对手",
            f"{name} {pure_code} 定增 并购 股权激励 资本运作",
            f"{name} {pure_code} 诉讼 处罚 减持 风险 警示",
            f"{name} {pure_code} 新产品 中标 订单 业务进展 2025 2026",
        ]
        keywords = ["订单", "产能", "毛利率", "市场份额", "行业", "风险"]

    search_results = await asyncio.gather(*[
        invoke_atomic_tool(
            ctx,
            tool_id="web_search",
            params={"query": q, "max_items": 5},
            skill_id="web_search",
        )
        for q in search_queries
    ], return_exceptions=True)

    search_parts: list[str] = []
    for q, sr in zip(search_queries, search_results):
        if isinstance(sr, Exception):
            continue
        if sr and sr.ok and sr.summary:
            search_parts.append(f"### 补充搜索：{q[:48]}\n\n{sr.summary[:1800]}")
    web_extra = "\n\n".join(search_parts)

    # 全模式都拉实时行情；短线/量价再附 K 线近端样本
    market_chunks: list[str] = []
    try:
        quote_res = await invoke_atomic_tool(
            ctx,
            tool_id="stock_quote",
            params={"codes": pure_code},
            skill_id="stock_quote",
        )
        if quote_res and quote_res.ok:
            payload = quote_res.data if isinstance(quote_res.data, dict) else {}
            market_chunks.append(
                "### 实时行情（stock_quote / 腾讯）\n\n"
                f"{quote_res.summary}\n\n"
                f"```json\n{_truncate_json(payload.get('quotes') or payload)}\n```"
            )
        else:
            market_chunks.append("### 实时行情（stock_quote）\n\n本次未获取到有效行情数据。")
    except Exception as exc:
        logger.warning("_collect_stock_facts quote failed: %s", exc)
        market_chunks.append("### 实时行情（stock_quote）\n\n本次未获取到有效行情数据。")

    if mode in ("shortterm", "vpa"):
        try:
            kline_res = await invoke_atomic_tool(
                ctx,
                tool_id="stock_kline",
                params={"code": pure_code, "ktype": "day"},
                skill_id="stock_kline",
            )
            if kline_res and kline_res.ok:
                payload = kline_res.data if isinstance(kline_res.data, dict) else {}
                kline = payload.get("kline") or []
                if isinstance(kline, list) and len(kline) > 40:
                    kline = kline[-40:]
                market_chunks.append(
                    "### 日 K 线（stock_kline，近端样本）\n\n"
                    f"{kline_res.summary}\n\n"
                    f"```json\n{_truncate_json(kline)}\n```"
                )
            else:
                market_chunks.append("### 日 K 线（stock_kline）\n\n本次未获取到有效 K 线数据。")
        except Exception as exc:
            logger.warning("_collect_stock_facts kline failed: %s", exc)
            market_chunks.append("### 日 K 线（stock_kline）\n\n本次未获取到有效 K 线数据。")

    market_extra = "\n\n".join(market_chunks)

    structured_facts = ""
    resolved_name = name
    try:
        from app.services.finance_factsheet import build_roundtable_fact_sheet

        combined_web = web_extra
        if market_extra:
            combined_web = (web_extra + "\n\n" + market_extra).strip() if web_extra else market_extra

        fact_bundle = await build_roundtable_fact_sheet(
            pure_code,
            name,
            web_extra=combined_web,
            keywords=keywords,
        )
        structured_facts = str(fact_bundle.get("fact_sheet_md") or "")
        cn = str(fact_bundle.get("stock_name") or "").strip()
        if cn:
            resolved_name = cn
    except Exception as exc:
        logger.warning("_collect_stock_facts factsheet failed: %s", exc)

    if not structured_facts or len(structured_facts) < 80:
        fallback_parts = [p for p in (web_extra, market_extra) if p]
        structured_facts = "\n\n".join(fallback_parts) or "（本次未获取到有效事实数据）"

    return {
        "pure_code": pure_code,
        "stock_name": resolved_name,
        "fact_sheet_md": structured_facts,
        "web_extra": web_extra,
        "market_extra": market_extra,
    }


def _fill_placeholders(
    md_path: str,
    *,
    brief: str = "",
    summary: str = "",
) -> None:
    """回填「先看结论」与「3 分钟摘要」占位块。"""
    current = _read_md(md_path)
    if brief and "<!--CONCLUSION_START-->" in current and "<!--CONCLUSION_END-->" in current:
        current = re.sub(
            r"<!--CONCLUSION_START-->.*?<!--CONCLUSION_END-->",
            f"## 先看结论\n\n{brief}\n\n",
            current,
            count=1,
            flags=re.DOTALL,
        )
    elif brief and "## 先看结论" not in current:
        current = f"## 先看结论\n\n{brief}\n\n---\n\n" + current

    if summary and "<!--SUMMARY_START-->" in current and "<!--SUMMARY_END-->" in current:
        current = re.sub(
            r"<!--SUMMARY_START-->.*?<!--SUMMARY_END-->",
            f"## 3 分钟摘要\n\n{summary}\n\n",
            current,
            count=1,
            flags=re.DOTALL,
        )
    elif summary and "## 3 分钟摘要" not in current:
        insert = f"## 3 分钟摘要\n\n{summary}\n\n"
        marker = "## 研究问题（由交易式问题改写）"
        if marker in current:
            current = current.replace(marker, insert + marker, 1)
        else:
            current = insert + current
    _write_md(md_path, current)


async def handle_web_search(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    from app.tool_center.skill_bridge import invoke_atomic_tool

    query = str(params.get("query") or "").strip()
    if not query:
        return SkillInvocationResult(False, "缺少 query", error="missing_query")
    return await invoke_atomic_tool(
        ctx,
        tool_id="web_search",
        params=params,
        skill_id="web_search",
        success_summary=f"联网检索「{query[:40]}」完成",
    )


async def handle_knowledge_retrieve(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    from app.tool_center.skill_bridge import invoke_atomic_tool

    query = str(params.get("query") or "").strip()
    if not query:
        return SkillInvocationResult(False, "缺少 query", error="missing_query")
    merged = dict(params)
    doc_ids = _resolve_doc_ids(ctx, params)
    if doc_ids:
        merged["doc_ids"] = [str(x) for x in doc_ids]
    elif not params.get("doc_ids"):
        return SkillInvocationResult(
            False,
            "未指定 doc_ids，且用户权限内暂无可检索文档",
            error="no_documents",
        )
    return await invoke_atomic_tool(
        ctx,
        tool_id="knowledge_retrieve",
        params=merged,
        skill_id="knowledge_retrieve",
        success_summary=f"知识库检索「{query[:40]}」完成",
    )


async def handle_kg_query(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    from app.tool_center.skill_bridge import invoke_atomic_tool

    question = str(params.get("question") or params.get("query") or "").strip()
    if not question:
        return SkillInvocationResult(False, "缺少 question", error="missing_question")
    return await invoke_atomic_tool(
        ctx,
        tool_id="kg_query",
        params={"question": question},
        skill_id="kg",
    )


async def handle_deep_research(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """深度研究：委托子 Agent 执行多轮联网检索与交叉验证，返回含引用链接的研究报告。"""
    task = str(params.get("task") or params.get("query") or "").strip()
    if not task:
        return SkillInvocationResult(False, "缺少研究课题", error="missing_task")

    from app.core.agent.subagent import execute_context_subagent

    loop_state = ctx.loop_state or {}
    result_json = await execute_context_subagent(
        db=ctx.db,
        user=ctx.user,
        kind="search",
        task=task,
        conversation_id=ctx.conversation_id,
        attachment_session_id=ctx.attachment_session_id,
        loop_state=loop_state,
    )
    try:
        payload = json.loads(result_json)
    except json.JSONDecodeError:
        payload = {}

    ok = payload.get("ok", False)
    summary = str(payload.get("summary") or "")
    full_result = (payload.get("data") or {}).get("result") or ""

    # 从完整报告文本中提取引用链接
    citations = _extract_deep_research_citations(full_result)
    return SkillInvocationResult(
        ok=ok,
        summary=summary[:200] if ok else f"深度研究失败：{summary[:200]}",
        data={"summary": summary, "citations": citations},
    )


_DE_CITATION_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)')


def _extract_deep_research_citations(text: str) -> list[dict]:
    """从 deep_research 报告文本中提取 markdown 链接作为结构化引用。"""
    seen: set[str] = set()
    citations: list[dict] = []
    for match in _DE_CITATION_RE.finditer(text):
        title = match.group(1).strip()
        url = match.group(2).strip().rstrip(".,;")
        if url not in seen and not url.endswith((".png", ".jpg", ".gif", ".svg")):
            seen.add(url)
            citations.append({
                "index": len(citations) + 1,
                "title": title or url,
                "url": url,
                "source": "web",
            })
    return citations


async def handle_stub_feature(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
    *,
    feature_title: str = "平台功能",
    route: str = "",
    hint: str = "",
) -> SkillInvocationResult:
    """占位 handler：返回功能说明与后续接入提示。"""
    _ = ctx
    msg = f"「{feature_title}」Skill 已注册，智能体循环接入中。"
    if route:
        msg += f" 用户也可在 {route} 使用完整界面。"
    if hint:
        msg += f" {hint}"
    return SkillInvocationResult(
        True,
        msg,
        data={"status": "stub", "params_received": params, "route": route or None},
    )


def make_stub_handler(
    *, feature_title: str, route: str, hint: str = ""
) -> SkillHandler:
    async def _handler(
        ctx: SkillInvocationContext, params: dict[str, Any]
    ) -> SkillInvocationResult:
        return await handle_stub_feature(
            ctx, params, feature_title=feature_title, route=route, hint=hint
        )

    return _handler


def _resolve_doc_ids(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> list[uuid.UUID]:
    from app.services.skill_guard import filter_doc_ids_for_user

    raw = params.get("doc_ids")
    if isinstance(raw, list) and raw:
        parsed: list[uuid.UUID] = []
        for item in raw:
            try:
                parsed.append(uuid.UUID(str(item)))
            except ValueError:
                continue
        if parsed:
            return filter_doc_ids_for_user(ctx.db, ctx.user, parsed)
    if ctx.doc_ids:
        return filter_doc_ids_for_user(ctx.db, ctx.user, list(ctx.doc_ids))
    return _default_searchable_doc_ids(ctx)


async def handle_free_web_ai_chat(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
) -> SkillInvocationResult:
    """免费网页 AI 文本对话。"""
    prompt = str(params.get("prompt") or params.get("query") or "").strip()
    if not prompt:
        return SkillInvocationResult(False, "缺少 prompt", error="missing_prompt")
    provider = str(params.get("provider") or "").strip() or None
    new_conv = bool(params.get("new_conversation", False))
    try:
        from app.integrations.free_web_ai import get_free_web_ai_manager
        from app.integrations.free_web_ai.config import get_free_web_ai_config

        cfg = get_free_web_ai_config()
        if not cfg.enabled:
            return SkillInvocationResult(
                False, "免费网页 AI 功能未启用，请配置 FREE_WEB_AI_ENABLED=true",
                error="disabled",
            )
        mgr = get_free_web_ai_manager()
        result = await mgr.chat(prompt, provider=provider, new_conversation=new_conv)
        if result.get("success"):
            return SkillInvocationResult(
                True,
                f"AI 回复（{result.get('provider', '?')}）",
                data={"response": result.get("response", ""), "provider": result.get("provider")},
            )
        return SkillInvocationResult(
            False,
            f"AI 回复失败: {result.get('reason', 'unknown')}",
            error=result.get("reason", "unknown"),
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"免费网页 AI 调用异常: {exc}", error=str(exc))


async def handle_free_web_ai_image_gen(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
) -> SkillInvocationResult:
    """免费网页 AI 文字生图。"""
    prompt = str(params.get("prompt") or params.get("query") or "").strip()
    if not prompt:
        return SkillInvocationResult(False, "缺少生图描述", error="missing_prompt")
    provider = str(params.get("provider") or "").strip() or None
    new_conv = bool(params.get("new_conversation", False))
    try:
        from app.integrations.free_web_ai import get_free_web_ai_manager
        from app.integrations.free_web_ai.config import get_free_web_ai_config

        cfg = get_free_web_ai_config()
        if not cfg.enabled:
            return SkillInvocationResult(False, "免费网页 AI 功能未启用", error="disabled")
        mgr = get_free_web_ai_manager()
        result = await mgr.generate_image(prompt, provider=provider, new_conversation=new_conv)
        if result.get("success"):
            return SkillInvocationResult(
                True,
                f"图片已生成（{result.get('provider', '?')}）",
                data={"response": result.get("response", ""), "provider": result.get("provider")},
            )
        return SkillInvocationResult(
            False, f"生图失败: {result.get('reason', 'unknown')}",
            error=result.get("reason", "unknown"),
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"生图异常: {exc}", error=str(exc))


async def handle_free_web_ai_image_ask(
    ctx: SkillInvocationContext,
    params: dict[str, Any],
) -> SkillInvocationResult:
    """免费网页 AI 识图问答。"""
    question = str(params.get("question") or params.get("query") or "").strip()
    if not question:
        return SkillInvocationResult(False, "缺少问题", error="missing_question")
    image_path = str(params.get("image_path") or "").strip()
    if not image_path:
        return SkillInvocationResult(False, "缺少图片路径", error="missing_image_path")
    provider = str(params.get("provider") or "").strip() or None
    new_conv = bool(params.get("new_conversation", False))
    try:
        from app.integrations.free_web_ai import get_free_web_ai_manager
        from app.integrations.free_web_ai.config import get_free_web_ai_config

        cfg = get_free_web_ai_config()
        if not cfg.enabled:
            return SkillInvocationResult(False, "免费网页 AI 功能未启用", error="disabled")
        mgr = get_free_web_ai_manager()
        result = await mgr.ask_with_image(question, image_path, provider=provider, new_conversation=new_conv)
        if result.get("success"):
            return SkillInvocationResult(
                True,
                f"识图回复（{result.get('provider', '?')}）",
                data={"response": result.get("response", ""), "provider": result.get("provider")},
            )
        return SkillInvocationResult(
            False, f"识图问答失败: {result.get('reason', 'unknown')}",
            error=result.get("reason", "unknown"),
        )
    except Exception as exc:
        return SkillInvocationResult(False, f"识图问答异常: {exc}", error=str(exc))


def _default_searchable_doc_ids(ctx: SkillInvocationContext) -> list[uuid.UUID]:
    """无显式 doc_ids 时，取用户权限内少量已索引/有文件的文档。"""
    try:
        from sqlalchemy import select

        from app.core.permissions import PermissionLevel, can_access_document
        from app.models.document import Document
        from app.services.compare_service import _document_retrieval_ready
        from app.services.document_index_service import (
            enrich_document_index_meta,
            is_index_ready_meta,
        )

        rows = ctx.db.scalars(
            select(Document.id)
            .where(Document.deleted_at.is_(None))
            .order_by(Document.updated_at.desc())
            .limit(50)
        ).all()
        candidates: list[Document] = []
        for doc_id in rows:
            doc = ctx.db.get(Document, doc_id)
            if doc and can_access_document(
                ctx.db, ctx.user, doc, PermissionLevel.query.value
            ):
                candidates.append(doc)
        if not candidates:
            return []
        meta_by_doc = enrich_document_index_meta(
            ctx.db, ctx.user, candidates, live_ragflow=False
        )
        index_ready_ids = {
            did for did, meta in meta_by_doc.items() if is_index_ready_meta(meta)
        }
        out: list[uuid.UUID] = []
        for doc in candidates:
            if _document_retrieval_ready(
                ctx.db,
                doc,
                index_ready_ids=index_ready_ids,
                allow_index_only=True,
            ):
                out.append(doc.id)
            if len(out) >= 10:
                break
        return out
    except Exception:
        return []


_CARBON_NEWS_KW = (
    "新闻", "资讯", "日报", "快讯", "头条", "动态", "解读",
    "今日要闻", "每日碳", "碳引擎", "碳道",
)
_CARBON_PRICE_KW = (
    "碳价", "成交价", "收盘价", "开盘价", "成交量", "成交额",
    "cea", "挂牌协议", "配额价格", "行情",
)
_CARBON_POLICY_KW = (
    "政策", "法规", "条例", "办法", "通知", "意见", "方案", "规划",
    "印发", "1+n", "顶层设计", "碳市场条例",
)
_CARBON_CCER_KW = ("ccer", "自愿减排", "方法学", "签发", "备案")
_CARBON_INTL_KW = ("欧盟", "eu ets", "eua", "article 6", "自愿碳市场", "国际碳")
_CARBON_LOCAL_KW = ("地方", "省市", "省级", "碳达峰方案", "零碳录")
_CARBON_EMISSION_KW = ("排放", "核算", "排放因子", "温室气体", "碳足迹", "mrv")


def _classify_carbon_question(question: str) -> str:
    """返回 news | price | policy | emission | ccer | international | local | general。"""
    q = (question or "").strip().lower()
    if not q:
        return "general"
    if any(kw in q for kw in _CARBON_NEWS_KW):
        return "news"
    if any(kw in q for kw in _CARBON_PRICE_KW):
        return "price"
    if any(kw in q for kw in _CARBON_POLICY_KW):
        return "policy"
    if any(kw in q for kw in _CARBON_CCER_KW):
        return "ccer"
    if any(kw in q for kw in _CARBON_INTL_KW):
        return "international"
    if any(kw in q for kw in _CARBON_LOCAL_KW):
        return "local"
    if any(kw in q for kw in _CARBON_EMISSION_KW):
        return "emission"
    return "general"


async def handle_carbon_qa_ask(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """双碳问答：官方源原子工具取数；新闻类返回浏览器执行指引。"""
    question = str(
        params.get("question") or params.get("query") or params.get("ask") or ""
    ).strip()
    if not question:
        return SkillInvocationResult(False, "缺少 question", error="missing_question")

    progress = ctx.progress_callback
    kind = _classify_carbon_question(question)

    if kind == "news":
        from app.services.carbon_service import news_browser_task_hint

        task = news_browser_task_hint(question)
        summary = (
            "## 新闻资讯需浏览器查最新\n\n"
            "碳新闻/资讯有强时效性，请父层或调度层执行：\n\n"
            f"`invoke_context_subagent(kind=execute, task=\"{task}\")`\n\n"
            "推荐站点：cenews.com.cn、tandao.org、3060.org.cn。"
            "拿到浏览器真实结果后再回复用户，禁止编造新闻条目。"
        )
        return SkillInvocationResult(
            ok=True,
            summary=summary,
            data={
                "kind": "news",
                "needs_browser": True,
                "execute_task": task,
                "question": question,
            },
        )

    from app.tool_center.skill_bridge import invoke_atomic_tool

    if progress:
        progress(15, "正在从官方源获取双碳数据...")

    tool_calls: list[tuple[str, dict[str, Any]]] = []
    if kind == "price":
        tool_calls.append(("carbon_price", {"keyword": question[:80]}))
    elif kind == "policy":
        tool_calls.append(("carbon_policy", {"keyword": question[:80]}))
    elif kind in ("emission", "ccer", "international", "local"):
        tool_calls.append(("carbon_data", {"topic": kind, "keyword": question[:80]}))
    else:
        # 综合问答：并行拉碳价 + 政策，必要时再补排放
        tool_calls.extend([
            ("carbon_price", {"keyword": question[:80]}),
            ("carbon_policy", {"keyword": question[:80]}),
        ])

    results = await asyncio.gather(*[
        invoke_atomic_tool(ctx, tool_id=tid, params=p, skill_id=tid)
        for tid, p in tool_calls
    ], return_exceptions=True)

    parts: list[str] = [f"## 双碳问答事实底稿\n\n**问题**：{question}\n"]
    any_ok = False
    for (tid, _), res in zip(tool_calls, results):
        if isinstance(res, Exception):
            parts.append(f"### {tid}\n\n调用失败：{res}")
            continue
        if res and res.ok:
            any_ok = True
            payload = res.data if isinstance(res.data, dict) else {}
            md = str(payload.get("summary_md") or res.summary or "")[:6000]
            parts.append(f"### {tid}\n\n{md}")
        else:
            err = (res.summary if res else "无结果") or "无结果"
            parts.append(f"### {tid}\n\n本次未获取到有效数据：{err[:500]}")

    parts.append(
        "\n---\n\n**约束**：以上内容仅来自本次工具返回；缺口标注「本次未获取到」，"
        "禁止编造碳价或政策条文。若需最新新闻资讯，请用 "
        "`invoke_context_subagent(kind=execute)` 浏览器查询。"
    )
    summary = "\n\n".join(parts)
    if progress:
        progress(90, "双碳数据汇总完成")

    return SkillInvocationResult(
        ok=any_ok or kind == "general",
        summary=summary,
        data={"kind": kind, "question": question, "tools": [t for t, _ in tool_calls]},
        error=None if any_ok else ("all_tools_failed" if kind != "general" else None),
    )


async def handle_stock_deep_analysis(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """AI 深度解读：结构化事实底稿 + 固定章节深度报告。"""
    stock = str(params.get("stock") or params.get("query") or "").strip()
    if not stock:
        return SkillInvocationResult(False, "缺少股票代码或名称", error="missing_stock")
    dimensions = str(params.get("dimensions") or "财务,估值,行业,成长,风险").strip()
    ai_context = str(params.get("ai_context") or "").strip()
    progress = ctx.progress_callback

    from datetime import datetime

    from app.integrations.deepseek_client import chat_completion_message_async

    stock_name = str(params.get("stock_name") or "").strip() or _pure_stock_code(stock)

    if progress:
        progress(10, "正在采集事实底稿...")
    facts_bundle = await _collect_stock_facts(
        ctx, stock, stock_name, mode="fundamental",
    )
    stock_name = str(facts_bundle.get("stock_name") or stock_name)
    facts = str(facts_bundle.get("fact_sheet_md") or "")

    if progress:
        progress(45, "撰写深度解读...")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context_note = f"\n## 用户补充上下文\n\n{ai_context}\n" if ai_context else ""
    system_prompt = (
        f"你是专业股票分析师，正在对 {stock_name}（{stock}）出具「AI 深度解读」。\n"
        f"关注维度：{dimensions}\n\n"
        "必须按以下 Markdown 标题完整输出（标题不可改名、不可省略）：\n\n"
        f"# 「{stock_name} ({stock})」AI 深度解读\n\n"
        f"生成完成 · {now_str}\n\n"
        "> **声明**：本报告为研究性质的深度基本面分析，**不构成任何投资建议**，"
        "不提供买入/卖出/持有指令、目标价、止盈止损位或收益承诺。"
        "全部讨论仅基于本次事实底稿；底稿未覆盖的内容一律标注「本次未获取到」。\n\n"
        "## 先看结论\n"
        "（一段一句话结论 + 价值线索/风险压力/跟踪优先级三条要点）\n\n"
        "## 一、公司概览\n"
        "（表格：公司全称/上市板块/商业模式/核心产品线/行业地位 + 商业模式解读）\n\n"
        "## 二、财务分析\n"
        "### 营收与利润趋势\n### 利润率分析\n### 现金流质量\n**财务健康度评估**\n\n"
        "## 三、估值分析\n"
        "（PE/PB/PS 等表格 + **估值结论**）\n\n"
        "## 四、行业格局\n\n"
        "## 五、成长驱动\n\n"
        "## 六、风险提示\n"
        "（编号列表，≥4 条）\n\n"
        "## 七、验证清单\n"
        "（≥5 条，附核验去向）\n\n"
        "## 八、研究边界\n"
        "（基于/不基于哪些数据 + 不构成投资建议声明）\n\n"
        "硬约束：禁止编造底稿没有的数字；缺口写「本次未获取到」；"
        "关键数字尽量引用事实底稿中的原表述。"
    )
    choice = await chat_completion_message_async(
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"## 事实底稿\n\n{facts[:12000]}\n{context_note}\n"
                    "请基于以上底稿出具完整深度解读报告。"
                ),
            },
        ],
        temperature=0.45,
        timeout=240,
    )
    report = ""
    if choice:
        report = str((choice.get("message") or {}).get("content") or "").strip()
    if not report:
        report = (
            f"# 「{stock_name} ({stock})」AI 深度解读\n\n"
            f"生成完成 · {now_str}\n\n"
            "## 先看结论\n\n本次未能生成分析正文。\n\n"
            "## 事实底稿摘要\n\n"
            f"{facts[:8000]}"
        )

    if progress:
        progress(95, "分析完成")
    logger.warning("handle_stock_deep_analysis: report_len=%s", len(report))
    return SkillInvocationResult(
        ok=bool(report.strip()),
        summary=report,
        data={"stock": stock, "dimensions": dimensions},
    )


async def handle_stock_roundtable_debate_fundamental(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """辩论圆桌·基本面：多角色对抗性辩论，聚焦财务/估值/行业格局。"""
    return await _execute_roundtable(
        ctx, params,
        roundtable_type="debate",
        direction="fundamental",
        focus_desc="基本面（财务/估值/行业格局）",
    )


async def handle_stock_roundtable_debate_shortterm(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """辩论圆桌·短线：多角色对抗性辩论，聚焦量价/资金/情绪。"""
    return await _execute_roundtable(
        ctx, params,
        roundtable_type="debate",
        direction="shortterm",
        focus_desc="短线（量价/资金/情绪）",
    )


async def handle_stock_roundtable_research_fundamental(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """专业研究·基本面：4 位研究角色协作，系统性基本面分析。"""
    return await _execute_roundtable(
        ctx, params,
        roundtable_type="research",
        direction="fundamental",
        focus_desc="基本面（财务/估值/行业格局）",
    )


async def handle_stock_roundtable_research_shortterm(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """专业研究·短线：4 位研究角色协作，短线技术面分析。"""
    return await _execute_roundtable(
        ctx, params,
        roundtable_type="research",
        direction="shortterm",
        focus_desc="短线（量价/资金/情绪）",
    )


# ── 圆桌模板：参与者表 ─────────────────────────────────────

def _roundtable_participants_table(
    roundtable_type: str, direction: str, focus_desc: str,
) -> str:
    """返回圆桌/研究参与者介绍（写入 .md 文件）。"""
    if roundtable_type == "debate" and direction == "shortterm":
        return (
            "## 圆桌参与者\n\n"
            "本场共 8 人上桌：4 位研究打底角色 + 3 位投资框架角色 + 1 位临时摇来的短线技术专家。"
            "仅列本次实际参会者。\n\n"
            "| 角色 | 观察镜头 | 执念（本场追打的问题） |\n"
            "|---|---|---|\n"
            "| **主持人（短线结构裁判）** | 拆解反弹/反转、量价与资金是否同向 | 底稿能把短线结构判断推进到哪一步 |\n"
            "| **平台信号研究员** | 断层信号、异动、业绩预告窗口 | 旧信号/公告窗口是否解释现价 |\n"
            "| **量价结构研究员** | K 线、成交量、放量/缩量关键位置 | 当前是修复结构还是趋势破坏 |\n"
            "| **资金面研究员** | 主力净流入、换手、北向/融资 | 资金在印证还是背离价格 |\n"
            "| **风险反方** | 假突破、流动性陷阱、情绪拥挤 | 短线逻辑最先断在哪一环 |\n"
            "| **霍华德·马克斯（虚构化角色）** | 赔率、情绪位置、风险补偿 | 短线赔率是否被价格补偿 |\n"
            "| **索罗斯（虚构化角色）** | 反身性、趋势拥挤、叙事强化 | 是价格推叙事还是基本面推价格 |\n"
            "| **段永平（虚构化角色）** | 常识、可理解性、不碰看不清的东西 | 这波波动能否用大白话讲清楚 |\n"
            "| **短线技术专家（临时摇入，专业视角模拟）** | 均线/MACD/关键位、缺口与量能 | 技术信号可靠性边界在哪里 |\n\n"
            "> 声明：霍华德·马克斯、索罗斯、段永平等均为虚构化圆桌角色；短线技术专家为专业视角模拟。\n\n"
            "---\n\n"
        )
    if roundtable_type == "debate":
        expert_lens = focus_desc or "行业周期、需求与订单节奏、产品迭代"
        return (
            "## 圆桌参与者\n\n"
            "本场共 8 人上桌：4 位研究打底角色 + 3 位投资框架角色 + 1 位临时摇来的领域专家。仅列本次实际参会者。\n\n"
            "| 角色 | 观察镜头 | 执念（本场追打的问题） |\n"
            "|---|---|---|\n"
            "| **主持人（周期位置裁判）** | 把叙事拆成周期变量，区分公司 alpha 与行业 beta，逐轮收束核心矛盾 | 本次底稿能把周期判断推进到哪一步，哪些是公司因素、哪些是行业因素、哪些无法判断 |\n"
            "| **平台信号研究员** | 平台断层信号、资金流方向、业绩预告 | 一条已经走弱的历史信号能否解释当前价格？资金面在印证还是背离？ |\n"
            "| **基本面研究员** | 主营构成、财务趋势、分部毛利率、ROE 回升 | 增长里公司自身可区分的 alpha 到底是什么？ |\n"
            "| **市场定价研究员** | PE/PB/PS、市值、近期涨跌、换手、股东户数 | 周期股的静态估值是否在误导——业绩好时 PE 低反而危险？ |\n"
            "| **风险反方** | 利润质量、经营现金流季节性、非经常损益、客户集中度 | 如果这套逻辑失败，最先断在哪个环节？ |\n"
            "| **霍华德·马克斯（虚构化角色）** | 周期位置、赔率、风险是否被价格补偿 | 在看不清周期位置时，价格给的补偿够不够？ |\n"
            "| **邱国鹭（虚构化角色）** | 便宜好公司、竞争格局、A 股定价错配、均值回归 | 这是价值回归，还是价值陷阱？ |\n"
            "| **段永平（虚构化角色）** | 商业模式、现金流、常识、能力圈 | 不用行业黑话，能不能讲清楚这家公司靠什么反复赚钱？ |\n"
            f"| **行业领域专家（临时摇入，专业视角模拟）** | {expert_lens} | 哪些是真需求驱动、哪些依赖外部投资节奏，且底稿证据到不到位？ |\n\n"
            "> 声明：霍华德·马克斯、邱国鹭、段永平等均为虚构化圆桌角色，仅借用其公开投资框架中的典型视角，不代表本人真实发言；领域专家为专业视角模拟。\n\n"
            "---\n\n"
        )
    if direction == "shortterm":
        return (
            "## 研究参与者\n\n"
            "本场共 4 位研究角色协作输出（无虚构投资者）。\n\n"
            "| 角色 | 分析重点 |\n"
            "|---|---|\n"
            "| **技术分析师** | 量价结构、K 线形态、技术指标信号 |\n"
            "| **资金分析师** | 资金流向、成交结构、筹码/换手 |\n"
            "| **情绪分析师** | 波动率、多空分歧、异常交易行为 |\n"
            "| **风险分析师** | 短线脆弱环节、关键价位、风险边界 |\n\n"
            "---\n\n"
        )
    return (
        "## 研究参与者\n\n"
        "本场共 4 位研究角色协作输出（无虚构投资者）。\n\n"
        "| 角色 | 分析重点 |\n"
        "|---|---|\n"
        "| **行业分析师** | 行业格局、竞争壁垒、产业链位置 |\n"
        "| **财务分析师** | 财报拆解、利润率趋势、现金流质量、ROE 归因 |\n"
        "| **估值分析师** | 估值倍数历史分位、可比公司对比 |\n"
        "| **风险分析师** | 经营风险、周期风险、治理风险、关键假设 |\n\n"
        "---\n\n"
    )


# ── 辩论轮次定义（含 LLM prompt 构造器）────────────────────

def _debate_round_definitions(direction: str, focus_desc: str) -> list[dict]:
    """返回辩论圆桌各轮的 prompt_builder 定义。"""
    if direction == "shortterm":
        return [
            {"label": "第 1 轮辩论", "temperature": 0.7, "prompt_builder": _st_round1_prompt},
            {"label": "第 2 轮辩论", "temperature": 0.7, "prompt_builder": _st_round2_prompt},
            {"label": "第 3 轮辩论", "temperature": 0.7, "prompt_builder": _st_round3_prompt},
            {"label": "第 4 轮辩论", "temperature": 0.7, "prompt_builder": _st_round4_prompt},
        ]
    return [
        {"label": "第 1 轮辩论", "temperature": 0.7, "prompt_builder": _round1_prompt},
        {"label": "第 2 轮辩论", "temperature": 0.7, "prompt_builder": _round2_prompt},
        {"label": "第 3 轮辩论", "temperature": 0.7, "prompt_builder": _round3_prompt},
        {"label": "第 4 轮辩论", "temperature": 0.7, "prompt_builder": _round4_prompt},
    ]


_RESEARCH_OUTPUT_CONTRACT = (
    "输出必须严格包含：\n"
    "1. 以指定的 `## …` 章节标题开头（不可改名）\n"
    "2. 关键数字引用事实底稿，缺口写「本次未获取到」\n"
    "3. 至少一张 Markdown 表格归纳要点\n"
    "4. 文末用 `### 本节移交` 列出交给下一环节的 2–3 个待验证问题\n"
    "禁止买卖指令、目标价、止盈止损。\n"
)


def _research_round_definitions(direction: str, focus_desc: str) -> list[dict]:
    """返回专业研究各轮的 prompt_builder 定义。"""
    if direction == "shortterm":
        return [
            {
                "label": "量价结构",
                "temperature": 0.45,
                "prompt_builder": _research_st_round1,
            },
            {
                "label": "资金面",
                "temperature": 0.45,
                "prompt_builder": _research_st_round2,
            },
            {
                "label": "情绪与指标",
                "temperature": 0.45,
                "prompt_builder": _research_st_round3,
            },
            {
                "label": "关键价位与风险",
                "temperature": 0.45,
                "prompt_builder": _research_st_round4,
            },
        ]
    return [
        {
            "label": "行业与定位",
            "temperature": 0.45,
            "prompt_builder": _research_fund_round1,
        },
        {
            "label": "财务深度拆解",
            "temperature": 0.45,
            "prompt_builder": _research_fund_round2,
        },
        {
            "label": "估值评估",
            "temperature": 0.45,
            "prompt_builder": _research_fund_round3,
        },
        {
            "label": "假设与风险",
            "temperature": 0.45,
            "prompt_builder": _research_fund_round4,
        },
    ]


# ── 每轮 prompt builder ─────────────────────────────────

_ROUND_OUTPUT_CONTRACT = (
    "输出必须严格包含以下 Markdown 结构（标题文字不可省略、不可改名）：\n"
    "1. 以 `## 第 N 轮｜{主题}` 开头\n"
    "2. 各角色发言：用 `**【角色名】开场定调/拆解/追问/拆台：**` 起段；每人必须含\n"
    "   * **追打** / * **证据** / * **点名反驳** / * **推翻条件** / * **证据边界**\n"
    "3. `### 三次互搏还原`：用引用块写满三场互搏，格式为\n"
    "   `> **互搏一**（A ↔ B）：… **主持人证据评级**：…证据硬度★…`\n"
    "4. `### 主持人裁决`：200–400 字收束本轮新增判断，并点明移交下一轮的问题\n"
    "5. `### 本轮框架：…`（第 4 轮可拆成「本轮框架一」「本轮框架二」）+ Markdown 表格\n"
    "禁止编造底稿没有的数字；缺口一律写「本次未获取到」。\n"
)


def _round1_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    """第 1 轮：基本观点陈述 — 各角色拆解周期变量暴露。"""
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的多角色对抗性辩论。\n"
        "当前轮次：第 1 轮 / 共 4 轮\n"
        "本轮主题：公司暴露在哪些周期变量上，底稿能支持到哪一步？\n\n"
        "请依次让以下角色发言：\n"
        "- **主持人**：开场定调，先把公司拆成周期变量地图\n"
        "- **基本面研究员**：拆解主营/分部的周期暴露\n"
        "- **行业领域专家**：追问外部投资/需求节奏是否有坐标\n"
        "- **风险反方**：剥离季节性与利润质量伪周期\n"
        "- **段永平**：用大白话追问商业本质与赚钱节奏\n\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "本轮框架表建议列：业务/产品、主要周期变量、底稿证据强度、暴露性质、错判风险。"
    )
    user = (
        f"## 事实底稿\n\n{facts}\n\n"
        f"## 前序内容\n\n{report[-2000:]}\n\n"
        "请开始第 1 轮辩论。标题必须是：## 第 1 轮｜公司暴露在哪些周期变量上，底稿能支持到哪一步？"
    )
    return system, user


def _round2_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    """第 2 轮：利润弹性 alpha/beta 拆分。"""
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的多角色对抗性辩论。\n"
        "当前轮次：第 2 轮 / 共 4 轮\n"
        "本轮主题：利润弹性来自公司 alpha 还是行业 beta？\n\n"
        "承接第 1 轮结论，本轮把「伪周期」噪声剥掉，逼到真问题。\n\n"
        "请依次让以下角色发言：\n"
        "- **主持人**：承接定调，要求看「同样的行业趋势下这家比同行多做对了什么」\n"
        "- **基本面研究员**：举证 alpha（可区分的公司因素）\n"
        "- **行业领域专家**：反驳——高毛利是行业结构特征还是公司能力\n"
        "- **风险反方**：拆台净利同比，质疑单季高增的质量\n"
        "- **霍华德·马克斯**：追问赔率——上得快是否下得也快\n\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "本轮框架表标题用：`### 本轮框架：利润弹性 alpha/beta 拆分表`。"
    )
    user = (
        f"## 全部辩论内容\n\n{report[-6000:]}\n\n"
        "请开始第 2 轮。标题必须是：## 第 2 轮｜利润弹性来自公司 alpha 还是行业 beta？"
    )
    return system, user


def _round3_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    """第 3 轮：估值是否已反映周期预期。"""
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的多角色对抗性辩论。\n"
        "当前轮次：第 3 轮 / 共 4 轮\n"
        "本轮主题：静态估值是否已反映周期高点或低点预期？\n\n"
        "承接前两轮利润拆解结论。\n\n"
        "请依次让以下角色发言：\n"
        "- **主持人**：承接定调——把利润账本换算成价格问题\n"
        "- **市场定价研究员**：立论——多口径估值读数与周期解释\n"
        "- **邱国鹭**：追问——这是价值回归还是价值陷阱\n"
        "- **风险反方**：拆台估值分母——利润不干净导致的失真便宜\n"
        "- **霍华德·马克斯**：裁断赔率——便宜不构成安全边际\n\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "本轮框架表标题用：`### 本轮框架：周期估值张力表`。"
    )
    user = (
        f"## 全部辩论内容\n\n{report[-6000:]}\n\n"
        "请开始第 3 轮。标题必须是：## 第 3 轮｜静态估值是否已反映周期高点或低点预期？"
    )
    return system, user


def _round4_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    """第 4 轮：错判断裂图与验证路径。"""
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的多角色对抗性辩论。\n"
        "当前轮次：第 4 轮 / 共 4 轮\n"
        "本轮主题：哪些外部数据决定周期判断能否推进，错判会从哪里断裂？\n\n"
        "前三轮做的是「拆」，本轮改为收口——把风险和缺口之间的因果链接起来。\n\n"
        "请依次让以下角色发言：\n"
        "- **主持人**：收口定调——排序标准只有一个：能不能把「暴露」升级为「位置」\n"
        "- **风险反方**：立断裂点——按伤害深度分档（致命/结构性/质量型）\n"
        "- **行业领域专家**：排数据优先级——什么数据能决定推进\n"
        "- **塞思·卡拉曼（虚构化角色）**：守下行边界——最坏情况亏多少\n"
        "- **平台信号研究员**：回收断层信号的账\n\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "本轮必须输出两张框架表：\n"
        "`### 本轮框架一：错判断裂图（按伤害深度分档）`\n"
        "`### 本轮框架二：资料缺口优先级与验证路径`"
    )
    user = (
        f"## 全部辩论内容\n\n{report[-8000:]}\n\n"
        "请开始第 4 轮。标题必须是：## 第 4 轮｜哪些外部数据决定周期判断能否推进，错判会从哪里断裂？"
    )
    return system, user


# ── 短线辩论轮次 ─────────────────────────────────────────

def _st_round1_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的短线多角色辩论。\n"
        "当前轮次：第 1 轮 / 共 4 轮\n"
        "本轮主题：当前走势是技术性反弹还是趋势反转？\n\n"
        "请依次让以下角色发言：\n"
        "- **主持人**：开场定调，禁止直接下买卖结论\n"
        "- **量价结构研究员**：拆解近期量价配合与关键位置\n"
        "- **短线技术专家**：追问均线/形态是否支持趋势定性\n"
        "- **风险反方**：拆台假突破与流动性陷阱\n"
        "- **段永平**：用大白话追问「这波波动讲得清吗」\n\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "本轮框架表标题：`### 本轮框架：反弹/反转判别表`。"
    )
    user = (
        f"## 事实底稿\n\n{facts}\n\n"
        f"## 前序内容\n\n{report[-2000:]}\n\n"
        "请开始第 1 轮。标题必须是：## 第 1 轮｜当前走势是技术性反弹还是趋势反转？"
    )
    return system, user


def _st_round2_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的短线多角色辩论。\n"
        "当前轮次：第 2 轮 / 共 4 轮\n"
        "本轮主题：资金面博弈——主力、散户情绪与筹码是否同向？\n\n"
        "请依次发言：主持人、资金面研究员、平台信号研究员、风险反方、索罗斯。\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "本轮框架表标题：`### 本轮框架：资金面印证/背离表`。"
    )
    user = (
        f"## 全部辩论内容\n\n{report[-6000:]}\n\n"
        "请开始第 2 轮。标题必须是：## 第 2 轮｜资金面博弈：主力、情绪与筹码是否同向？"
    )
    return system, user


def _st_round3_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的短线多角色辩论。\n"
        "当前轮次：第 3 轮 / 共 4 轮\n"
        "本轮主题：技术信号可靠性与短线赔率。\n\n"
        "请依次发言：主持人、短线技术专家、霍华德·马克斯、风险反方、资金面研究员。\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "本轮框架表标题：`### 本轮框架：技术信号与赔率表`。"
    )
    user = (
        f"## 全部辩论内容\n\n{report[-6000:]}\n\n"
        "请开始第 3 轮。标题必须是：## 第 3 轮｜技术信号可靠性与短线赔率？"
    )
    return system, user


def _st_round4_prompt(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的短线多角色辩论。\n"
        "当前轮次：第 4 轮 / 共 4 轮\n"
        "本轮主题：短线逻辑压力测试——缺口与断裂点。\n\n"
        "请依次发言：主持人、风险反方、短线技术专家、平台信号研究员、霍华德·马克斯。\n"
        f"{_ROUND_OUTPUT_CONTRACT}"
        "必须输出两张框架表：\n"
        "`### 本轮框架一：短线错判断裂图`\n"
        "`### 本轮框架二：短线资料缺口与验证路径`"
    )
    user = (
        f"## 全部辩论内容\n\n{report[-8000:]}\n\n"
        "请开始第 4 轮。标题必须是：## 第 4 轮｜短线逻辑压力测试：缺口与断裂点在哪里？"
    )
    return system, user


# ── 专业研究轮次 ─────────────────────────────────────────

def _research_fund_round1(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是行业分析师，正在对 {stock_name}（{stock}）进行专业研究·基本面。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "本章标题必须是：## 一、行业与竞争定位"
    )
    user = (
        f"## 事实底稿\n\n{facts[:5000]}\n\n"
        "请输出「一、行业与竞争定位」完整章节（行业空间、竞争格局、公司位势、护城河）。"
    )
    return system, user


def _research_fund_round2(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是财务分析师，正在对 {stock_name}（{stock}）进行专业研究·基本面。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "本章标题必须是：## 二、财务深度拆解"
    )
    user = (
        f"## 事实底稿\n\n{facts[:4000]}\n\n"
        f"## 前序章节\n\n{report[-4000:]}\n\n"
        "请输出「二、财务深度拆解」（营收驱动、毛利率归因、费用、现金流匹配、ROE）。"
    )
    return system, user


def _research_fund_round3(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是估值分析师，正在对 {stock_name}（{stock}）进行专业研究·基本面。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "本章标题必须是：## 三、估值评估"
    )
    user = (
        f"## 事实底稿\n\n{facts[:3000]}\n\n"
        f"## 前序章节\n\n{report[-5000:]}\n\n"
        "请输出「三、估值评估」（历史分位、可比、情景区间；禁止目标价）。"
    )
    return system, user


def _research_fund_round4(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是风险分析师，正在对 {stock_name}（{stock}）进行专业研究·基本面。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "必须输出两节：\n"
        "## 四、关键假设与验证项\n"
        "## 五、风险清单\n"
        "（风险清单用表格：风险 / 概率 / 潜在影响 / 跟踪方式）"
    )
    user = (
        f"## 事实底稿\n\n{facts[:3000]}\n\n"
        f"## 前序章节\n\n{report[-6000:]}\n\n"
        "请输出第四、五章完整内容。"
    )
    return system, user


def _research_st_round1(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是技术分析师，正在对 {stock_name}（{stock}）进行专业研究·短线。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "本章标题必须是：## 一、量价结构分析"
    )
    user = (
        f"## 事实底稿\n\n{facts[:5000]}\n\n"
        "请输出「一、量价结构分析」。"
    )
    return system, user


def _research_st_round2(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是资金分析师，正在对 {stock_name}（{stock}）进行专业研究·短线。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "本章标题必须是：## 二、资金面分析"
    )
    user = (
        f"## 事实底稿\n\n{facts[:4000]}\n\n"
        f"## 前序章节\n\n{report[-4000:]}\n\n"
        "请输出「二、资金面分析」。"
    )
    return system, user


def _research_st_round3(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是情绪/技术指标分析师，正在对 {stock_name}（{stock}）进行专业研究·短线。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "必须输出：\n"
        "## 三、情绪面分析\n"
        "## 四、技术指标信号\n"
        "（第四节用表格：指标 / 当前值或状态 / 信号 / 解读；缺数写本次未获取到）"
    )
    user = (
        f"## 事实底稿\n\n{facts[:4000]}\n\n"
        f"## 前序章节\n\n{report[-5000:]}\n\n"
        "请输出第三、四章。"
    )
    return system, user


def _research_st_round4(
    stock_name: str, stock: str, report: str, facts: str,
) -> tuple[str, str]:
    system = (
        f"你是风险分析师，正在对 {stock_name}（{stock}）进行专业研究·短线。\n"
        f"{_RESEARCH_OUTPUT_CONTRACT}"
        "本章标题必须是：## 五、关键价位与风险\n"
        "只给观察区间与风险边界，禁止买卖指令/目标价/止盈止损指令。"
    )
    user = (
        f"## 事实底稿\n\n{facts[:3000]}\n\n"
        f"## 前序章节\n\n{report[-6000:]}\n\n"
        "请输出「五、关键价位与风险」。"
    )
    return system, user


async def _execute_roundtable(
    ctx: SkillInvocationContext, params: dict[str, Any],
    *,
    roundtable_type: str,
    direction: str,
    focus_desc: str,
) -> SkillInvocationResult:
    """圆桌/研究的通用执行逻辑 — 渐进式写入 .md 文件，逐轮 LLM 推进。"""
    stock = str(params.get("stock") or params.get("query") or "").strip()
    if not stock:
        return SkillInvocationResult(False, "缺少股票代码或名称", error="missing_stock")
    rounds = int(params.get("rounds") or 4)
    loop_state = ctx.loop_state or {}
    progress = ctx.progress_callback
    report_id = str(uuid.uuid4().hex[:12])
    md_path = _report_md_path(report_id)

    from datetime import datetime

    from app.integrations.deepseek_client import chat_completion_message_async

    stock_name = str(params.get("stock_name") or "").strip()
    if not stock_name:
        stock_name = _pure_stock_code(stock)
    report_type_label = "辩论圆桌" if roundtable_type == "debate" else "专业研究"
    fact_mode = "shortterm" if direction == "shortterm" else "fundamental"

    # ═══════════════════════════════════════════════════════════
    # Phase 1–2: 统一采集事实底稿（数字不经 LLM 压缩）
    # ═══════════════════════════════════════════════════════════
    if progress:
        progress(8, "正在采集事实数据...")
    logger.warning(
        "_execute_roundtable[%s/%s] Phase1: collect_stock_facts stock=%s name=%s",
        roundtable_type, direction, stock, stock_name,
    )
    facts_bundle = await _collect_stock_facts(ctx, stock, stock_name, mode=fact_mode)
    stock_name = str(facts_bundle.get("stock_name") or stock_name)
    structured_facts = str(facts_bundle.get("fact_sheet_md") or "")

    if progress:
        progress(25, "事实底稿整理完成")

    # ── 写入初始报告骨架 ──
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    direction_label = "基本面" if direction == "fundamental" else "短线"
    edition = "辩论版" if roundtable_type == "debate" else "专业研究"
    header = (
        f"# 「{stock_name} ({stock})」{direction_label}圆桌 · {edition}\n\n"
        f"生成完成 · {now_str}\n\n"
        "---\n\n"
    )

    conclusion_placeholder = (
        "<!--CONCLUSION_START-->\n\n"
        "## 先看结论\n\n"
        "*（最终研究报告结论将在研究结束后生成）*\n\n"
        "<!--CONCLUSION_END-->\n\n---\n\n"
    )

    if roundtable_type == "debate":
        detail_header = (
            "## 详细研究过程\n\n"
            f"# 「{stock_name} ({stock})」股票圆桌研究\n\n"
            "> **声明**：本报告是研究解释，不是投资建议。全程不提供买入/卖出建议、目标价、买卖点、"
            "止盈止损或收益承诺。文中出现的圆桌角色均为**虚构化圆桌角色**，仅借用其公开投资框架中的典型视角，"
            "不代表本人真实发言；领域专家为专业视角模拟。所有判断只基于已注入的事实底稿，"
            "底稿未覆盖的内容一律标注「本次未获取到」，不做猜测补全。\n\n"
        )
        rq_extra = (
            "增长有多少来自公司 alpha、多少来自行业 beta？"
            if direction == "fundamental"
            else "当前是反弹还是反转？资金与价格是否同向？"
        )
    else:
        detail_header = (
            "## 详细研究过程\n\n"
            f"# 「{stock_name} ({stock})」专业研究报告\n\n"
            "> **声明**：本报告为研究团队协作的系统性分析，**不构成任何投资建议**，"
            "不提供买入/卖出建议、目标价、买卖点、止盈止损或收益承诺。"
            "无虚构投资者角色。所有判断只基于已注入的事实底稿，"
            "底稿未覆盖的内容一律标注「本次未获取到」。\n\n"
        )
        rq_extra = (
            "关键假设是否合理、估值分位说明什么？"
            if direction == "fundamental"
            else "量价/资金/情绪哪一层证据最硬、哪一层是缺口？"
        )

    summary_placeholder = (
        "<!--SUMMARY_START-->\n\n"
        "## 3 分钟摘要\n\n"
        "*（研究结束后生成）*\n\n"
        "<!--SUMMARY_END-->\n\n"
    )

    research_question = (
        "## 研究问题（由交易式问题改写）\n\n"
        f"> 用户原始问题：对 {stock_name}（{stock}）进行"
        f"{'辩论圆桌研究' if roundtable_type == 'debate' else '专业研究分析'}"
        f"（隐含意图为「这只票怎么样/能不能看」）。\n>\n"
        f"> **改写为研究问题**：{stock_name} 在 {focus_desc} 方向上，"
        f"当前事实底稿能支撑什么级别的判断？{rq_extra}"
        f"核心分歧在哪里？哪些关键变量本次无法定位，必须优先验证哪些数据才能推进研究？\n\n"
    )

    fact_section = (
        "## 事实底稿摘要\n\n"
        "以下资料状态**全文集中呈现一次**，后文各轮只引用「事实底稿摘要中的相应缺口」，不再重复铺表。\n\n"
        f"{structured_facts}\n\n---\n\n"
    )

    participant_section = _roundtable_participants_table(roundtable_type, direction, focus_desc)

    initial_content = (
        header
        + conclusion_placeholder
        + detail_header
        + summary_placeholder
        + research_question
        + fact_section
        + participant_section
    )
    _write_md(md_path, initial_content)

    if progress:
        progress(28, "开始逐轮研究..." if roundtable_type != "debate" else "开始逐轮辩论...")

    # ═══════════════════════════════════════════════════════════
    # Phase 3: 逐轮推进
    # ═══════════════════════════════════════════════════════════

    if roundtable_type == "debate":
        round_defs = _debate_round_definitions(direction, focus_desc)
    else:
        round_defs = _research_round_definitions(direction, focus_desc)
    actual_rounds = min(rounds, len(round_defs))

    base_pct = 30
    pct_per_round = 50 // max(actual_rounds, 1)

    for round_idx in range(actual_rounds):
        rd = round_defs[round_idx]
        pct = base_pct + round_idx * pct_per_round

        # 先通知进度
        round_label = rd.get("label", f"第 {round_idx + 1} 轮")
        if progress:
            progress(pct, f"{round_label}...")

        # 读取当前完整 .md 内容 + 事实底稿作为本轮上下文
        current_report = _read_md(md_path)
        fact_context = structured_facts[:4000]  # 事实底稿摘要

        # 构造本轮 LLM prompt
        system_prompt, user_prompt = rd["prompt_builder"](stock_name, stock, current_report, fact_context)

        choice = await chat_completion_message_async(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=rd.get("temperature", 0.7),
            timeout=240,
        )
        round_content = ""
        if choice:
            msg = choice.get("message") or {}
            round_content = str(msg.get("content") or "").strip()
        if round_content:
            _append_md(md_path, f"\n\n{round_content}\n\n")
        else:
            _append_md(md_path, f"\n\n（{round_label} 未能生成内容）\n\n")

        logger.warning("_execute_roundtable[%s/%s] Round %s done: content_len=%s",
                       roundtable_type, direction, round_idx + 1, len(round_content))

    # ═══════════════════════════════════════════════════════════
    # Phase 4: 收束（辩论版 / 专业研究版标题不同）
    # ═══════════════════════════════════════════════════════════
    if progress:
        progress(82, "研究收束中...")

    final_report = _read_md(md_path)

    if roundtable_type == "debate":
        synthesis_prompt = (
            f"你是辩论主持人，正在主持对 {stock_name}（{stock}）的{report_type_label}"
            f"（方向：{focus_desc}）。\n"
            "请基于以上全部辩论内容，出具最终研究报告总结。\n\n"
            "必须按以下标题完整输出（标题文字不可改名、不可省略任一节）：\n\n"
            "## 主持人收束：客观研究结论\n"
            "（一段总述，说明本桌不回答「能不能买」，只结算证据结构）\n\n"
            "### 证据加权\n"
            "（表格：证据 / 方向 / 硬度 / 说明）\n\n"
            "### 五条非平庸洞见\n"
            "（恰好 5 条）\n\n"
            "### 研究分层结论\n"
            "（A/B/C/D 四层 + 总定性）\n\n"
            "### 统一数据缺口台账\n"
            "### 验证清单\n"
            "（≥8 条）\n\n"
            "### 参考资料\n"
            "### 研究边界\n"
            "禁止编造数字；缺口写「本次未获取到」。"
        )
    else:
        synthesis_prompt = (
            f"你是研究主编，正在汇总对 {stock_name}（{stock}）的专业研究"
            f"（方向：{focus_desc}）。\n"
            "请基于以上全部章节，出具最终研究结论。\n\n"
            "必须按以下标题完整输出：\n\n"
            "## 研究结论\n"
            "（一段总述，不回答「能不能买」）\n\n"
            "### 核心判断\n"
            "### 证据加权\n"
            "（表格：证据 / 方向 / 硬度 / 说明）\n\n"
            "### 关键假设\n"
            "### 验证清单\n"
            "（≥6 条，附核验去向）\n\n"
            "### 参考资料\n"
            "### 研究边界\n"
            "禁止编造数字；缺口写「本次未获取到」；禁止买卖指令。"
        )

    choice = await chat_completion_message_async(
        messages=[
            {"role": "system", "content": synthesis_prompt},
            {
                "role": "user",
                "content": f"以下是全部研究内容：\n\n{final_report}\n\n请出具最终总结。",
            },
        ],
        temperature=0.5,
        timeout=240,
    )
    synthesis_text = ""
    if choice:
        synthesis_text = str((choice.get("message") or {}).get("content") or "").strip()
    if synthesis_text:
        _append_md(md_path, f"\n\n---\n\n{synthesis_text}\n")
        if progress:
            progress(90, "回填结论与摘要...")

        brief_choice = await chat_completion_message_async(
            messages=[{
                "role": "user",
                "content": (
                    f"请基于以下收束内容，为 {stock_name}（{stock}）写「先看结论」"
                    f"（Markdown，约 350-650 字）。\n\n"
                    "必须包含：\n"
                    "1. 一段一句话结论（不加标题）\n"
                    "2. 三条要点：价值线索 / 风险压力 / 跟踪优先级\n"
                    "3. 核心原因：证据强度、核心分歧、最大不确定性\n\n"
                    "禁止编造底稿没有的数字。\n\n"
                    f"{synthesis_text[:6000]}"
                ),
            }],
            temperature=0.4,
            timeout=120,
        )
        brief = ""
        if brief_choice:
            brief = str((brief_choice.get("message") or {}).get("content") or "").strip()

        summary_choice = await chat_completion_message_async(
            messages=[{
                "role": "user",
                "content": (
                    f"请基于以下收束，为 {stock_name}（{stock}）写「3 分钟摘要」"
                    "（Markdown 无序列表，5 条：一句话结论 / 证据强度 / 核心分歧 / "
                    "最大资料缺口 / 后续 3 个验证项）。禁止编造数字。\n\n"
                    f"{synthesis_text[:5000]}"
                ),
            }],
            temperature=0.35,
            timeout=90,
        )
        summary = ""
        if summary_choice:
            summary = str((summary_choice.get("message") or {}).get("content") or "").strip()

        _fill_placeholders(md_path, brief=brief, summary=summary)

    if progress:
        progress(95, "报告整理中...")

    full_report = _read_md(md_path)
    logger.warning("_execute_roundtable[%s/%s] done: full_report_len=%s",
                   roundtable_type, direction, len(full_report))

    return SkillInvocationResult(
        ok=bool(full_report.strip()),
        summary=full_report,
        data={"stock": stock, "roundtable_type": roundtable_type, "direction": direction, "rounds": rounds},
        error=None if full_report.strip() else "报告生成失败",
    )


async def handle_stock_volume_price(
    ctx: SkillInvocationContext, params: dict[str, Any]
) -> SkillInvocationResult:
    """量价会诊：结构化行情底稿 + 四层检查单。"""
    stock = str(params.get("stock") or params.get("query") or "").strip()
    if not stock:
        return SkillInvocationResult(False, "缺少股票代码或名称", error="missing_stock")
    aspects = str(params.get("aspects") or "indicators,patterns,trend,decision").strip()
    progress = ctx.progress_callback

    from datetime import datetime

    from app.integrations.deepseek_client import chat_completion_message_async

    stock_name = str(params.get("stock_name") or "").strip() or _pure_stock_code(stock)

    if progress:
        progress(10, "获取行情与事实底稿...")
    facts_bundle = await _collect_stock_facts(ctx, stock, stock_name, mode="vpa")
    stock_name = str(facts_bundle.get("stock_name") or stock_name)
    facts = str(facts_bundle.get("fact_sheet_md") or "")

    if progress:
        progress(45, "四层量价诊断中...")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_prompt = (
        f"你是技术分析专家，正在对 {stock_name}（{stock}）出具「量价会诊报告」。\n"
        f"关注层面：{aspects}\n\n"
        "必须按以下 Markdown 标题完整输出（不可改名、不可省略）：\n\n"
        f"# 「{stock_name} ({stock})」量价会诊报告\n\n"
        f"生成完成 · {now_str}\n\n"
        "> **声明**：本报告为技术面辅助诊断工具，**不构成任何投资建议**，"
        "不提供买入/卖出指令、目标价、止盈止损或收益承诺。"
        "仅基于量价指标推演，缺口标注「本次未获取到」。\n\n"
        "## 先看结论\n"
        "（一句话结构判断 + 3 条观察要点，禁止买卖指令）\n\n"
        "## 一、指标层\n"
        "（表格：指标 / 当前值或状态 / 评估 / 解读；含强弱、量比、换手、资金流向、市场温度）\n\n"
        "## 二、形态层\n"
        "### K 线结构\n### 经典形态\n### 量价关键位置\n\n"
        "## 三、趋势层\n"
        "（均线表 MA5/10/20/60/120：当前价位置 / 方向 / 支撑或压力）\n"
        "**近期涨跌幅** / **波段强度** / **背离风险**\n\n"
        "## 四、决策层\n"
        "### 观察清单\n"
        "（≥5 条）\n"
        "### 风险边界\n"
        "（≥3 条；只写边界与失效条件，不写买卖点）\n\n"
        "## 五、数据缺口\n"
        "## 六、研究边界\n"
        "硬约束：禁止编造数字；禁止买卖指令/目标价。"
    )
    choice = await chat_completion_message_async(
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"## 事实底稿（含行情/K线样本）\n\n{facts[:12000]}\n\n"
                    "请按四层框架出具完整量价会诊报告。"
                ),
            },
        ],
        temperature=0.45,
        timeout=220,
    )
    report = ""
    if choice:
        report = str((choice.get("message") or {}).get("content") or "").strip()
    if not report:
        report = (
            f"# 「{stock_name} ({stock})」量价会诊报告\n\n"
            f"生成完成 · {now_str}\n\n"
            "## 先看结论\n\n本次未能生成诊断正文。\n\n"
            "## 事实底稿摘要\n\n"
            f"{facts[:8000]}"
        )

    if progress:
        progress(95, "诊断完成")
    logger.warning("handle_stock_volume_price: report_len=%s", len(report))
    return SkillInvocationResult(
        ok=bool(report.strip()),
        summary=report,
        data={"stock": stock, "aspects": aspects},
    )
