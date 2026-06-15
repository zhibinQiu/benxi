"""碳资产 demo API 冒烟测试。"""

from __future__ import annotations


def test_carbon_asset_feature_listed_but_disabled(client, admin_token):
    r = client.get("/api/v1/system/features", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    item = next(x for x in r.json()["data"] if x["id"] == "carbon_asset_trading")
    assert item["enabled"] is False
    assert item["accessible"] is False
    assert item["route"] is None


def test_carbon_asset_api_unavailable_when_disabled(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/carbon-assets/overview", headers=h)
    assert r.status_code == 404
