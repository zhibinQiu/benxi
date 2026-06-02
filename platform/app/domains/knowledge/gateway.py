"""KnowFlow 知识域 Facade — 平台内知识能力的唯一对外编排入口。

其他模块应通过 ``knowledge`` 单例调用，避免直接散落 import
ragflow_identity / ragflow_sync / ragflow_scope 形成环依赖。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.config import get_settings
from app.integrations.knowflow_client import (
    KnowflowClient,
    get_knowflow_client,
    get_knowflow_client_for_user,
    knowflow_stack_reachable,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.document import Document
    from app.models.org import User
    from app.models.ragflow_document_link import RagflowDocumentLink


class KnowledgeGateway:
    """Facade：封装 SSO、文档同步、KB 授权与嵌入元数据。"""

    @staticmethod
    def enabled() -> bool:
        return bool(get_settings().knowflow_enabled)

    @staticmethod
    def stack_reachable() -> bool:
        return knowflow_stack_reachable()

    @staticmethod
    def client_for_user(db: Session, user: User) -> KnowflowClient:
        return get_knowflow_client_for_user(db, user)

    @staticmethod
    def client_probe(platform_user_id: uuid.UUID | None = None) -> KnowflowClient:
        """探活 / meta，不触发 RAGFlow 开户。"""
        return get_knowflow_client(platform_user_id=platform_user_id)

    @staticmethod
    def user_auth(db: Session, user: User) -> str | None:
        from app.services.ragflow_identity_service import get_user_ragflow_auth

        return get_user_ragflow_auth(db, user)

    @staticmethod
    def warm_on_login(db: Session, user: User):
        from app.services.ragflow_identity_service import warm_ragflow_on_login

        return warm_ragflow_on_login(db, user)

    @staticmethod
    def ensure_account(db: Session, user: User):
        from app.services.ragflow_identity_service import ensure_ragflow_account

        return ensure_ragflow_account(db, user)

    @staticmethod
    def reconcile_dept_membership_kb(
        db: Session,
        user: User,
        *,
        previous_dept_ids: list[uuid.UUID] | None,
    ) -> None:
        from app.services.ragflow_scope_service import reconcile_dept_membership_kb

        reconcile_dept_membership_kb(db, user, previous_dept_ids=previous_dept_ids)

    @staticmethod
    def revoke_all_dept_kb_grants(db: Session, user: User) -> None:
        from app.services.ragflow_scope_service import revoke_all_dept_kb_grants

        revoke_all_dept_kb_grants(db, user)

    @staticmethod
    def build_embed_session(db: Session, user: User, *, sync_catalog: bool | None = None) -> dict:
        from app.services.ragflow_identity_service import build_embed_session

        return build_embed_session(db, user, sync_catalog=sync_catalog)

    @staticmethod
    def meta_payload(db: Session, user: User) -> dict:
        from app.domains.knowledge.meta_service import build_rag_meta_payload

        return build_rag_meta_payload(db, user)

    @staticmethod
    def sync_document(
        db: Session, user: User, document: Document, *, force: bool = False
    ) -> str | None:
        from app.services.ragflow_sync_service import sync_document_to_knowflow

        return sync_document_to_knowflow(db, user, document, force=force)

    @staticmethod
    def remove_document(db: Session, document: Document) -> bool:
        from app.services.ragflow_sync_service import remove_platform_document_from_knowflow

        return remove_platform_document_from_knowflow(db, document)

    @staticmethod
    def document_link(db: Session, document_id: uuid.UUID) -> RagflowDocumentLink | None:
        from app.services.ragflow_sync_service import get_document_link

        return get_document_link(db, document_id)

    @staticmethod
    def sync_kb_grants(db: Session, document: Document) -> None:
        from app.services.ragflow_scope_service import sync_document_kb_grants

        sync_document_kb_grants(db, document)

    @staticmethod
    def reconcile_catalog(
        db: Session,
        user: User,
        *,
        sync_limit: int = 0,
        sync_documents: bool = False,
    ) -> dict:
        from app.services.knowflow_catalog_service import reconcile_user_knowflow_catalog

        return reconcile_user_knowflow_catalog(
            db, user, sync_limit=sync_limit, sync_documents=sync_documents
        )

    @staticmethod
    def purge_stale_links(db: Session) -> int:
        from app.services.ragflow_sync_service import purge_stale_knowflow_links

        return purge_stale_knowflow_links(db)


knowledge = KnowledgeGateway()
