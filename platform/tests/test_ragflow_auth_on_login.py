"""登录后 RAGFlow 会话：缓存 token 也应同步模型配置。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink


def test_cached_auth_finalizes_llm_config():
    from app.services.ragflow_identity_service import get_user_ragflow_auth

    user = User(
        id=uuid.uuid4(),
        username="carol",
        email="carol@corp.com",
        password_hash="x",
        display_name="Carol",
    )
    link = RagflowAccountLink(
        platform_user_id=user.id,
        ragflow_email="carol@platform.local",
        ragflow_access_token="cached-jwt",
        ragflow_user_id="rag-u1",
    )
    db = MagicMock()

    with patch("app.services.ragflow_identity_service.get_settings") as gs, patch(
        "app.services.ragflow_identity_service.get_or_create_link",
        return_value=link,
    ), patch(
        "app.services.ragflow_identity_service._ragflow_auth_valid",
        return_value=True,
    ), patch(
        "app.integrations.ragflow_provision.finalize_ragflow_link"
    ) as finalize:
        gs.return_value.knowflow_enabled = True
        token = get_user_ragflow_auth(db, user)

    assert token == "cached-jwt"
    finalize.assert_called_once_with(link, "cached-jwt", user)
    db.flush.assert_called()
