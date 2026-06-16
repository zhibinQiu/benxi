"""资讯导入与首版上传：避免 current_version_id 被外层 commit 覆盖。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch


def test_create_initial_uploaded_version_flushes_without_commit():
    from app.services.documents.crud import create_initial_uploaded_version

    document = MagicMock(id=uuid.uuid4())
    user = MagicMock(id=uuid.uuid4())
    version = MagicMock(id=uuid.uuid4())
    db = MagicMock()
    store = MagicMock()
    store.build_file_key.return_value = "docs/x/v1/a.pdf"

    with patch("app.services.documents.crud.get_object_store", return_value=store), patch(
        "app.services.documents.crud.DocumentVersion",
        return_value=version,
    ):
        create_initial_uploaded_version(
            db,
            document,
            user,
            file_name="a.pdf",
            mime_type="application/pdf",
            content=b"%PDF-1.4",
            schedule_post_upload=False,
        )

    db.commit.assert_not_called()
    assert db.flush.call_count >= 2
    assert document.current_version_id == version.id


def test_subscription_import_uses_resolve_current_version():
    import inspect

    from app.services import subscription_import_service as svc

    source = inspect.getsource(svc.run_subscription_import_job)
    assert "resolve_current_version" in source
    assert "repair=True" in source
