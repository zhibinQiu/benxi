"""单账号单会话：新登录顶掉旧 token。"""


def test_login_replaces_previous_session(client):
    login_a = client.post(
        "/api/v1/auth/login",
        json={"account": "admin", "password": "admin123"},
    )
    assert login_a.status_code == 200, login_a.text
    token_a = login_a.json()["data"]["access_token"]

    me_a = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert me_a.status_code == 200, me_a.text

    login_b = client.post(
        "/api/v1/auth/login",
        json={"account": "admin", "password": "admin123"},
    )
    assert login_b.status_code == 200, login_b.text
    token_b = login_b.json()["data"]["access_token"]
    assert token_b != token_a

    me_old = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert me_old.status_code == 401, me_old.text
    body = me_old.json()
    assert body.get("reason") == "session_replaced"

    me_new = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert me_new.status_code == 200, me_new.text
