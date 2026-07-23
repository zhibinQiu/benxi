"""CEA 日度至年底预测单测。"""

from datetime import date, timedelta

from app.services.carbon_compliance.price_forecast import forecast_cea_to_year_end


def _synth_history(n: int = 200, start: date | None = None) -> list[dict]:
    start = start or date(2025, 1, 2)
    rows = []
    px = 80.0
    d = start
    while len(rows) < n:
        if d.weekday() < 5:
            # 轻微上行 + 噪声
            px = max(40.0, px + (0.02 if d.month >= 10 else 0.005) + ((d.toordinal() % 7) - 3) * 0.05)
            rows.append({"t": d.isoformat(), "close": round(px, 2)})
        d += timedelta(days=1)
    return rows


def test_forecast_to_year_end_has_daily_points():
    hist = _synth_history(220, start=date(2025, 6, 1))
    as_of = date(2026, 7, 20)
    # 截断历史到 as_of
    hist = [h for h in hist if h["t"] <= as_of.isoformat()]
    # 补足：用真实长度不够时再造到 as_of
    if not hist or hist[-1]["t"] < as_of.isoformat():
        hist = _synth_history(260, start=date(2025, 1, 2))
        hist = [h for h in hist if h["t"] <= as_of.isoformat()]

    fc = forecast_cea_to_year_end(hist, as_of=as_of, year=2026)
    assert fc["ok"] is True
    pts = fc["points"]
    assert len(pts) > 50
    assert pts[0]["t"] > as_of.isoformat() or pts[0]["t"] >= hist[-1]["t"]
    assert pts[-1]["t"].startswith("2026-12")
    assert "price" in pts[0] and "low" in pts[0] and "high" in pts[0]
    assert pts[0]["low"] <= pts[0]["price"] <= pts[0]["high"]
    s = fc["summary"]
    assert s["year_end_price"] > 0
    assert s["trading_days"] == len(pts)
    assert s["peak_date"] >= pts[0]["t"]


def test_rule_forecast_peak_before_year_end():
    """履约季冲高回落：预测高点应早于年底（或至少不严格单调抬升到 12/31）。"""
    from app.services.carbon_compliance.price_forecast import forecast_to_year_end

    # 构造多年含四季度抬升的历史，供溢价估计
    hist = _synth_history(400, start=date(2024, 1, 2))
    as_of = date(2026, 7, 15)
    hist = [h for h in hist if h["t"] <= as_of.isoformat()]
    fc = forecast_to_year_end(hist, as_of=as_of, year=2026, method="rule")
    assert fc["ok"] is True
    pts = fc["points"]
    assert pts[-1]["t"].startswith("2026-12")
    peak = max(pts, key=lambda p: p["price"])
    year_end = pts[-1]["price"]
    # 高点不在最后一天，或年底相对峰值有回吐
    assert peak["t"] < pts[-1]["t"] or year_end <= peak["price"] * 1.001
    assert peak["price"] >= year_end * 0.995
    note = (fc.get("summary") or {}).get("note") or ""
    assert "Q4" not in note and "H1" not in note
    assert "冲高回落" in note or "回吐" in note


def test_compliance_bump_shape():
    from app.services.carbon_compliance.price_forecast import _compliance_season_daily_bump

    amp = 0.06
    early = _compliance_season_daily_bump(date(2026, 10, 15), amp=amp)
    mid = _compliance_season_daily_bump(date(2026, 12, 2), amp=amp)
    late = _compliance_season_daily_bump(date(2026, 12, 28), amp=amp)
    assert mid > early > 0
    assert late < 0


def test_forecast_insufficient_history():
    fc = forecast_cea_to_year_end([{"t": "2026-01-02", "close": 80}], as_of=date(2026, 7, 1))
    assert fc["ok"] is False


def test_forecast_methods_ets_sarimax():
    from app.services.carbon_compliance.price_forecast import forecast_to_year_end

    hist = _synth_history(220, start=date(2025, 1, 2))
    as_of = date(2026, 7, 20)
    hist = [h for h in hist if h["t"] <= as_of.isoformat()]

    ets = forecast_to_year_end(hist, as_of=as_of, year=2026, method="ets")
    assert ets["ok"] is True
    assert ets["method"] in ("ets", "ets_fallback_rule")
    assert len(ets["points"]) > 30

    sx = forecast_to_year_end(hist, as_of=as_of, year=2026, method="sarimax")
    assert sx["ok"] is True
    assert "sarimax" in str(sx.get("method") or "")
    assert len(sx["points"]) > 30

    pr = forecast_to_year_end(hist, as_of=as_of, year=2026, method="prophet")
    assert pr["ok"] is True
    assert len(pr["points"]) > 30


def test_ccer_forecast():
    from app.services.carbon_compliance.price_forecast import forecast_to_year_end

    hist = _synth_history(180, start=date(2025, 8, 1))
    as_of = date(2026, 7, 20)
    hist = [h for h in hist if h["t"] <= as_of.isoformat()]
    fc = forecast_to_year_end(hist, as_of=as_of, year=2026, instrument="ccer")
    assert fc["ok"] is True
    assert fc["instrument"] == "ccer"
    assert "规则模型" in (fc["summary"]["note"] or "") or "冲高回落" in (fc["summary"]["note"] or "")
