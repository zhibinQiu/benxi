"""无需 RAGFLOW_API_KEY 时 KnowFlow 客户端逻辑。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.integrations.knowflow_client import get_knowflow_client


def test_user_session_enables_client_without_admin_api_key():
    with patch("app.integrations.knowflow_client.get_settings") as gs:
        s = MagicMock()
        s.knowflow_enabled = True
        s.ragflow_api_key = ""
        s.ragflow_api_url = "http://127.0.0.1:9380"
        gs.return_value = s
        with patch(
            "app.integrations.knowflow_client.knowflow_stack_reachable",
            return_value=True,
        ):
            kf = get_knowflow_client(ragflow_auth="jwt-from-platform-sso")
    assert kf.enabled() is True
