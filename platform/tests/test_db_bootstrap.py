from unittest.mock import MagicMock, patch

from app.db_bootstrap import resolve_bootstrap_mode


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
