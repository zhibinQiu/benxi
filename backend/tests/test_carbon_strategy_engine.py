"""策略引擎与行情周期单测。"""

from datetime import date

from app.services.carbon_compliance.accounting import AccountingInput, compute_accounting
from app.services.carbon_compliance.defaults import default_settings
from app.services.carbon_compliance.market_cycle import judge_market_cycle
from app.services.carbon_compliance.strategy_engine import build_strategy_payload


def test_market_cycle_low_buy():
    prices = [50 + i for i in range(20)] + [40]
    r = judge_market_cycle(prices, 40, 30, as_of=date(2026, 3, 1))
    assert r.price_band == "low"
    assert r.time_window == "early"
    assert r.action_tag == "buy"


def test_strategy_three_plans_cea_ccer_only():
    # 数量单位：万吨
    acc = compute_accounting(
        AccountingInput(
            verified_override=1.0,
            free_cea_quota=0.7,
            own_ccer_eligible=0.02,
            ccer_max_ratio=0.05,
        )
    )
    market = judge_market_cycle(
        [60, 70, 80, 90, 100],
        65,
        50,
        as_of=date(2026, 5, 1),
    )
    for profile in ("conservative", "balanced", "aggressive"):
        payload = build_strategy_payload(
            risk_profile=profile,
            annual_budget_cap=5_000_000,
            single_trade_limit=0,
            settings=default_settings(),
            accounting=acc,
            market=market,
            cea_price=80,
            ccer_price=50,
            sellable_cea=0,
            cea_price_predicted=79,
        )
        assert len(payload["plans"]) == 3
        keys = {p["key"] for p in payload["plans"]}
        assert keys == {"min_cost", "optimized", "full_compliance"}
        for plan in payload["plans"]:
            actions = [a["action"] for a in plan["actions"]]
            assert "buy_green_power" not in actions
            assert "buy_green_cert" not in actions
            assert all(a in ("use_ccer", "buy_ccer", "buy_cea", "sell_cea") for a in actions)
        if profile == "conservative":
            full = next(p for p in payload["plans"] if p["key"] == "full_compliance")
            assert "buy_ccer" not in [a["action"] for a in full["actions"]] or all(
                a.get("qty", 0) == 0 for a in full["actions"] if a["action"] == "buy_ccer"
            )


def test_offline_preferred_on_buy():
    acc = compute_accounting(
        AccountingInput(verified_override=0.5, free_cea_quota=0.4, own_ccer_eligible=0)
    )
    market = judge_market_cycle([70, 80, 90], 75, 60, as_of=date(2026, 6, 1))
    settings = default_settings()
    settings["channel"] = {"prefer_offline": True, "offline_discount_vs_listed": 0.05}
    payload = build_strategy_payload(
        risk_profile="balanced",
        annual_budget_cap=10_000_000,
        single_trade_limit=0,
        settings=settings,
        accounting=acc,
        market=market,
        cea_price=100,
        ccer_price=60,
        cea_price_predicted=100,
    )
    plan = payload["plans"][0]
    buys = [a for a in plan["actions"] if a["action"] == "buy_cea"]
    assert buys
    assert buys[0]["meta"].get("channel") == "offline_preferred"
    assert abs(buys[0]["unit_price"] - 95.0) < 1e-6
    assert "线下撮合" in buys[0]["note"]


def test_no_green_actions_even_with_legacy_attrs():
    acc = compute_accounting(
        AccountingInput(verified_override=0.5, free_cea_quota=0.4, own_ccer_eligible=0)
    )
    market = judge_market_cycle([70, 80, 90], 75, 60, as_of=date(2026, 6, 1))
    payload = build_strategy_payload(
        risk_profile="aggressive",
        annual_budget_cap=10_000_000,
        single_trade_limit=0,
        enterprise_attrs={"listed": True, "cbam": True},
        settings=default_settings(),
        accounting=acc,
        market=market,
        green_premium_per_mwh=10,
        grec_price=5,
        own_renewable_mwh=1000,
    )
    for plan in payload["plans"]:
        assert not any(
            a["action"] in ("buy_green_cert", "buy_green_power") for a in plan["actions"]
        )
