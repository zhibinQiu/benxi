"""履约策略 API / 引擎门面冒烟（不依赖真实 DB 会话时可测纯函数路径）。"""

from __future__ import annotations

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.services.carbon_compliance.defaults import default_settings, deep_merge
from app.services.carbon_compliance.report_export import strategy_run_to_markdown


def test_plugin_description_updated():
    ensure_plugins_loaded()
    p = get_plugin("carbon_assistant")
    assert p is not None
    assert "履约" in (p.description or "") or "compliance" in (p.description or "").lower()


def test_settings_merge():
    base = default_settings()
    merged = deep_merge(base, {"compliance": {"ccer_max_ratio": 0.08}})
    assert merged["compliance"]["ccer_max_ratio"] == 0.08
    assert merged["cost"]["listing_fee_rate"] == base["cost"]["listing_fee_rate"]
    assert merged["cost"]["block_fee_rate"] == base["cost"]["block_fee_rate"]


def test_report_markdown_contains_plans():
    md = strategy_run_to_markdown(
        enterprise_name="测试电厂",
        compliance_year=2025,
        accounting={
            "verified_emission": 10000,
            "free_cea_quota": 8000,
            "compliance_gap": 2000,
            "ccer_cap": 500,
            "own_ccer_usable": 100,
        },
        market_tags={
            "price_band": "low",
            "time_window": "early",
            "action_tag": "buy",
            "rationale": "低位宜采购",
        },
        plans=[
            {
                "key": "min_cost",
                "title": "最低成本履约方案",
                "description": "刚需",
                "total_cost": 1000,
                "net_saving": 0,
                "time_window": "early",
                "actions": [
                    {
                        "action": "buy_cea",
                        "qty": 1900,
                        "unit_price": 80,
                        "window": "early",
                        "note": "分批采购",
                    }
                ],
                "compliance": {"notes": []},
            }
        ],
    )
    assert "测试电厂" in md
    assert "最低成本履约方案" in md
    assert "买入 CEA" in md
