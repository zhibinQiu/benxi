"""RAGFlow HTTP client (KnowFlow 知识库底层)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class RagflowError(RuntimeError):
    pass


def _extract_uploaded_doc(data: Any) -> dict:
    """解析 RAGFlow /v1/document/upload 多种返回结构。"""
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first
    if isinstance(data, dict):
        if isinstance(data.get("document"), dict):
            return data["document"]
        if isinstance(data.get("doc"), dict):
            return data["doc"]
        if data.get("id") or data.get("doc_id"):
            return data
        nested = data.get("data")
        if isinstance(nested, dict):
            return _extract_uploaded_doc(nested)
        if isinstance(nested, list):
            return _extract_uploaded_doc(nested)
    raise RagflowError(f"上传文档返回为空或无法解析: {data!r}")


class RagflowClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session_auth: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ragflow_api_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.ragflow_api_key
        self.session_auth = session_auth
        self.timeout = timeout

    @property
    def _use_session_api(self) -> bool:
        return bool(self.session_auth and not self.api_key)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.session_auth:
            # RAGFlow Web 登录 JWT（无 Bearer 前缀）
            h["Authorization"] = self.session_auth
        elif self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._headers()
        if files:
            headers = {"Authorization": headers.get("Authorization", "")}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.request(
                    method,
                    url,
                    headers=headers,
                    json=json if not files else None,
                    files=files,
                    data=data,
                )
        except httpx.HTTPError as e:
            raise RagflowError(f"无法连接 RAGFlow ({self.base_url}): {e}") from e
        if r.status_code >= 400:
            raise RagflowError(f"RAGFlow HTTP {r.status_code}: {r.text[:500]}")
        body = r.json()
        if isinstance(body, dict) and body.get("code", 0) != 0:
            raise RagflowError(body.get("message") or str(body))
        return body.get("data") if isinstance(body, dict) and "data" in body else body

    def health_ok(self) -> bool:
        """经 nginx 反代时 /v1/system/healthz 可能 500，改用 config 探测。"""
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/v1/system/config")
                if r.status_code != 200:
                    return False
                body = r.json()
                return isinstance(body, dict) and body.get("code") == 0
        except Exception:
            return False

    def list_datasets(self, *, name: str | None = None) -> list[dict]:
        if self._use_session_api:
            data = self._request("POST", "/v1/kb/list", json={})
            kbs = data.get("kbs", []) if isinstance(data, dict) else []
            out = [{"id": k.get("id"), "name": k.get("name")} for k in kbs if k.get("id")]
            if name:
                out = [k for k in out if k.get("name") == name]
            return out
        params = ""
        if name:
            params = f"?name={name}"
        data = self._request("GET", f"/api/v1/datasets{params}")
        if isinstance(data, list):
            return data
        return data.get("items", []) if isinstance(data, dict) else []

    def create_dataset(self, name: str, *, description: str = "", permission: str = "me") -> dict:
        if self._use_session_api:
            data = self._request(
                "POST",
                "/v1/kb/create",
                json={
                    "name": name,
                    "description": description or name,
                    "parser_id": "naive",
                },
            )
            kb_id = data.get("kb_id") if isinstance(data, dict) else None
            return {"id": kb_id} if kb_id else {}
        payload = {
            "name": name,
            "description": description or name,
            "permission": permission,
            "chunk_method": "naive",
        }
        return self._request("POST", "/api/v1/datasets", json=payload)

    def ensure_dataset(self, name: str) -> str:
        for ds in self.list_datasets(name=name):
            if ds.get("name") == name:
                return str(ds["id"])
        created = self.create_dataset(name)
        kid = created.get("id") or created.get("kb_id")
        if kid:
            return str(kid)
        raise RagflowError(f"创建知识库失败: {created!r}")

    def update_dataset_name(self, dataset_id: str, name: str) -> None:
        """将知识库名称改为展示名（兼容旧 zt-* 技术名）。"""
        if not dataset_id or not name:
            return
        if self._use_session_api:
            try:
                self._request(
                    "POST",
                    "/v1/kb/update",
                    json={"kb_id": dataset_id, "name": name},
                )
                return
            except RagflowError as e:
                logger.debug("KnowFlow kb/update 改名跳过: %s", e)
        self._request(
            "PUT",
            f"/api/v1/datasets/{dataset_id}",
            json={"name": name},
        )

    def find_dataset_by_names(self, names: list[str]) -> dict | None:
        seen: set[str] = set()
        for name in names:
            n = (name or "").strip()
            if not n or n in seen:
                continue
            seen.add(n)
            for ds in self.list_datasets(name=n):
                if ds.get("name") == n and ds.get("id"):
                    return ds
        return None

    def get_dataset_name(self, dataset_id: str) -> str | None:
        for ds in self.list_datasets():
            if str(ds.get("id")) == str(dataset_id):
                return (ds.get("name") or "").strip() or None
        return None

    def upload_document(
        self,
        dataset_id: str,
        *,
        file_name: str,
        content: bytes,
        meta_fields: dict | None = None,
    ) -> dict:
        if self._use_session_api:
            files = {"file": (file_name, content)}
            form = {"kb_id": dataset_id}
            data = self._request(
                "POST",
                "/v1/document/upload",
                files=files,
                data=form,
            )
            doc = _extract_uploaded_doc(data)
            doc_id = doc.get("id") or doc.get("doc_id")
            if doc_id:
                self.parse_documents(dataset_id, [str(doc_id)])
            return doc
        files = {"file": (file_name, content)}
        data = self._request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/documents",
            files=files,
        )
        doc = _extract_uploaded_doc(data)
        doc_id = doc.get("id") or doc.get("doc_id")
        if doc_id and meta_fields:
            self._request(
                "PUT",
                f"/api/v1/datasets/{dataset_id}/documents/{doc_id}",
                json={"meta_fields": meta_fields},
            )
        if doc_id:
            self.parse_documents(dataset_id, [str(doc_id)])
        return doc

    def delete_documents(self, dataset_id: str, document_ids: list[str]) -> None:
        """从知识库删除指定文档（body 必须为 ids 字段）。"""
        ids = [str(i).strip() for i in document_ids if str(i).strip()]
        if not ids:
            return
        if self._use_session_api:
            self._request(
                "POST",
                "/v1/document/rm",
                json={"doc_id": ids},
            )
            return
        self._request(
            "DELETE",
            f"/api/v1/datasets/{dataset_id}/documents",
            json={"ids": ids},
        )

    def parse_documents(self, dataset_id: str, document_ids: list[str]) -> None:
        if self._use_session_api:
            self._request(
                "POST",
                "/v1/document/run",
                json={"doc_ids": document_ids, "run": "1", "delete": False},
            )
            return
        self._request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/chunks",
            json={"document_ids": document_ids},
        )

    def retrieval(
        self,
        *,
        question: str,
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> list[dict]:
        payload: dict[str, Any] = {
            "question": question,
            "dataset_ids": dataset_ids,
            "top_k": top_k,
            "keyword": True,
            "highlight": True,
        }
        if document_ids:
            payload["document_ids"] = document_ids
        data = self._request("POST", "/api/v1/retrieval", json=payload)
        if not data:
            return []
        chunks = data.get("chunks") if isinstance(data, dict) else data
        if not isinstance(chunks, list):
            return []
        hits: list[dict] = []
        for ch in chunks:
            content = ch.get("content") or ch.get("content_with_weight") or ""
            doc_id = ch.get("document_id") or ch.get("doc_id")
            meta = ch.get("meta_fields") or {}
            hits.append(
                {
                    "snippet": content,
                    "score": ch.get("similarity") or ch.get("score") or 0,
                    "document_id": meta.get("platform_document_id") or doc_id,
                    "ragflow_document_id": doc_id,
                    "anchor_json": {
                        "page": ch.get("page_num") or ch.get("page"),
                        "bbox": ch.get("bbox"),
                    },
                }
            )
        return hits
