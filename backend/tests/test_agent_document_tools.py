"""本析智能文档管理工具。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent_document_service import (
    create_kb_folder_for_agent,
    create_library_document_for_agent,
    delete_document_for_agent,
    list_library_documents_for_agent,
    list_manageable_documents,
    read_document_content_for_agent,
    rename_document_for_agent,
    search_documents_by_name_for_agent,
    share_document_for_agent,
)
from app.services.agent_tools import agent_tool_names, build_agent_tool_specs, tool_workflow_meta


def test_document_tools_registered():
    names = agent_tool_names()
    assert "search_documents_by_name" in names
    assert "read_document_content" in names
    assert "list_library_documents" in names
    assert "list_manageable_documents" in names
    assert "list_document_folders" in names
    assert "create_kb_folder" in names
    assert "create_library_document" in names
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
def test_search_documents_by_name(mock_filter):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc = MagicMock(
        id=uuid.uuid4(),
        title="采购管理制度",
        scope="company",
        folder_id=None,
    )
    mock_filter.return_value = [doc]
    with patch(
        "app.services.agent_document_service._serialize_document_summary",
        return_value={"id": str(doc.id), "title": doc.title, "scope": "company"},
    ):
        rows = search_documents_by_name_for_agent(db, user, name="采购", limit=5)
    assert len(rows) == 1
    assert rows[0]["title"] == "采购管理制度"
    mock_filter.assert_called_once()
    assert mock_filter.call_args.kwargs["keyword"] == "采购"
    assert mock_filter.call_args.kwargs["scope"] is None


@patch("app.services.pageindex_service.get_pageindex_document_content")
@patch("app.services.document_service.resolve_current_version")
@patch("app.services.document_service.get_document")
@patch("app.core.document_scope.can_read_document", return_value=True)
def test_read_document_content_for_agent(
    mock_can_read,
    mock_get_doc,
    mock_resolve_version,
    mock_get_pageindex,
):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc_id = uuid.uuid4()
    doc = MagicMock(id=doc_id, title="采购制度", deleted_at=None)
    mock_get_doc.return_value = doc
    mock_resolve_version.return_value = MagicMock()
    mock_get_pageindex.return_value = {
        "file_name": "采购制度.pdf",
        "full_text": "第一章 总则\n内容示例",
        "char_count": 12,
        "parse_quality": "pageindex",
        "warning": None,
        "source": "pageindex",
    }

    result = read_document_content_for_agent(
        db, user, document_id=doc_id, max_chars=16000
    )
    assert result["document_id"] == str(doc_id)
    assert result["title"] == "采购制度"
    assert "第一章" in result["full_text"]
    assert result["truncated"] is False
    assert result["parse_source"] == "pageindex"
    mock_get_pageindex.assert_called_once_with(db, user, doc_id)


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
        db, user, folder_name="资讯管理", limit=10
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


@patch("app.services.agent_document_service.create_kb_folder")
def test_create_kb_folder_for_agent(mock_create):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    folder_id = uuid.uuid4()
    mock_create.return_value = MagicMock(
        id=folder_id, name="项目资料", scope="personal"
    )

    result = create_kb_folder_for_agent(
        db, user, name="项目资料", scope="personal"
    )
    assert result["id"] == str(folder_id)
    assert "项目资料" in result["message"]
    db.commit.assert_called_once()


@patch("app.services.agent_document_service.document_service")
def test_create_library_document_for_agent(mock_svc):
    db = MagicMock()
    user = MagicMock(id=uuid.uuid4())
    doc_id = uuid.uuid4()
    doc = MagicMock(
        id=doc_id,
        title="会议纪要",
        scope="personal",
        folder_id=None,
    )
    mock_svc.create_document.return_value = doc

    result = create_library_document_for_agent(
        db,
        user,
        title="会议纪要",
        content="# 摘要\n内容",
        scope="personal",
    )
    assert result["id"] == str(doc_id)
    mock_svc.create_document.assert_called_once()
    mock_svc.create_initial_uploaded_version.assert_called_once()
    db.commit.assert_called_once()
