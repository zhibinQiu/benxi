"""碳行情：环交所 K 线解析与同步策略单测。"""

from datetime import date, datetime, timedelta, timezone

from app.services.carbon_compliance.defaults import default_settings
from app.services.carbon_compliance.market_sync import (
    aggregate_daily_to_monthly,
    cneeex_url,
    html_to_text,
    parse_ccer_daily_article,
    parse_ccer_list_trade_date,
    parse_ccn_cea_quote,
    parse_ccn_ccer_history_table,
    parse_ccn_ccer_quote,
    parse_cneeex_daily_bars,
    parse_cneeex_intraday_latest,
    parse_market_page,
    period_tag_for_month,
    CNEEEX_DAILY_URL,
)
from app.services.carbon_compliance_service import should_auto_sync_market

SAMPLE_DAILY = [
    ["2026-07-16", "89.00", "89.50", "88.80", "90.00", "1000"],
    ["2026-07-17", "89.50", "90.00", "89.20", "90.50", "2000"],
    ["2026-07-20", "90.20", "90.15", "90.05", "90.30", "69272"],
]

SAMPLE_INTRADAY = [
    ["09:30", "90.02", "0.00", "0.00", "0.00", "0.00", "0", "0.00", "0.00%"],
    ["15:00", "90.15", "90.20", "90.30", "90.05", "0.00", "69,272", "6,244,559.40", "0.14%"],
]

SAMPLE_HTML = (
    "全国碳市场综合价格行情（CEA） （2026年7月20日） "
    "开盘 （元/吨） 最高 （元/吨） 最低 （元/吨） 收盘 （元/吨） 涨跌幅 （%） "
    "90.20 90.30 90.05 90.15 0.14 来源：上海环境能源交易所 "
    "全国温室气体自愿减排交易行情 （2026年7月20日） "
    "成交量（吨） 成交额（元） 均价（元/吨） 涨跌幅 （%） "
    "62001 4992190.50 80.52 -10.44 来源：北京绿色交易所"
)


def test_cneeex_url_appends_timestamp():
    u = cneeex_url(CNEEEX_DAILY_URL, ts_ms=1784594250701)
    assert u.endswith("?1784594250701")
    assert "hiskline.json" in u


def test_parse_cneeex_daily_bars():
    quotes = parse_cneeex_daily_bars(SAMPLE_DAILY)
    assert len(quotes) == 3
    last = quotes[-1]
    assert last.trade_date == date(2026, 7, 20)
    assert last.open == 90.20
    assert last.close == 90.15
    assert last.low == 90.05
    assert last.high == 90.30


def test_parse_cneeex_intraday_latest():
    q = parse_cneeex_intraday_latest(SAMPLE_INTRADAY, as_of=date(2026, 7, 20))
    assert q is not None
    assert q.close == 90.15
    assert q.open == 90.20
    assert q.high == 90.30
    assert q.low == 90.05



def test_aggregate_daily_to_monthly():
    quotes = parse_cneeex_daily_bars(SAMPLE_DAILY)
    monthly = aggregate_daily_to_monthly(quotes)
    assert len(monthly) == 1
    m = monthly[0]
    assert m.year_month == "2026-07"
    assert m.last_close == 90.15
    assert m.high == 90.50
    assert m.low == 88.80
    assert m.trade_days == 3


def test_parse_cea_from_ccn_text():
    q = parse_ccn_cea_quote(SAMPLE_HTML)
    assert q is not None
    assert q.close == 90.15


def test_parse_ccer_from_ccn_text():
    q = parse_ccn_ccer_quote(SAMPLE_HTML)
    assert q is not None
    assert q.avg_price == 80.52


def test_parse_ccer_list_trade_date():
    assert parse_ccer_list_trade_date(
        "2026年7月20日全国温室气体自愿减排交易市场交易行情"
    ) == date(2026, 7, 20)
    assert parse_ccer_list_trade_date("无日期") is None


def test_parse_ccer_daily_article_avg():
    html = (
        "<p>2026年7月20日，核证自愿减排量成交量62,001吨，"
        "成交额4,992,190.50元，成交均价80.52元/吨。</p>"
    )
    q = parse_ccer_daily_article(html, trade_date=date(2026, 7, 20))
    assert q is not None
    assert q.avg_price == 80.52
    assert q.volume == 62001.0


def test_parse_ccer_daily_article_no_trade():
    html = "<p>2026年6月22日，核证自愿减排量无成交。</p>"
    assert parse_ccer_daily_article(html, trade_date=date(2026, 6, 22)) is None


def test_parse_ccer_daily_article_amount_fallback():
    html = (
        "<p>2024年1月22日，全国温室气体自愿减排交易市场总成交量375,315 吨，"
        "总成交额23,835,280.00 元。</p>"
    )
    q = parse_ccer_daily_article(html, trade_date=date(2024, 1, 22))
    assert q is not None
    assert abs(q.avg_price - 63.51) < 0.01


def test_parse_ccn_ccer_history_table():
    text = (
        "时间 总成交量（吨） 成交额（元） 均价（元/吨） 涨跌幅（%） "
        "2026/1/5 100001 8,150,075.00 81.50 -4.12 "
        "2026/1/6 20101 1,668,334.00 83.00 1.84"
    )
    rows = parse_ccn_ccer_history_table(text)
    assert len(rows) == 2
    assert rows[0].trade_date == date(2026, 1, 5)
    assert rows[0].avg_price == 81.50
    assert rows[1].avg_price == 83.00


def test_parse_market_page_html():
    html = f"<html><body><div>{SAMPLE_HTML}</div></body></html>"
    parsed = parse_market_page(html)
    assert parsed["cea"] is not None
    assert parsed["ccer"] is not None


def test_html_to_text_strips_tags():
    assert "90.15" in html_to_text("<b>90.15</b> 元/吨")


def test_period_tag():
    assert period_tag_for_month(3) == "early"
    assert period_tag_for_month(7) == "mid"
    assert period_tag_for_month(11) == "late"


def test_should_auto_sync_respects_period_and_flag():
    base = default_settings()
    assert should_auto_sync_market(base) is True
    disabled = {
        "integrations": {"market_sync_enabled": False, "market_sync_period": "day"}
    }
    assert should_auto_sync_market(disabled) is False
    recent = {
        "integrations": {
            "market_sync_enabled": True,
            "market_sync_period": "day",
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
        }
    }
    assert should_auto_sync_market(recent) is False
    stale = {
        "integrations": {
            "market_sync_enabled": True,
            "market_sync_period": "day",
            "last_sync_at": (
                datetime.now(timezone.utc) - timedelta(hours=13)
            ).isoformat(),
        }
    }
    assert should_auto_sync_market(stale) is True
