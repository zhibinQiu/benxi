"""文档同步与越权过滤（单元测试）。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.ragflow_naming import dataset_name_for_dept


def test_dataset_name_for_dept_unique():
    a = dataset_name_for_dept(uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    b = dataset_name_for_dept(uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    assert a != b
    assert a.startswith("zt-dept-")


def test_allowed_ragflow_doc_map_empty_when_knowflow_disabled():
    from app.services.ragflow_sync_service import allowed_ragflow_doc_map

    db = MagicMock()
    user = MagicMock()
    with patch("app.config.get_settings") as gs:
        gs.return_value.knowflow_enabled = False
        assert allowed_ragflow_doc_map(db, user, ["00000000-0000-0000-0000-000000000001"]) == {}
