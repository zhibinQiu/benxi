"""Knowledge Q&A — KnowFlow 混合检索 + LLM 引用回答（见 knowledge_qa_service）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PermissionLevel
from app.core.text_sanitize import sanitize_json_text
from app.core.uuid_utils import parse_uuid_list
from app.integrations.knowflow_client import get_knowflow_client_for_user
from app.models.org import User
from app.models.rag import RagMessage, RagSession
from app.services.compare_service import (
    load_parsed_documents,
    validate_document_scope,
)
from app.services.document_service import get_document

def _sync_docs_to_knowflow(
    db: Session, user: User, docs
) -> dict[str, str]:
    """返回已有索引映射；仅对尚未完成索引的文档提交后台任务。"""
    from app.domains.knowledge.gateway import knowledge
    from app.services.document_index_service import (
        enrich_document_index_meta,
        is_index_ready_meta,
    )
    from app.services.document_service import resolve_current_version
    from app.services.knowledge_sync_job_service import enqueue_document_knowledge_index
    from app.services.ragflow_sync_service import allowed_ragflow_doc_map

    ids = [str(d.id) for d in docs]
    mapping = allowed_ragflow_doc_map(db, user, ids)
    if not knowledge.enabled():
        return mapping

    meta_by_doc = enrich_document_index_meta(
        db, user, list(docs), live_ragflow=False
    )
    for doc in docs:
        if is_index_ready_meta(meta_by_doc.get(str(doc.id))):
            continue
        version_id = None
        version = resolve_current_version(db, doc)
        if version:
            version_id = version.id
        enqueue_document_knowledge_index(
            db,
            user_id=user.id,
            document_id=doc.id,
            version_id=version_id,
            force=False,
            document_title=doc.title,
        )
    return mapping


def create_session(
    db: Session,
    user: User,
    *,
    document_ids: list[str],
    title: str = "知识问答",
) -> RagSession:
    uuids = parse_uuid_list(document_ids)
    if len(uuids) < 1:
        from app.core.exceptions import bad_request

        raise bad_request("请至少选择 1 份文档")
    docs = validate_document_scope(
        db,
        user,
        uuids,
        min_count=1,
        max_count=20,
        required_level=PermissionLevel.query.value,
        allow_index_only=True,
    )
    parsed = load_parsed_documents(db, docs)
    ragflow_map = _sync_docs_to_knowflow(db, user, docs)
    session = RagSession(
        created_by=user.id,
        title=title,
        document_ids=[str(x) for x in uuids],
        payload={
            "parsed": [
                {
                    "document_id": str(p.document_id),
                    "file_name": sanitize_json_text(p.file_name),
                    "char_count": len(p.full_text),
                    "parse_quality": p.parse_quality,
                    "warning": sanitize_json_text(p.warning),
                }
                for p in parsed
            ],
            "ragflow_doc_map": ragflow_map,
            "knowflow": get_knowflow_client_for_user(db, user).health(),
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_user_session(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID
) -> RagSession | None:
    s = db.get(RagSession, session_id)
    if not s or s.created_by != user_id:
        return None
    return s


def ask(
    db: Session,
    session: RagSession,
    user: User,
    question: str,
    *,
    use_agentic: bool = True,
) -> RagMessage:
    from app.services.knowledge_qa_service import answer_knowledge_question

    return answer_knowledge_question(
        db, session, user, question, use_agentic=use_agentic
    )


def session_to_dict(db: Session, session: RagSession) -> dict:
    messages = db.scalars(
        select(RagMessage)
        .where(RagMessage.session_id == session.id)
        .order_by(RagMessage.created_at)
    ).all()
    titles = {}
    for did in session.document_ids:
        d = get_document(db, uuid.UUID(did))
        if d:
            titles[did] = d.title
    return {
        "id": str(session.id),
        "title": session.title,
        "document_ids": session.document_ids,
        "document_titles": titles,
        "payload": session.payload or {},
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "citations": m.citations or [],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }
