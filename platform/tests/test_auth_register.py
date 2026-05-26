def test_register_creates_member_user(client, db):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "newuser1", "password": "secret12"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data.get("access_token")

    from sqlalchemy import select

    from app.models.org import Role, User, UserRole

    user = db.scalar(select(User).where(User.username == "newuser1"))
    assert user is not None
    member = db.scalar(select(Role).where(Role.code == "member"))
    assert member is not None
    link = db.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == member.id)
    )
    assert link is not None
    admin_link = db.scalar(
        select(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, Role.code == "sys_admin")
    )
    assert admin_link is None


def test_register_rejects_duplicate_username(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "dupuser", "password": "secret12"},
    )
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "dupuser", "password": "secret12"},
    )
    assert r.status_code == 400
