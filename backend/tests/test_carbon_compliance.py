"""合规校验单测。"""

from datetime import date, timedelta

from app.services.carbon_compliance.compliance import (
    PlanAction,
    eligible_ccer_qty,
    filter_plan_actions,
)


def test_eligible_excludes_expired_and_dual_rights():
    today = date(2026, 6, 1)
    qty = eligible_ccer_qty(
        [
            {"eligible_qty": 100, "expire_at": "2025-01-01"},
            {"eligible_qty": 50, "expire_at": "2030-01-01", "linked_green_cert": True},
            {"eligible_qty": 80, "expire_at": "2030-01-01"},
        ],
        as_of=today,
    )
    assert qty == 80


def test_ccer_cap_blocks_excess():
    actions = [
        PlanAction(action="use_ccer", qty=60, unit_price=0),
        PlanAction(action="buy_ccer", qty=50, unit_price=40),
    ]
    r = filter_plan_actions(
        actions,
        ccer_cap=80,
        annual_budget_cap=1_000_000,
        single_trade_limit=0,
        large_split_threshold=100_000,
    )
    total_ccer = sum(a.qty for a in r.actions if a.action in ("use_ccer", "buy_ccer"))
    assert total_ccer <= 80 + 1e-9
    assert any(i.code == "ccer_cap" or "CCER" in n for i in r.issues for n in [""]) or any(
        "CCER" in n for n in r.notes
    )


def test_dual_rights_blocked():
    r = filter_plan_actions(
        [
            PlanAction(
                action="use_ccer",
                qty=10,
                meta={"linked_green_cert": True},
            )
        ],
        ccer_cap=100,
        annual_budget_cap=0,
        single_trade_limit=0,
        large_split_threshold=0,
    )
    assert any(i.code == "dual_rights" for i in r.issues)
    assert r.actions == []


def test_budget_cap_blocks_purchase():
    # qty 万吨 × 单价 元/吨 → 金额含 ×10000
    r = filter_plan_actions(
        [PlanAction(action="buy_cea", qty=0.1, unit_price=80)],
        ccer_cap=100,
        annual_budget_cap=1000,
        single_trade_limit=0,
        large_split_threshold=0,
    )
    assert any(i.code == "budget_cap" for i in r.issues)
    assert r.actions == []


def test_cash_cost_uses_wan_to_tons():
    from app.services.carbon_compliance.units import (
        fee_cny,
        fee_rate_for_channel,
        notional_cny,
        resolve_fee_rates,
        trade_cash_cny,
    )

    # 成交总额 1 万吨 × 80 元/吨 = 800_000 元
    assert notional_cny(1.0, 80.0) == 800_000.0
    # 手续费 = 成交总额 × 费率
    assert fee_cny(1.0, 80.0, fee_rate=0.01) == 8_000.0
    # 买入应付 = 总额 + 手续费；卖出实收 = 总额 − 手续费
    assert trade_cash_cny(1.0, 80.0, fee_rate=0.006, side="buy") == 800_000.0 + 4_800.0
    assert trade_cash_cny(1.0, 80.0, fee_rate=0.006, side="sell") == 800_000.0 - 4_800.0
    listing, block = resolve_fee_rates(
        {"listing_fee_rate": 0.006, "block_fee_rate": 0.005}
    )
    assert listing == 0.006 and block == 0.005
    assert fee_rate_for_channel("listed_fallback", listing_fee_rate=0.006, block_fee_rate=0.005) == 0.006
    assert fee_rate_for_channel("offline_preferred", listing_fee_rate=0.006, block_fee_rate=0.005) == 0.005
    # 旧字段回退
    assert resolve_fee_rates({"trade_fee_rate": 0.004}) == (0.004, 0.004)


def test_eligible_caps_to_holding_qty():
    today = date(2026, 6, 1)
    # 可抵扣虚高时按持有量封顶
    assert (
        eligible_ccer_qty(
            [{"qty": 0.65, "eligible_qty": 6.5, "expire_at": "2030-01-01"}],
            as_of=today,
        )
        == 0.65
    )
    # 可抵扣为 0 时回退持有量
    assert (
        eligible_ccer_qty(
            [{"qty": 1.2, "eligible_qty": 0, "expire_at": "2030-01-01"}],
            as_of=today,
        )
        == 1.2
    )
