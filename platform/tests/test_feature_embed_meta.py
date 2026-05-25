"""Feature iframe embed meta API."""

from __future__ import annotations


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_smart_forecast_embed_meta(client, admin_token):
    r = client.get(
        "/api/v1/system/features/smart_forecast/embed-meta",
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["available"] is True
    assert data["embed_url"] == "http://127.0.0.1:8501/"
    assert data.get("requires_auth") is False
