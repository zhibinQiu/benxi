"""本析智能文档管理工具。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent_document_service import (
    delete_document_for_agent,
    list_library_documents_for_agent,
    list_manageable_documents,
    rename_document_for_agent,
    share_document_for_agent,
)
from app.services.agent_tools import agent_tool_names, build_agent_tool_specs, tool_workflow_meta


def test_document_tools_registered():
    names = agent_tool_names()
    assert "list_library_documents" in names
    assert "list_manageable_documents" in names
    assert "rename_document" in names
    assert "move_document" in names
    assert "share_document" in names
    assert "delete_document" in names


def test_build_agent_tool_specs_includes_document_tools():
    db = MagicMock()
    user = MagicMock()
    specs = build_agent_tool_specs(db, user)
    tool_names = {s["function"]["name"] for s in specs}
    assert "rename_document" in tool_names


def test_rename_document_workflow_meta():
    meta = tool_workflow_meta(
        "rename_document",
        '{"document_id": "00000000-0000-0000-0000-000000000001", "new_title": "新标题"}',
    )
    assert meta["tool"] == "document.rename"
    assert "重命名" in meta["title"]


@patch("app.services.agent_document_service.filter_accessible_documents")
@patch("app.services.agent_document_service.ensure_web_favorites_folder")
def test_list_library_documents_web_favorites_folder(mock_ensure_folder, mock_filter):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    folder_id = uuid.uuid4()
    mock_ensure_folder.return_value = MagicMock(id=folder_id)
    doc = MagicMock(
        id=uuid.uuid4(),
        title="收藏文章",
        scope="personal",
        folder_id=folder_id,
    )
    mock_filter.return_value = [doc]
    rows = list_library_documents_for_agent(
        db, user, folder_name="网页收藏", limit=10
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "收藏文章"
    mock_filter.assert_called_once()
    assert mock_filter.call_args.kwargs["folder_id"] == folder_id


@patch("app.services.agent_document_service.filter_accessible_documents")
def test_list_manageable_documents(mock_filter):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = MagicMock(
        id=uuid.uuid4(),
        title="测试文档",
        scope="personal",
        folder_id=None,
    )
    mock_filter.return_value = [doc]
    with patch(
        "app.services.agent_document_service.can_grant_document_permissions",
        return_value=True,
    ):
        rows = list_manageable_documents(db, user, keyword="测试", limit=5)
    assert len(rows) == 1
    assert rows[0]["title"] == "测试文档"
    mock_filter.assert_called_once()


@patch("app.services.agent_document_service.document_service")
@patch("app.services.agent_document_service.can_modify_document", return_value=True)
def test_rename_document_for_agent(mock_can_modify, mock_svc):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc_id = uuid.uuid4()
    doc = MagicMock(id=doc_id, title="新名称", deleted_at=None)
    mock_svc.get_document.return_value = doc
    mock_svc.update_document.return_value = doc

    result = rename_document_for_agent(
        db, user, document_id=doc_id, new_title="新名称"
    )
    assert result["title"] == "新名称"
    mock_svc.update_document.assert_called_once()


def test_delete_document_requires_confirm():
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    with pytest.raises(Exception) as exc:
        delete_document_for_agent(
            db, user, document_id=uuid.uuid4(), confirm=False
        )
    assert "confirm" in str(exc.value.detail.get("message", ""))


@patch("app.services.agent_document_service.document_service")
@patch(
    "app.services.agent_document_service.can_grant_document_permissions",
    return_value=True,
)
def test_share_document_for_agent(mock_can_grant, mock_svc):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc_id = uuid.uuid4()
    target_id = uuid.uuid4()
    doc = MagicMock(id=doc_id, title="分享文档", deleted_at=None)
    mock_svc.get_document.return_value = doc
    mock_svc.list_acl_user_candidates.return_value = [
        {
            "id": target_id,
            "username": "张三",
            "display_name": "张三",
        }
    ]
    mock_svc.set_document_shares.return_value = [
        {"user_id": target_id, "user_name": "张三", "level": "query"}
    ]

    result = share_document_for_agent(
        db,
        user,
        document_id=doc_id,
        user_names=["张三"],
        level="query",
    )
    assert result["shared_with"] == ["张三"]
    mock_svc.set_document_shares.assert_called_once()
