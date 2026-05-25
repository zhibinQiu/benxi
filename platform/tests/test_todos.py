"""待办事项 API."""

from __future__ import annotations


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_todo_crud_and_reorder(client, admin_token):
    r = client.post(
        "/api/v1/todos",
        headers=_auth(admin_token),
        json={"title": "任务 A", "note": "备注"},
    )
    assert r.status_code == 200
    a = r.json()["data"]

    r2 = client.post(
        "/api/v1/todos",
        headers=_auth(admin_token),
        json={"title": "任务 B"},
    )
    b = r2.json()["data"]

    r = client.post(
        "/api/v1/todos/reorder",
        headers=_auth(admin_token),
        json={"status": "pending", "ordered_ids": [b["id"], a["id"]]},
    )
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["data"]]
    assert ids == [b["id"], a["id"]]

    r = client.patch(
        f"/api/v1/todos/{a['id']}",
        headers=_auth(admin_token),
        json={"status": "done"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "done"

    r = client.get("/api/v1/todos?status=pending", headers=_auth(admin_token))
    pending = r.json()["data"]
    assert len(pending) == 1
    assert pending[0]["title"] == "任务 B"

    r = client.delete(f"/api/v1/todos/{b['id']}", headers=_auth(admin_token))
    assert r.status_code == 200


def test_todos_require_auth(client):
    assert client.get("/api/v1/todos").status_code == 401
