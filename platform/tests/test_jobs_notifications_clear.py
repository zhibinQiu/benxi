"""任务与消息清理 API。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.services.job_service import cancel_job, create_job


def _bootstrap_user(db):
    return db.scalar(select(User).where(User.phone == bootstrap_login_id()))


def test_clear_jobs_endpoint(client, admin_token):
    r = client.delete(
        "/api/v1/jobs/clear?scope=finished",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["scope"] == "finished"
    assert "deleted" in data


def test_batch_delete_jobs_endpoint(client, admin_token):
    import uuid

    from app.models.job import JobStatus

    db = SessionLocal()
    try:
        admin = _bootstrap_user(db)
        assert admin is not None
        job = create_job(
            db,
            job_type="maintenance",
            created_by=admin.id,
        )
        job.status = JobStatus.done.value
        db.commit()
        job_id = str(job.id)
    finally:
        db.close()

    r = client.post(
        "/api/v1/jobs/batch-delete",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"job_ids": [job_id]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"] == 1


def test_cancel_job_endpoint(client, admin_token):
    db = SessionLocal()
    try:
        admin = _bootstrap_user(db)
        assert admin is not None
        job = create_job(db, job_type="maintenance", created_by=admin.id)
        job_id = str(job.id)
    finally:
        db.close()

    r = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "cancelled"
    assert "终止" in (r.json()["data"]["error_message"] or "")

    r2 = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r2.status_code == 400


def test_cancel_job_service():
    db = SessionLocal()
    try:
        admin = _bootstrap_user(db)
        job = create_job(db, job_type="maintenance", created_by=admin.id)
        out = cancel_job(db, job)
        assert out.status == "cancelled"
    finally:
        db.close()


def test_clear_notifications_endpoint(client, admin_token):
    r = client.patch(
        "/api/v1/notifications/read-all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    r = client.delete(
        "/api/v1/notifications/clear?scope=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    assert "deleted" in r.json()["data"]
