"""系统版本接口。"""


def test_system_version(client):
    r = client.get("/api/v1/system/version")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["version"] == "2.1.0"
    assert data["version_label"] == "v2"
    assert data["app_name"]
