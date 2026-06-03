"""显式分享：可查询及以上镜像到接收者个人库，可见档不进 KnowFlow。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.permissions import PermissionLevel
from app.models.document import Document


def test_has_explicit_user_query_share_requires_query_level():
    from app.core.document_scope import has_explicit_user_query_share

    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = Document(id=uuid.uuid4(), owner_id=uuid.uuid4())
    perm_query = MagicMock(level=PermissionLevel.query.value, expires_at=None)
    perm_visible = MagicMock(level=PermissionLevel.visible.value, expires_at=None)

    with patch.object(db, "scalars") as scalars:
        scalars.return_value.all.side_effect = [[perm_visible], [perm_query]]
        assert not has_explicit_user_query_share(db, user, doc)
        assert has_explicit_user_query_share(db, user, doc)


def test_should_mirror_only_for_explicit_query_share():
    from app.services.ragflow_sync_service import _should_mirror_shared_document

    db = MagicMock()
    owner_id = uuid.uuid4()
    user = MagicMock(id=uuid.uuid4())
    doc = MagicMock(owner_id=owner_id)

    with patch(
        "app.services.ragflow_sync_service.can_access_document",
        return_value=True,
    ), patch(
        "app.services.ragflow_sync_service.has_explicit_user_query_share",
        return_value=False,
    ):
        assert not _should_mirror_shared_document(db, user, doc)

    with patch(
        "app.services.ragflow_sync_service.can_access_document",
        return_value=False,
    ):
        assert not _should_mirror_shared_document(db, user, doc)

    with patch(
        "app.services.ragflow_sync_service.can_access_document",
        return_value=True,
    ), patch(
        "app.services.ragflow_sync_service.has_explicit_user_query_share",
        return_value=True,
    ):
        assert _should_mirror_shared_document(db, user, doc)


def test_sync_document_kb_grants_personal_uses_mirrors_not_whole_kb_grant():
    db = MagicMock()
    doc = MagicMock(id=uuid.uuid4(), owner_id=uuid.uuid4())
    owner = MagicMock(id=doc.owner_id)
    link = MagicMock(dataset_id="ds-owner")

    with patch(
        "app.services.ragflow_scope_service._document_scope",
        return_value="personal",
    ), patch.object(db, "scalar", return_value=link), patch.object(
        db, "get", return_value=owner
    ), patch(
        "app.services.ragflow_scope_service.kb_level_for_user_on_document",
        return_value="admin",
    ), patch(
        "app.services.ragflow_scope_service._ragflow_user_id",
        return_value="rag-owner",
    ), patch(
        "app.services.ragflow_scope_service.grant_kb_user_permission",
        return_value=True,
    ), patch(
        "app.services.ragflow_scope_service._revoke_explicit_share_kb_grants_on_canonical",
        return_value=1,
    ) as revoke, patch(
        "app.services.ragflow_sync_service.sync_document_mirrors_for_shares",
        return_value=2,
    ) as mirrors:
        from app.services.ragflow_scope_service import sync_document_kb_grants

        count = sync_document_kb_grants(db, doc)

    assert count == 4
    revoke.assert_called_once_with(db, doc, "ds-owner")
    mirrors.assert_called_once_with(db, doc)
