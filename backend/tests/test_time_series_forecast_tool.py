"""time_series_forecast 模型类工具：参数校验与 adapter。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.agent_tool_args import TOOL_ARG_MODELS, validate_tool_arguments
from app.core.tool_skill_taxonomy import ToolCategory, _TOOL_CATEGORIES
from app.tool_center.adapters import _run_time_series_forecast, _slim_forecast_payload


def test_time_series_forecast_category_is_model():
    assert _TOOL_CATEGORIES["time_series_forecast"] == ToolCategory.MODEL


def test_time_series_forecast_args_defaults():
    params, err = validate_tool_arguments("time_series_forecast", {})
    assert err is None
    assert params == {"method": "rule", "series": "cea"}


def test_time_series_forecast_args_accepts_methods():
    for method in ("rule", "ets", "sarimax", "prophet"):
        params, err = validate_tool_arguments(
            "time_series_forecast", {"method": method, "series": "ccer"}
        )
        assert err is None
        assert params == {"method": method, "series": "ccer"}


def test_time_series_forecast_args_rejects_invalid_method():
    with pytest.raises(ValidationError):
        TOOL_ARG_MODELS["time_series_forecast"].model_validate({"method": "xgboost"})


def test_time_series_forecast_args_rejects_invalid_series():
    with pytest.raises(ValidationError):
        TOOL_ARG_MODELS["time_series_forecast"].model_validate({"series": "stock"})


def test_slim_forecast_payload_samples_points():
    raw = {
        "ok": True,
        "title": "CEA 日度预测",
        "unit": "元/吨",
        "source_name": "test",
        "source_page": "https://example.com",
        "queried_at": "2026-07-23T00:00:00+08:00",
        "forecast_method": "ets",
        "summary": {"year_end_price": 100.0, "last_close": 90.0},
        "latest": {"close": 90.0},
        "forecast_points": [
            {"t": "2026-07-24", "price": 91},
            {"t": "2026-09-01", "price": 95},
            {"t": "2026-12-31", "price": 100},
        ],
        "note": "ok",
    }
    slim = _slim_forecast_payload(raw, method="ets", series="cea")
    assert slim["ok"] is True
    assert slim["series"] == "cea"
    assert slim["method"] == "ets"
    assert slim["forecast_point_count"] == 3
    assert len(slim["forecast_sample"]) == 3
    assert "points" not in slim
    assert slim["summary"]["year_end_price"] == 100.0


def test_run_time_series_forecast_mocked(monkeypatch):
    async def _fake_cea(kind: str = "daily", *, method: str = "rule"):
        assert kind == "forecast"
        assert method == "prophet"
        return {
            "ok": True,
            "title": "CEA 日度预测（Prophet 预测 · 当前→年底）",
            "unit": "元/吨",
            "source_name": "mock",
            "source_page": "https://example.com",
            "queried_at": "2026-07-23T12:00:00+08:00",
            "forecast_method": "prophet",
            "summary": {
                "last_close": 80.0,
                "year_end_price": 88.0,
                "year_end_low": 70.0,
                "year_end_high": 100.0,
                "peak_price": 95.0,
                "peak_date": "2026-12-05",
                "trough_price": 78.0,
                "trough_date": "2026-08-01",
                "trading_days": 110,
                "note": "mock",
            },
            "latest": {"close": 80.0, "price": 80.0},
            "forecast_points": [
                {"t": "2026-07-24", "price": 81, "low": 79, "high": 83},
                {"t": "2026-12-31", "price": 88, "low": 70, "high": 100},
            ],
            "note": "mock",
        }

    monkeypatch.setattr(
        "app.services.carbon_compliance.market_sync.fetch_cea_chart_series",
        _fake_cea,
    )

    ctx = SimpleNamespace(loop_state={})
    ok, summary, data = asyncio.run(
        _run_time_series_forecast(ctx, {"method": "prophet", "series": "cea"})
    )
    assert ok is True
    assert "CEA" in summary
    assert data is not None
    assert data["method"] == "prophet"
    assert data["series"] == "cea"
    assert data["summary"]["year_end_price"] == 88.0
    assert data["forecast_point_count"] == 2
