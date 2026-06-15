"""KnowFlow 引用截图（源 PDF 切片快照）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.integrations.ragflow_client import RagflowClient
from app.services.knowledge_qa_service import resolve_citation_image_id


def test_extract_chunk_image_id_prefers_img_id():
    assert RagflowClient.extract_chunk_image_id({"img_id": "kb-abc"}) == "kb-abc"
    assert RagflowClient.extract_chunk_image_id({"image_id": "kb-xyz"}) == "kb-xyz"
    assert RagflowClient.extract_chunk_image_id({"image_id": "", "img_id": "kb-1"}) == "kb-1"


def test_synthesize_chunk_image_id_falls_back_to_dataset_chunk():
    chunk = {"chunk_id": "abc123", "image_id": "", "kb_id": "ds-1"}
    assert RagflowClient.synthesize_chunk_image_id(chunk) == "ds-1-abc123"


def test_retrieval_maps_img_id_to_image_id():
    client = RagflowClient(api_key="test-key")
    payload = {
        "chunks": [
            {
                "id": "chunk-1",
                "content": "片段",
                "highlight": "<em>片段</em>",
                "document_id": "doc-1",
                "kb_id": "ds-1",
                "img_id": "kb_id-snapshot.jpg",
                "positions": [[2, 10, 20, 30, 40]],
                "similarity": 0.9,
            }
        ]
    }
    with patch.object(client, "_request", return_value=payload):
        hits = client.retrieval(question="q", dataset_ids=["ds-1"])
    assert len(hits) == 1
    assert hits[0]["image_id"] == "kb_id-snapshot.jpg"
    assert hits[0]["preview_available"] is True
    assert hits[0]["anchor_json"]["page"] == 2
    assert hits[0]["anchor_json"]["bbox"] == [10.0, 20.0, 30.0, 40.0]


def test_retrieval_session_uses_retrieval_test_and_maps_image_id():
    client = RagflowClient(session_auth="jwt-token")
    payload = {
        "chunks": [
            {
                "chunk_id": "chunk-1",
                "content_with_weight": "体检通知",
                "doc_id": "doc-1",
                "kb_id": "ds-1",
                "image_id": "ds-1-snapshot",
                "positions": [[1, 5, 6, 7, 8]],
                "similarity": 0.85,
            }
        ]
    }

    with patch.object(client, "_request", return_value=payload) as mock_req:
        hits = client.retrieval(
            question="体检",
            dataset_ids=["ds-1"],
            document_ids=["doc-1"],
        )

    mock_req.assert_called_once()
    assert mock_req.call_args[0] == ("POST", "/v1/chunk/retrieval_test")
    body = mock_req.call_args.kwargs["json"]
    assert body["kb_id"] == "ds-1"
    assert body["doc_ids"] == ["doc-1"]
    assert body["highlight"] is True
    assert len(hits) == 1
    assert hits[0]["chunk_id"] == "chunk-1"
    assert hits[0]["image_id"] == "ds-1-snapshot"
    assert hits[0]["preview_available"] is True
    assert hits[0]["ragflow_document_id"] == "doc-1"
    assert hits[0]["dataset_id"] == "ds-1"


def test_get_chunk_image_tries_v1_document_image_first():
    client = RagflowClient(session_auth="jwt-token")
    response = httpx.Response(200, content=b"jpeg-bytes", headers={"content-type": "image/jpeg"})

    with patch("httpx.Client") as client_cls:
        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = response
        client_cls.return_value = mock_http

        data, content_type = client.get_chunk_image("kb-abc")

    assert data == b"jpeg-bytes"
    assert content_type == "image/jpeg"
    called_url = mock_http.get.call_args[0][0]
    assert called_url.endswith("/v1/document/image/kb-abc")


def test_get_chunk_image_rejects_json_error_body():
    client = RagflowClient(session_auth="jwt-token")
    response = httpx.Response(
        200,
        content=b'{"code":100,"message":"no image"}',
        headers={"content-type": "application/json"},
    )

    with patch("httpx.Client") as client_cls:
        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = response
        client_cls.return_value = mock_http

        try:
            client.get_chunk_image("kb-abc")
            assert False, "expected RagflowError"
        except Exception as exc:
            assert "引用截图" in str(exc)


def test_retrieval_plain_text_chunk_has_no_preview():
    client = RagflowClient(api_key="test-key")
    payload = {
        "chunks": [
            {
                "id": "chunk-plain",
                "content": "纯文本分块无页级坐标",
                "document_id": "doc-1",
                "kb_id": "ds-1",
                "similarity": 0.7,
            }
        ]
    }
    with patch.object(client, "_request", return_value=payload):
        hits = client.retrieval(question="纯文本", dataset_ids=["ds-1"])
    assert len(hits) == 1
    assert hits[0]["image_id"] is None
    assert hits[0]["preview_available"] is False


def test_retrieval_bbox_only_preview_without_image_id():
    client = RagflowClient(api_key="test-key")
    payload = {
        "chunks": [
            {
                "id": "chunk-bbox",
                "content": "有坐标无 image_id",
                "document_id": "doc-1",
                "kb_id": "ds-1",
                "positions": [[1, 0.1, 0.2, 0.3, 0.4]],
                "similarity": 0.8,
            }
        ]
    }
    with patch.object(client, "_request", return_value=payload):
        hits = client.retrieval(question="坐标", dataset_ids=["ds-1"])
    assert hits[0]["image_id"] is None
    assert hits[0]["preview_available"] is True
    assert hits[0]["anchor_json"]["bbox"] == [0.1, 0.2, 0.3, 0.4]


def test_resolve_citation_image_id_from_chunk():
    user = MagicMock()
    db = MagicMock()
    rag = MagicMock()
    rag.health_ok.return_value = True
    rag.resolve_chunk_image_id.return_value = "kb-resolved"

    with patch(
        "app.services.knowledge_qa_service._rag_clients_for_qa",
        return_value=[rag],
    ):
        out = resolve_citation_image_id(
            db,
            user,
            chunk_id="c1",
            dataset_id="ds1",
            ragflow_document_id="rd1",
        )
    assert out == "kb-resolved"
