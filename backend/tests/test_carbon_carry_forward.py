"""CEA 结转额度单测。"""

from datetime import date

from app.services.carbon_compliance.accounting import AccountingInput, compute_accounting
from app.services.carbon_compliance.alerts import build_alerts
from app.services.carbon_compliance.carry_forward import compute_carry_forward
from app.services.carbon_compliance.defaults import default_settings
from app.services.carbon_compliance.market_cycle import judge_market_cycle
from app.services.carbon_compliance.strategy_engine import build_strategy_payload


def test_max_carry_is_min_of_formula_and_holding():
    r = compute_carry_forward(
        base_qty=10,
        net_sell=4,
        year_end_holding=20,
        net_sell_multiplier=1.5,
        deadline_md="06-10",
        deadline_year=2026,
    )
    # 10 + 4*1.5 = 16 < 20 → max=16, excess=4
    assert abs(r.formula_cap - 16) < 1e-9
    assert abs(r.max_carry - 16) < 1e-9
    assert abs(r.excess - 4) < 1e-9
    assert abs(r.sell_to_expand_cap - 4 / 2.5) < 1e-9
    assert r.deadline == date(2026, 6, 10)


def test_holding_caps_carry():
    r = compute_carry_forward(base_qty=100, net_sell=10, year_end_holding=5)
    assert r.max_carry == 5
    assert r.excess == 0


def test_strategy_sells_carry_excess():
    # 盈余 1.0，基础 0.2，净卖出 0 → 可结转 0.2，超额 0.8
    acc = compute_accounting(
        AccountingInput(verified_override=0.5, free_cea_quota=1.5, own_ccer_eligible=0)
    )
    assert acc.compliance_gap < 0
    carry = compute_carry_forward(
        base_qty=0.2,
        net_sell=0,
        year_end_holding=1.0,
        deadline_md="06-10",
        deadline_year=2027,
    )
    market = judge_market_cycle([70, 80, 90], 75, 60, as_of=date(2026, 6, 1))
    payload = build_strategy_payload(
        risk_profile="conservative",
        annual_budget_cap=10_000_000,
        single_trade_limit=0,
        settings=default_settings(),
        accounting=acc,
        market=market,
        cea_price=100,
        ccer_price=60,
        sellable_cea=1.0,
        carry_forward=carry,
    )
    sells = [
        a
        for p in payload["plans"]
        for a in p["actions"]
        if a["action"] == "sell_cea" and a.get("qty", 0) > 0
    ]
    assert sells
    assert any("超额" in (a.get("note") or "") for a in sells)
    assert any(a.get("meta", {}).get("carry_excess", 0) > 0 for a in sells)


def test_carry_excess_alert():
    carry = compute_carry_forward(
        base_qty=1,
        net_sell=0,
        year_end_holding=5,
        deadline_md="06-10",
        deadline_year=date.today().year,
        as_of=date.today(),
    )
    alerts = build_alerts(
        compliance_year=date.today().year,
        clearance_deadline_md="12-31",
        warn_days=[90, 30, 15],
        compliance_gap=-1,
        ccer_used=0,
        ccer_cap=1,
        price_band="mid",
        carry_forward=carry,
        as_of=date.today(),
    )
    assert any(a["alert_type"] == "carry_forward_excess" for a in alerts)
