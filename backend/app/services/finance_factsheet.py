"""理财圆桌「事实底稿」采集与拼装。

原则：
1. 能从 AKshare / 东财结构化 API 取的，优先 API，禁止编造；
2. 同一指标只取一次（去重），多源冲突时保留主源并在「来源」列标注；
3. 公告/互动/新闻/千股千评/股吧走结构化接口；资本运作、风险、社区舆情走联网补充；
4. 新闻/股吧/千股千评为软证据，可参与情绪与分歧对照，不得单独定论；
5. 输出完整 Markdown 表格，供圆桌辩论注入，不依赖 LLM 再压缩数字。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 对外文档：维度 → 推荐来源（脚本与注释共用）
FACT_SOURCE_MATRIX: list[dict[str, str]] = [
    {"维度": "公司定位", "主源": "东财 F10 公司概况 CompanySurvey / individual_info", "兜底": "联网检索"},
    {"维度": "公司自述市场地位", "主源": "互动易 / 公司概况经营范围", "兜底": "联网检索"},
    {"维度": "主营构成", "主源": "AKshare stock_zygc_em", "兜底": "东财 MAINOP_PRODUCT"},
    {"维度": "全年业绩", "主源": "AKshare stock_financial_abstract_ths（年报行）", "兜底": "—"},
    {"维度": "季度业绩", "主源": "AKshare stock_financial_abstract_ths（单季行）", "兜底": "—"},
    {"维度": "实时股价", "主源": "东财 push2 / 腾讯行情", "兜底": "日线末行"},
    {"维度": "最新行情区间", "主源": "AKshare stock_zh_a_hist（近 15 日）", "兜底": "—"},
    {"维度": "估值", "主源": "东财 push2 实时（PE/PB/PS/市值/换手）", "兜底": "个股信息总市值"},
    {"维度": "资金流向", "主源": "AKshare stock_individual_fund_flow", "兜底": "push2his fflow"},
    {"维度": "近期公告", "主源": "东财公告 API", "兜底": "—"},
    {"维度": "投资者互动", "主源": "AKshare stock_irm_cninfo", "兜底": "—"},
    {"维度": "个股新闻", "主源": "AKshare stock_news_em / 东财搜索", "兜底": "web_search"},
    {"维度": "市场情绪(千股千评)", "主源": "东财 datacenter 千股千评", "兜底": "—"},
    {"维度": "股吧热帖", "主源": "东财股吧列表页/API", "兜底": "web_search"},
    {"维度": "资本运作/风险/产品/舆情补充", "主源": "web_search", "兜底": "—"},
]


def _cell(text: Any, limit: int = 420) -> str:
    s = str(text or "").strip().replace("\n", "；")
    s = s.replace("|", "\\|")
    if not s:
        return "—"
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _pick_annual(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows or []:
        d = str(r.get("report_date") or "")
        if "年报" in d or (len(d) >= 10 and d[5:10] in ("12-31", "12/31")):
            out.append(r)
        elif d.endswith("年报"):
            out.append(r)
    return out[:4] or list(rows or [])[:2]


def _pick_quarterly(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows or []:
        d = str(r.get("report_date") or "")
        if any(x in d for x in ("一季", "中报", "三季", "Q1", "Q2", "Q3", "-03-31", "-06-30", "-09-30")):
            out.append(r)
    return out[:6] or list(rows or [])[:4]


def _format_kline_recent(kline: dict, n: int = 5) -> str:
    bars = list(kline.get("klines") or [])[-n:]
    if not bars:
        ch = kline.get("change_pct") or "--"
        return (
            f"区间 {kline.get('start_date', '')}~{kline.get('end_date', '')} "
            f"收盘 {kline.get('end_close', '--')}，涨跌幅 {ch}"
        )
    parts = []
    for b in reversed(bars):
        parts.append(
            f"{b.get('date')} 收 {b.get('close')} 元、当日 {b.get('change_pct', 0):+.2f}%"
        )
    ch = kline.get("change_pct") or "--"
    return (
        f"{'；'.join(parts)}。"
        f"区间({kline.get('start_date')}~{kline.get('end_date')})累计 {ch}"
    )


def _format_valuation(quote: dict, fallback_info: dict, kline: dict | None = None) -> str:
    bits = []
    date = (quote or {}).get("trade_date") or "最新"
    if quote:
        if quote.get("pe_dynamic") is not None:
            bits.append(f"PE(动) {quote['pe_dynamic']}")
        if quote.get("pe_ttm") is not None:
            bits.append(f"PE(TTM) {quote['pe_ttm']}")
        if quote.get("pb") is not None:
            bits.append(f"PB {quote['pb']}")
        if quote.get("ps_ttm") is not None:
            bits.append(f"PS(TTM) {quote['ps_ttm']}")
        if quote.get("turnover") is not None:
            bits.append(f"换手率 {quote['turnover']}%")
        if quote.get("total_mv"):
            bits.append(f"总市值 {quote['total_mv']}")
        if quote.get("float_mv"):
            bits.append(f"流通市值 {quote['float_mv']}")
        if quote.get("price") is not None:
            bits.append(f"现价 {quote['price']} 元")
        if quote.get("source"):
            bits.append(f"来源 {quote['source']}")
    if not bits and kline:
        # 用区间行情末价兜底，避免估值格完全空白
        bits.append(f"现价参考收盘 {kline.get('end_close', '待核实')} 元")
        bits.append(f"区间涨跌 {kline.get('change_pct', '待核实')}")
        date = kline.get("end_date") or date
    if not bits:
        info = fallback_info or {}
        bits.append(f"总股本参考 {info.get('total_shares') or '待核实'}")
        bits.append(f"流通股参考 {info.get('circulating_shares') or '待核实'}")
        bits.append("PE/PB 本窗口未返回，需东财操盘必读或年报核对")
    return f"（{date} 口径）" + "、".join(bits)


def _format_realtime_quote(quote: dict) -> str:
    """实时价量快照（可直接参与短线/情绪对照）。"""
    q = quote or {}
    if not q or (q.get("price") is None and not q.get("total_mv")):
        return "—"
    bits = []
    if q.get("name"):
        bits.append(str(q["name"]))
    if q.get("price") is not None:
        ch = q.get("change_pct")
        ch_s = f"（{ch:+.2f}%）" if isinstance(ch, (int, float)) else ""
        bits.append(f"现价 {q['price']} 元{ch_s}")
    if q.get("change") is not None:
        bits.append(f"涨跌额 {q['change']}")
    for k, label in (
        ("open", "开"),
        ("high", "高"),
        ("low", "低"),
        ("prev_close", "昨收"),
    ):
        if q.get(k) is not None:
            bits.append(f"{label} {q[k]}")
    if q.get("volume") is not None:
        bits.append(f"成交量 {q['volume']} 手")
    if q.get("amount") is not None:
        try:
            amt = float(q["amount"])
            bits.append(f"成交额 {amt / 1e8:.2f} 亿" if amt >= 1e6 else f"成交额 {amt}")
        except (TypeError, ValueError):
            bits.append(f"成交额 {q['amount']}")
    if q.get("turnover") is not None:
        bits.append(f"换手 {q['turnover']}%")
    if q.get("volume_ratio") is not None:
        bits.append(f"量比 {q['volume_ratio']}")
    if q.get("amplitude") is not None:
        bits.append(f"振幅 {q['amplitude']}%")
    if q.get("trade_date"):
        bits.append(f"时点 {q['trade_date']}")
    if q.get("source"):
        bits.append(f"源 {q['source']}")
    return "；".join(bits) if bits else "—"


def _format_news(rows: list[dict]) -> str:
    if not rows:
        return "—"
    parts = []
    for n in rows[:8]:
        parts.append(
            f"{n.get('date', '')} 〔{n.get('source', '')}〕"
            f"{_cell(n.get('title'), 60)}"
            f"：{_cell(n.get('summary'), 90)}"
        )
    return "；".join(parts)


def _format_retail_sentiment(sent: dict) -> str:
    s = sent or {}
    if not s or len(s) <= 1:
        return "—"
    bits = []
    def _num2(v) -> str:
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return str(v)

    if s.get("focus_index") is not None:
        bits.append(f"用户关注指数 {_num2(s['focus_index'])}（{s.get('focus_date') or '最新'}）")
    if s.get("total_score") is not None:
        bits.append(f"综合评分 {_num2(s['total_score'])}（{s.get('score_date') or '最新'}）")
    if s.get("org_participate") is not None:
        bits.append(f"机构参与度 {_num2(s['org_participate'])}（{s.get('org_date') or '最新'}）")
    if not bits:
        return "—"
    return "；".join(bits) + "。【情绪辅助，证据等级低于公告/财报，不可单独定论】"


def _format_guba(rows: list[dict]) -> str:
    if not rows:
        return "—"
    parts = []
    for p in rows[:8]:
        meta = []
        if p.get("read") is not None:
            meta.append(f"读{p['read']}")
        if p.get("comment") is not None:
            meta.append(f"评{p['comment']}")
        meta_s = f"（{'/'.join(meta)}）" if meta else ""
        parts.append(f"{p.get('date', '')} {_cell(p.get('title'), 70)}{meta_s}")
    return "；".join(parts) + "。【股吧讨论仅为散户风向样本，证据等级最低】"


def _format_main_business(items: list[dict]) -> str:
    if not items:
        return "—"
    parts = []
    for it in items[:8]:
        parts.append(
            f"{it.get('business_name', '')}：营收 {it.get('revenue', '--')} "
            f"（占比 {it.get('revenue_pct', '--')}），毛利率 {it.get('gross_margin', '--')}"
        )
    return "；".join(parts)


def _format_fin_rows(rows: list[dict], label: str) -> str:
    if not rows:
        return "—"
    parts = []
    for r in rows[:4]:
        parts.append(
            f"{r.get('report_date', '')}：营收 {r.get('revenue', '--')}，"
            f"归母净利 {r.get('parent_netprofit', '--')}，"
            f"EPS {r.get('basic_eps', '--')}，同比 {r.get('netprofit_yoy', '--')}"
        )
    return f"{label}：" + "；".join(parts)


def _format_profit(rows: list[dict]) -> str:
    if not rows:
        return "—"
    parts = []
    for r in rows[:4]:
        cash = r.get("operate_cashflow") or r.get("ocf")
        extra = f"，经营现金流 {cash}" if cash else ""
        parts.append(
            f"{r.get('report_date', '')}：ROE {r.get('roe', '--')}，"
            f"毛利率 {r.get('gross_margin', '--')}，净利率 {r.get('net_margin', '--')}{extra}"
        )
    return "；".join(parts)


def _format_fund_flow(rows: list[dict]) -> str:
    if not rows:
        return "—"
    parts = [
        f"{r.get('date')} 主力净流入 {r.get('main_net', '--')}"
        for r in rows[:5]
    ]
    return "；".join(parts)


def _format_announcements(rows: list[dict]) -> str:
    if not rows:
        return "—"
    return "；".join(f"{a.get('date')} {a.get('title', '')[:48]}" for a in rows[:8])


def _format_qa(rows: list[dict]) -> str:
    if not rows:
        return "—"
    parts = []
    for q in rows[:5]:
        parts.append(
            f"{q.get('date')} Q：{_cell(q.get('question'), 80)} "
            f"A：{_cell(q.get('answer'), 100)}"
        )
    return "；".join(parts)


def _infer_gaps(rows: list[tuple[str, str, str]]) -> list[str]:
    gaps: list[str] = []
    empty_dims = [d for d, v, _ in rows if not v or v == "—"]
    for d in empty_dims:
        gaps.append(f"{d}：本窗口未见结构化记录（不等于不存在，需专题补证）")
    # 常见外部周期缺口（结构化接口通常覆盖不到）
    always = [
        "国网/南网投资计划与招标中标明细（需公告或行业库）",
        "在手订单金额与产能利用率（需年报/调研纪要）",
        "自由现金流完整勾稽（若财报指标未返回则需年报 PDF 核对）",
    ]
    for g in always:
        if g not in gaps:
            gaps.append(g)
    return gaps[:12]


def assemble_fact_sheet_md(
    *,
    code: str,
    stock_name: str,
    f10: dict[str, Any],
    quote: dict[str, Any] | None = None,
    survey: dict[str, Any] | None = None,
    web_extra: str = "",
) -> str:
    """将结构化数据拼成完整事实底稿 Markdown（不去重丢失字段）。"""
    info = f10.get("company_info") or {}
    survey = survey or {}
    quote = quote or {}

    positioning = (
        survey.get("profile")
        or survey.get("business_scope")
        or (
            f"{info.get('company_name') or stock_name}，行业：{info.get('industry') or '待核实'}"
            f"；总股本 {info.get('total_shares') or '待核实'}，流通股 {info.get('circulating_shares') or '待核实'}"
        )
    )
    market_pos = (
        survey.get("market_position")
        or survey.get("comp_name")
        or info.get("full_name")
        or info.get("company_name")
        or ""
    )
    if not market_pos or market_pos == "—":
        market_pos = (
            "见下方「公开资料补充」（公司自述/媒体口径，需公告复核）"
            if web_extra
            else f"{stock_name or code}（行业 {info.get('industry') or '待核实'}；结构化市场地位未返回）"
        )

    fin = list(f10.get("financial_abstract") or [])
    annual = _format_fin_rows(_pick_annual(fin), "年报口径")
    quarterly = _format_fin_rows(_pick_quarterly(fin), "单季/中报口径")

    # 实时快照优先用 get_full_report 并行结果，再回落到外部传入的 quote
    live = f10.get("quote_live") if isinstance(f10.get("quote_live"), dict) else {}
    if live and (live.get("price") is not None or live.get("total_mv")):
        quote = {**(quote or {}), **{k: v for k, v in live.items() if v is not None}}

    table_rows: list[tuple[str, str, str]] = [
        ("公司定位", _cell(positioning, 500), "东财概况/F10"),
        ("公司自述市场地位", _cell(market_pos, 360), "东财概况/互动易"),
        ("主营构成", _cell(_format_main_business(f10.get("main_business") or []), 600), "zygc_em"),
        ("全年业绩", _cell(annual, 600), "financial_abstract"),
        ("季度业绩", _cell(quarterly, 600), "financial_abstract"),
        ("盈利能力/现金流", _cell(_format_profit(f10.get("profit_indicators") or []), 500), "financial_indicator"),
        ("实时股价", _cell(_format_realtime_quote(quote), 520), "push2/腾讯qt"),
        ("最新行情区间", _cell(_format_kline_recent(f10.get("kline_range") or {}), 500), "daily/kline"),
        ("估值", _cell(_format_valuation(quote, info, f10.get("kline_range") or {}), 360), "push2/indicator/hist"),
        ("资金流向", _cell(_format_fund_flow(f10.get("fund_flow") or []), 360), "fflow"),
        ("近期公告", _cell(_format_announcements(f10.get("announcements") or []), 500), "公告API"),
        ("投资者互动", _cell(_format_qa(f10.get("qa") or []), 600), "互动易"),
        ("个股新闻", _cell(_format_news(f10.get("news") or []), 700), "东财新闻"),
        (
            "市场情绪(千股千评)",
            _cell(_format_retail_sentiment(f10.get("retail_sentiment") or {}), 360),
            "东财千股千评",
        ),
        ("股吧热帖", _cell(_format_guba(f10.get("guba_posts") or []), 500), "东财股吧"),
    ]

    # 业绩预告 / 股东 / 北向 —— 并入表，避免重复拉取
    fc = f10.get("forecast") or []
    if fc:
        f0 = fc[0]
        table_rows.append((
            "业绩预告",
            _cell(
                f"{f0.get('forecast_type', '')}；区间 {f0.get('lower')}~{f0.get('upper')}；"
                f"同比 {f0.get('change_lower')}~{f0.get('change_upper')}；"
                f"{f0.get('reason', '')}",
                360,
            ),
            "业绩预告API",
        ))
    hc = f10.get("holder_count") or []
    if hc:
        table_rows.append((
            "股东户数",
            _cell(f"{hc[0].get('report_date')} 户数 {hc[0].get('holder_count')}", 200),
            "股东户数API",
        ))
    nb = f10.get("northbound") or []
    if nb:
        n0 = nb[0] if isinstance(nb[0], dict) else {}
        table_rows.append((
            "北向持仓",
            _cell(
                f"{n0.get('date')} 持股占比 {n0.get('hold_pct')}，市值 {n0.get('hold_value')}",
                200,
            ),
            "北向API",
        ))

    # 联网块：原样保留，引导模型/读者对照
    web_block = (web_extra or "").strip()
    if web_block:
        table_rows.extend([
            ("资本运作（报道）", "见「公开资料补充」中的资本运作相关条目", "web_search"),
            ("风险事项（报道）", "见「公开资料补充」中的风险相关条目", "web_search"),
            ("产品动态（报道）", "见「公开资料补充」中的产品/业务条目", "web_search"),
            ("舆情/社区补充", "见「公开资料补充」中的股吧/雪球/评论相关条目", "web_search"),
            ("重大新闻补充", "见「公开资料补充」（与上方结构化「个股新闻」交叉核对）", "web_search"),
        ])
    else:
        table_rows.extend([
            ("资本运作（报道）", "—", "web_search"),
            ("风险事项（报道）", "—", "web_search"),
            ("产品动态（报道）", "—", "web_search"),
            ("舆情/社区补充", "—", "web_search"),
            ("重大新闻补充", "—", "web_search"),
        ])

    lines = [
        f"**标的**：{stock_name}（{code}）",
        "",
        "以下为结构化事实底稿（数字仅在此处详列一次；辩论轮次只引用维度名，不重复铺表）。",
        "",
        "### 一、已获取（可作结构化依据）",
        "",
        "| 维度 | 关键事实（关键数字全文首次详列） | 来源 |",
        "|------|-------------------------------|------|",
    ]
    for dim, fact, src in table_rows:
        lines.append(f"| {dim} | {fact} | {src} |")

    lines.extend([
        "",
        "### 二、本窗口未见结构化记录（不等于不存在）",
        "",
        "- **股东增减持**：本数据窗口未见结构化记录时，不能据此写成「公司没有相关事项」；如需结论须以后续公告核验。",
        "- **其他未返回字段**：接口空值或失败项见下表「需专题补证」，不等于事项不存在。",
        "",
        "### 三、公开资料补充（证据等级低于正式公告/财报，需以公告或财报复核）",
        "",
        "> 使用约定：上方「个股新闻 / 千股千评 / 股吧热帖 / 投资者互动」与本节联网摘要均为**软证据**，"
        "可参与分歧与情绪对照，但不得单独支撑周期位置或投资结论；与公告/财报冲突时以公告/财报为准。",
        "",
    ])
    soft_blocks: list[str] = []
    news_txt = _format_news(f10.get("news") or [])
    if news_txt and news_txt != "—":
        soft_blocks.append("#### 结构化个股新闻摘录\n\n" + news_txt)
    guba_txt = _format_guba(f10.get("guba_posts") or [])
    if guba_txt and guba_txt != "—":
        soft_blocks.append("#### 股吧热帖摘录\n\n" + guba_txt)
    if web_block:
        soft_blocks.append("#### 联网检索补充\n\n" + web_block)
    if soft_blocks:
        lines.append("\n\n".join(soft_blocks))
    else:
        lines.append("（本次未执行联网补充或未返回有效结果）")

    gaps = _infer_gaps(table_rows)
    lines.extend([
        "",
        "### 四、需专题补证（本次底稿完全缺失或薄弱的外部/专项数据）",
        "",
        "以下缺口直接决定：报告只能识别暴露变量，**无法在证据不足时强行定位周期位置或给出投资判断**。",
        "",
    ])
    for g in gaps:
        lines.append(f"- {g}")
    lines.extend([
        "- 行业投资额、招标节奏、在手订单、产能利用率、库存、下游景气、上游材料价格——若上文未给出结构化数字，一律视为**本次未获取到**。",
        "",
        "> 数据源矩阵（主源/兜底）供核验：",
        "",
        "| 维度 | 主源 | 兜底 |",
        "|------|------|------|",
    ])
    for row in FACT_SOURCE_MATRIX:
        lines.append(f"| {row['维度']} | {row['主源']} | {row['兜底']} |")

    return "\n".join(lines)


async def build_roundtable_fact_sheet(
    code: str,
    stock_name: str = "",
    *,
    web_extra: str = "",
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """采集 F10（含新闻/情绪/股吧）+ 估值快照 + 公司概况，拼装完整事实底稿。"""
    from app.services import finance_f10 as f10

    pure = (code or "").split(".")[0].strip()
    f10_data = await f10.get_full_report(pure, keywords=keywords)
    info = f10_data.get("company_info") or {}
    name = (
        stock_name
        or info.get("company_name")
        or info.get("full_name")
        or pure
    )

    quote: dict = {}
    survey: dict = {}
    # 优先复用 get_full_report 内并行拿到的 quote_live，避免重复请求
    live = f10_data.get("quote_live") if isinstance(f10_data.get("quote_live"), dict) else {}
    if live and (live.get("price") is not None or live.get("total_mv")):
        quote = live
    else:
        try:
            quote = await f10.get_quote_snapshot(pure)
        except Exception as exc:
            logger.warning("get_quote_snapshot failed: %s", exc)
    try:
        survey = await f10.get_company_survey(pure)
    except Exception as exc:
        logger.warning("get_company_survey failed: %s", exc)

    md = assemble_fact_sheet_md(
        code=pure,
        stock_name=name,
        f10=f10_data,
        quote=quote if isinstance(quote, dict) else {},
        survey=survey if isinstance(survey, dict) else {},
        web_extra=web_extra,
    )
    return {
        "code": pure,
        "stock_name": name,
        "fact_sheet_md": md,
        "f10": f10_data,
        "quote": quote,
        "survey": survey,
        "news": f10_data.get("news") or [],
        "retail_sentiment": f10_data.get("retail_sentiment") or {},
        "guba_posts": f10_data.get("guba_posts") or [],
    }
