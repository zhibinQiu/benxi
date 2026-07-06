from unittest.mock import MagicMock, patch

from app.db_bootstrap import bootstrap_database, resolve_bootstrap_mode


def test_resolve_bootstrap_mode_auto_light_when_schema_current():
    with patch("app.db_bootstrap.is_platform_schema_current", return_value=True):
        assert resolve_bootstrap_mode(MagicMock()) == "light"


def test_resolve_bootstrap_mode_auto_full_when_schema_stale():
    with patch("app.db_bootstrap.is_platform_schema_current", return_value=False):
        assert resolve_bootstrap_mode(MagicMock()) == "full"


def test_resolve_bootstrap_mode_explicit_override():
    with patch("app.db_bootstrap.get_settings") as gs:
        gs.return_value.db_startup_bootstrap = "off"
        assert resolve_bootstrap_mode(MagicMock()) == "off"


def test_bootstrap_database_skips_when_lock_not_acquired():
    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"
    mock_conn = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_conn.execute.return_value.scalar.side_effect = [False, None, None]

    with (
        patch("app.db_bootstrap.resolve_bootstrap_mode", return_value="light") as resolve,
        patch("app.db_bootstrap._run_bootstrap") as run,
        patch("app.db_bootstrap._wait_for_bootstrap_lock") as wait_lock,
    ):
        mode = bootstrap_database(mock_engine)

    assert mode == "light"
    run.assert_not_called()
    wait_lock.assert_called_once_with(mock_engine)
    mock_conn.close.assert_called_once()
    assert resolve.call_count == 2


def test_bootstrap_database_runs_when_lock_acquired():
    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"
    mock_conn = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_conn.execute.return_value.scalar.return_value = True

    with (
        patch("app.db_bootstrap.resolve_bootstrap_mode", return_value="light"),
        patch("app.db_bootstrap._run_bootstrap", return_value="light") as run,
        patch("app.db_bootstrap._wait_for_bootstrap_lock") as wait_lock,
    ):
        mode = bootstrap_database(mock_engine)

    assert mode == "light"
    run.assert_called_once_with(mock_engine, "light")
    wait_lock.assert_not_called()
    mock_conn.close.assert_called_once()
