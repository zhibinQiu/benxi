"""KnowFlow / RAGFlow 集成客户端。"""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from app.config import get_settings
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.integrations.text_extract import ParsedDocument, local_search
from app.services.ragflow_naming import dataset_name_for_user

logger = logging.getLogger(__name__)


def knowflow_stack_reachable() -> bool:
    settings = get_settings()
    if not settings.knowflow_enabled:
        return False
    return RagflowClient().health_ok()


class KnowflowClient(Protocol):
    def enabled(self) -> bool: ...

    def health(self) -> dict: ...

    def retrieve(
        self,
        parsed_docs: list[ParsedDocument],
        query: str,
        *,
        document_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]: ...

    def sync_platform_document(
        self,
        *,
        platform_document_id: uuid.UUID,
        file_name: str,
        content: bytes,
        mime_type: str,
        dataset_id: str | None = None,
    ) -> str | None: ...


class LocalKnowflowClient:
    def enabled(self) -> bool:
        return False

    def health(self) -> dict:
        return {"mode": "local", "ok": True}

    def retrieve(
        self,
        parsed_docs: list[ParsedDocument],
        query: str,
        *,
        document_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        allowed = set(document_ids or [])
        docs = parsed_docs
        if allowed:
            docs = [d for d in parsed_docs if str(d.document_id) in allowed]
        return local_search(docs, query, limit=limit)

    def sync_platform_document(self, **kwargs) -> str | None:
        return None


class RagflowKnowflowClient:
    def __init__(
        self,
        *,
        platform_user_id: uuid.UUID | None = None,
        ragflow_auth: str | None = None,
    ) -> None:
        self._settings = get_settings()
        if self._settings.ragflow_api_key:
            self._rag = RagflowClient(api_key=self._settings.ragflow_api_key)
        elif ragflow_auth:
            self._rag = RagflowClient(session_auth=ragflow_auth)
        else:
            self._rag = RagflowClient()
        self._platform_user_id = platform_user_id
        self._dataset_id: str | None = None
        self._doc_map: dict[str, str] = {}

    def enabled(self) -> bool:
        return bool(
            self._settings.ragflow_api_key
            or self._rag.session_auth
        )

    def health(self) -> dict:
        ok = self._rag.health_ok()
        return {
            "mode": "ragflow",
            "ok": ok,
            "base_url": self._settings.ragflow_api_url,
            "dataset": self._dataset_id,
            "auth": "api_key" if self._settings.ragflow_api_key else "user_session",
        }

    def _ensure_dataset(self) -> str:
        if self._dataset_id:
            return self._dataset_id
        if not self._platform_user_id:
            name = self._settings.ragflow_dataset_name
        else:
            name = dataset_name_for_user(self._platform_user_id)
        self._dataset_id = self._rag.ensure_dataset(name)
        return self._dataset_id

    def sync_platform_document(
        self,
        *,
        platform_document_id: uuid.UUID,
        file_name: str,
        content: bytes,
        mime_type: str,
        dataset_id: str | None = None,
    ) -> str | None:
        pid = str(platform_document_id)
        if pid in self._doc_map:
            return self._doc_map[pid]
        try:
            ds_id = dataset_id or self._ensure_dataset()
            doc = self._rag.upload_document(
                ds_id,
                file_name=file_name,
                content=content,
                meta_fields={
                    "platform_document_id": pid,
                    "platform_user_id": str(self._platform_user_id or ""),
                    "mime_type": mime_type,
                },
            )
            rag_doc_id = doc.get("id") or doc.get("doc_id")
            if not rag_doc_id:
                return None
            try:
                self._rag.parse_documents(ds_id, [str(rag_doc_id)])
            except RagflowError as e:
                logger.warning(
                    "KnowFlow 解析文档失败（文件已上传）%s: %s", pid, e
                )
            self._doc_map[pid] = str(rag_doc_id)
            return str(rag_doc_id)
        except RagflowError as e:
            logger.warning("KnowFlow 索引文档失败 %s: %s", pid, e)
            return None

    def retrieve(
        self,
        parsed_docs: list[ParsedDocument],
        query: str,
        *,
        document_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        allowed = list(document_ids or [])
        rag_doc_ids: list[str] = []
        for pid in allowed:
            if pid in self._doc_map:
                rag_doc_ids.append(self._doc_map[pid])
        try:
            ds_id = self._ensure_dataset()
            hits = self._rag.retrieval(
                question=query,
                dataset_ids=[ds_id],
                document_ids=rag_doc_ids or None,
                top_k=limit,
            )
            if hits:
                for h in hits:
                    h.setdefault("source", "knowflow")
                return hits
        except RagflowError as e:
            logger.warning("KnowFlow 检索失败，回退本地检索: %s", e)
        docs = parsed_docs
        if allowed:
            docs = [d for d in parsed_docs if str(d.document_id) in allowed]
        return local_search(docs, query, limit=limit)


def get_knowflow_client(
    *,
    platform_user_id: uuid.UUID | None = None,
    ragflow_auth: str | None = None,
) -> KnowflowClient:
    settings = get_settings()
    if not settings.knowflow_enabled or not knowflow_stack_reachable():
        return LocalKnowflowClient()
    client = RagflowKnowflowClient(
        platform_user_id=platform_user_id,
        ragflow_auth=ragflow_auth,
    )
    if client.enabled():
        return client
    return LocalKnowflowClient()


def get_knowflow_client_for_user(db, user) -> KnowflowClient:
    from app.services.ragflow_identity_service import get_user_ragflow_auth

    auth = get_user_ragflow_auth(db, user)
    return get_knowflow_client(platform_user_id=user.id, ragflow_auth=auth)


def get_knowflow_client_for_catalog(db, user) -> KnowflowClient:
    """目录对齐：mapped 模式下分级库在 bootstrap 租户，普通用户也用特权会话建库/匹配。"""
    from app.config import get_settings
    from app.core.permissions import user_is_system_admin
    from app.services.ragflow_scope_service import _privileged_rag_client

    mode = (get_settings().ragflow_account_mode or "").strip().lower()
    use_privileged = user_is_system_admin(db, user) or mode == "mapped"
    if use_privileged:
        priv = _privileged_rag_client(db)
        if priv and priv.session_auth:
            client = get_knowflow_client(
                platform_user_id=user.id,
                ragflow_auth=priv.session_auth,
            )
            if client.enabled():
                return client
        if priv and priv.api_key:
            client = RagflowKnowflowClient(platform_user_id=user.id)
            client._rag = priv
            if client.enabled():
                return client
    return get_knowflow_client_for_user(db, user)
