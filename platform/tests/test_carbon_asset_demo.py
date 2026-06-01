"""碳资产 demo API 冒烟测试。"""

from __future__ import annotations


def test_carbon_asset_feature_listed(client, admin_token):
    r = client.get("/api/v1/system/features", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    items = r.json()["data"]
    ids = [x["id"] for x in items]
    assert "carbon_asset_trading" in ids


def test_carbon_asset_overview_and_trade(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/carbon-assets/overview", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["demo"] is True

    r = client.post(
        "/api/v1/carbon-assets/trades",
        headers=h,
        json={"side": "buy", "asset_code": "CEA", "quantity_tco2": 10},
    )
    assert r.status_code == 200
    assert r.json()["data"]["trade"]["side"] == "buy"

    r = client.post(
        "/api/v1/carbon-assets/trades",
        headers=h,
        json={"side": "sell", "asset_code": "CEA", "quantity_tco2": 50_000},
    )
    assert r.status_code == 400
