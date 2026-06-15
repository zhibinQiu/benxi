"""RAGFlow HTTP 熔断与 DB 连接池行为。"""

from __future__ import annotations

import pytest
from unittest.mock import patch

import httpx

from app.integrations.ragflow_http import (
    mark_ragflow_http_failure,
    mark_ragflow_http_success,
    ragflow_http_timeout,
    reset_ragflow_http_circuit_for_tests,
    should_attempt_ragflow_http,
)


@pytest.fixture(autouse=True)
def _reset_ragflow_circuit():
    from app.integrations.ragflow_http import reset_ragflow_http_circuit_for_tests

    reset_ragflow_http_circuit_for_tests()
    yield
    reset_ragflow_http_circuit_for_tests()


def test_ragflow_http_circuit_opens_after_failure():
    reset_ragflow_http_circuit_for_tests()
    assert should_attempt_ragflow_http() is True
    mark_ragflow_http_failure()
    assert should_attempt_ragflow_http() is False
    mark_ragflow_http_success()
    assert should_attempt_ragflow_http() is True


def test_ragflow_http_timeout_shorter_for_remote_deps():
    reset_ragflow_http_circuit_for_tests()
    with patch("app.integrations.ragflow_http.get_settings") as gs:
        gs.return_value.ragflow_http_timeout = 0
        gs.return_value.remote_deps = True
        assert ragflow_http_timeout() == 12.0
        gs.return_value.remote_deps = False
        assert ragflow_http_timeout() == 30.0


def test_get_user_ragflow_auth_skips_during_cooldown():
    import uuid
    from unittest.mock import MagicMock

    from app.models.org import User
    from app.models.ragflow_link import RagflowAccountLink
    from app.services.ragflow_identity_service import get_user_ragflow_auth

    reset_ragflow_http_circuit_for_tests()
    mark_ragflow_http_failure()

    user = User(
        id=uuid.uuid4(),
        username="eve",
        email="eve@corp.com",
        password_hash="x",
        display_name="Eve",
    )
    link = RagflowAccountLink(
        platform_user_id=user.id,
        ragflow_email="eve@platform.local",
    )
    db = MagicMock()

    with patch("app.services.ragflow_identity_service.get_settings") as gs, patch(
        "app.services.ragflow_identity_service.get_or_create_link",
        return_value=link,
    ), patch(
        "app.services.ragflow_identity_service.provision_and_login",
    ) as provision:
        gs.return_value.knowflow_enabled = True
        assert get_user_ragflow_auth(db, user) is None
        provision.assert_not_called()


def test_get_user_ragflow_auth_marks_failure_on_connect_error():
    import uuid
    from unittest.mock import MagicMock

    from app.models.org import User
    from app.models.ragflow_link import RagflowAccountLink
    from app.services.ragflow_identity_service import get_user_ragflow_auth

    reset_ragflow_http_circuit_for_tests()

    user = User(
        id=uuid.uuid4(),
        username="dave",
        email="dave@corp.com",
        password_hash="x",
        display_name="Dave",
    )
    link = RagflowAccountLink(
        platform_user_id=user.id,
        ragflow_email="dave@platform.local",
    )
    db = MagicMock()

    with patch("app.services.ragflow_identity_service.get_settings") as gs, patch(
        "app.services.ragflow_identity_service.get_or_create_link",
        return_value=link,
    ), patch(
        "app.services.ragflow_identity_service._ragflow_auth_valid",
        return_value=False,
    ), patch(
        "app.services.ragflow_identity_service.provision_and_login",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        gs.return_value.knowflow_enabled = True
        assert get_user_ragflow_auth(db, user) is None
    assert should_attempt_ragflow_http() is False


def test_hybrid_remote_dev_uses_full_db_pool():
    from app.database import _engine_kwargs

    class S:
        remote_deps = True
        database_url = "postgresql+psycopg2://platform:platform@127.0.0.1:5432/platform"
        db_pool_size = 20
        db_max_overflow = 40
        db_pool_timeout = 30
        db_pool_recycle = 1800
        db_connect_timeout = 10
        debug_sql = False

    kw = _engine_kwargs(S())
    assert kw["pool_size"] == 20
    assert kw["max_overflow"] == 40
    assert kw["connect_args"]["connect_timeout"] == 10


def test_remote_dev_remote_db_respects_pool_settings():
    from app.database import _engine_kwargs

    class S:
        remote_deps = True
        database_url = "postgresql+psycopg2://platform:platform@172.19.134.45:40002/platform"
        db_pool_size = 12
        db_max_overflow = 18
        db_pool_timeout = 30
        db_pool_recycle = 1800
        db_connect_timeout = 10
        debug_sql = False

    kw = _engine_kwargs(S())
    assert kw["pool_size"] == 12
    assert kw["max_overflow"] == 18
    assert kw["connect_args"]["connect_timeout"] == 25
