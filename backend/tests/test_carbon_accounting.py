"""碳排放核算引擎单测。"""

from app.services.carbon_compliance.accounting import AccountingInput, compute_accounting


def test_scope1_only_ignores_scope2_inputs():
    """履约核查仅 Scope1；外购电 / Scope2 / 绿电输入不计入核查总量。"""
    r = compute_accounting(
        AccountingInput(
            scope1_combustion=1000,
            scope1_process=200,
            scope2_power=500,
            purchased_mwh=1000,
            market_green_mwh=200,
            grid_emission_factor=0.5,
            free_cea_quota=800,
            own_ccer_eligible=50,
            ccer_max_ratio=0.05,
        )
    )
    assert r.scope1_total == 1200
    assert r.scope2_from_power == 0
    assert r.reducible_power == 0
    assert r.verified_emission == 1200
    assert r.compliance_gap == 400
    assert abs(r.ccer_cap - 60) < 1e-6
    assert r.own_ccer_usable == 50
    assert abs(r.residual_gap_after_own_ccer - 350) < 1e-6


def test_verified_override():
    r = compute_accounting(
        AccountingInput(
            scope1_combustion=9999,
            verified_override=2000,
            free_cea_quota=1500,
            own_ccer_eligible=200,
            ccer_max_ratio=0.05,
        )
    )
    assert r.verified_emission == 2000
    assert r.compliance_gap == 500
    assert r.ccer_cap == 100
    assert r.own_ccer_usable == 100


def test_surplus_no_ccer_use():
    r = compute_accounting(
        AccountingInput(
            verified_override=1000,
            free_cea_quota=1200,
            own_ccer_eligible=100,
            ccer_max_ratio=0.05,
        )
    )
    assert r.compliance_gap == -200
    assert r.own_ccer_usable == 0
