"""登录页功能展示公开接口。"""


def test_showcase_features_public(client):
    r = client.get("/api/v1/system/showcase-features")
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert isinstance(rows, list)
    assert len(rows) > 0
    ids = {row["id"] for row in rows}
    assert "pdf_translate" in ids
    assert "carbon_asset_trading" not in ids
