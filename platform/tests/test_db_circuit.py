"""数据库熔断与读库路由测试。"""

from __future__ import annotations

import pytest

from app.core.db_circuit import (
    DbCircuitOpenError,
    guard_db_circuit,
    mark_db_failure,
    mark_db_success,
    reset_db_circuit_for_tests,
    should_attempt_db,
)


@pytest.fixture(autouse=True)
def _reset_circuit():
    reset_db_circuit_for_tests()
    yield
    reset_db_circuit_for_tests()


def test_db_circuit_opens_after_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.core.db_circuit.get_settings",
        lambda: type(
            "S",
            (),
            {
                "db_circuit_enabled": True,
                "db_circuit_failure_threshold": 3,
                "db_circuit_cooldown_sec": 10,
            },
        )(),
    )
    reset_db_circuit_for_tests()
    assert should_attempt_db() is True
    mark_db_failure()
    mark_db_failure()
    assert should_attempt_db() is True
    mark_db_failure()
    assert should_attempt_db() is False
    with pytest.raises(DbCircuitOpenError):
        guard_db_circuit()


def test_db_circuit_resets_on_success(monkeypatch):
    monkeypatch.setattr(
        "app.core.db_circuit.get_settings",
        lambda: type(
            "S",
            (),
            {
                "db_circuit_enabled": True,
                "db_circuit_failure_threshold": 2,
                "db_circuit_cooldown_sec": 10,
            },
        )(),
    )
    reset_db_circuit_for_tests()
    mark_db_failure()
    mark_db_failure()
    assert should_attempt_db() is False
    mark_db_success()
    assert should_attempt_db() is True
    guard_db_circuit()


def test_read_session_factory_falls_back_to_primary(monkeypatch):
    monkeypatch.setattr(
        "app.core.db_circuit.get_settings",
        lambda: type("S", (), {"database_read_url": ""})(),
    )
    import app.database as db_mod

    db_mod._read_engine = None
    db_mod.ReadSessionLocal = None
    assert db_mod.read_session_factory() is db_mod.SessionLocal
