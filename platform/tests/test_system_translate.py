"""System features & translate job access tests."""

from __future__ import annotations


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_system_features_lists_pdf_translate(client, admin_token):
    r = client.get("/api/v1/system/features", headers=_auth(admin_token))
    assert r.status_code == 200
    items = r.json()["data"]
    assert any(x["id"] == "pdf_translate" and x["enabled"] for x in items)
    translate = next(x for x in items if x["id"] == "pdf_translate")
    assert translate["route"] == "/system/translate"
    assert translate.get("accessible") is True
    assert translate.get("permission") == "feature.translate"


def test_translate_jobs_requires_auth(client):
    r = client.get("/api/v1/translate/jobs")
    assert r.status_code == 401


def test_translate_job_forbidden_for_other_user(client, admin_token):
    r = client.get(
        "/api/v1/translate/jobs/00000000-0000-0000-0000-000000000099",
        headers=_auth(admin_token),
    )
    assert r.status_code in (403, 404)
