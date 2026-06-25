"""定时通知调度 — 无 Celery Worker 时仍应触发进程内 Timer。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.services import background_job_dispatch as dispatch_mod


def test_dispatch_scheduled_notification_uses_celery_when_available(monkeypatch):
    timer_calls: list[tuple[float, object]] = []
    inprocess_calls: list[uuid.UUID] = []

    class FakeTimer:
        def __init__(self, delay, fn):
            timer_calls.append((delay, fn))

        def start(self):
            return None

    monkeypatch.setattr(dispatch_mod.threading, "Timer", FakeTimer)
    monkeypatch.setattr(
        dispatch_mod,
        "_dispatch_scheduled_notification_inprocess",
        lambda nid: inprocess_calls.append(nid),
    )
    monkeypatch.setattr(dispatch_mod, "_try_celery", lambda *a, **k: True)

    nid = uuid.uuid4()
    dispatch_mod.dispatch_scheduled_notification(nid, countdown=60)

    assert timer_calls == []
    assert inprocess_calls == []


def test_dispatch_scheduled_notification_falls_back_to_timer(monkeypatch):
    timer_calls: list[tuple[float, object]] = []
    inprocess_calls: list[uuid.UUID] = []

    class FakeTimer:
        def __init__(self, delay, fn):
            timer_calls.append((delay, fn))

        def start(self):
            return None

    monkeypatch.setattr(dispatch_mod.threading, "Timer", FakeTimer)
    monkeypatch.setattr(
        dispatch_mod,
        "_dispatch_scheduled_notification_inprocess",
        lambda nid: inprocess_calls.append(nid),
    )
    monkeypatch.setattr(dispatch_mod, "_try_celery", MagicMock(return_value=False))

    nid = uuid.uuid4()
    dispatch_mod.dispatch_scheduled_notification(nid, countdown=60)

    assert len(timer_calls) == 1
    assert timer_calls[0][0] == 60
    timer_calls[0][1]()
    assert inprocess_calls == [nid]


def test_dispatch_scheduled_notification_immediate_inprocess(monkeypatch):
    inprocess_calls: list[uuid.UUID] = []
    monkeypatch.setattr(
        dispatch_mod,
        "_dispatch_scheduled_notification_inprocess",
        lambda nid: inprocess_calls.append(nid),
    )
    monkeypatch.setattr(dispatch_mod, "_try_celery", MagicMock(return_value=False))

    nid = uuid.uuid4()
    dispatch_mod.dispatch_scheduled_notification(nid, countdown=0)

    assert inprocess_calls == [nid]
