"""RAGFlow SSO 开通（mock HTTP）。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.ragflow_provision import provision_and_login
from app.models.org import User
from app.models.ragflow_link import RagflowAccountLink


@pytest.fixture
def platform_user():
    return User(
        id=uuid.uuid4(),
        username="tester",
        email="tester@corp.com",
        password_hash="x",
        display_name="测试",
    )


def test_provision_and_login_sets_token(platform_user):
    link = RagflowAccountLink(
        platform_user_id=platform_user.id,
        ragflow_email="tester@corp.com",
        ragflow_password="secret-pass",
    )
    mock_resp_reg = MagicMock(status_code=200)
    mock_resp_reg.json.return_value = {
        "code": 0,
        "data": {"access_token": "jwt-from-register"},
    }
    mock_resp_login = MagicMock(status_code=200)
    mock_resp_login.headers = {"Authorization": "jwt-token-abc"}
    mock_resp_login.json.return_value = {"code": 0, "data": {}}
    mock_resp_info = MagicMock(status_code=200)
    mock_resp_info.json.return_value = {"code": 0, "data": {"id": "rag-user-1"}}

    with patch("app.integrations.ragflow_provision.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.side_effect = [mock_resp_login, mock_resp_reg]
        client.get.return_value = mock_resp_info
        token = provision_and_login(link, platform_user)

    assert token == "jwt-token-abc"
    assert link.ragflow_access_token == "jwt-token-abc"
    assert link.ragflow_user_id == "rag-user-1"
