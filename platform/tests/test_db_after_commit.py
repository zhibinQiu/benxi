"""事务提交后再调度后台任务。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.db_after_commit import run_after_commit


def test_run_after_commit_queues_callback():
    db = MagicMock()
    db.info = {}
    callbacks = []

    with patch("app.core.db_after_commit.event.listens_for"):
        run_after_commit(db, lambda: callbacks.append(True))
        run_after_commit(db, lambda: callbacks.append(True))

    assert len(db.info["after_commit_callbacks"]) == 2
    assert callbacks == []
    for fn in db.info["after_commit_callbacks"]:
        fn()
    assert callbacks == [True, True]
