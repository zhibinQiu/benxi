"""版本更新亮点接口。"""


def test_release_highlights_requires_auth(client):
    r = client.get("/api/v1/system/release-highlights")
    assert r.status_code == 401


def test_release_highlights(client, admin_token):
    r = client.get(
        "/api/v1/system/release-highlights",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    if data is None:
        return
    assert data["version"]
    assert isinstance(data.get("features"), list)
    assert isinstance(data.get("fixes"), list)
