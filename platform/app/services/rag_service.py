"""Knowledge Q&A — KnowFlow / RAGFlow 检索，未启用时回退本地关键词检索。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.knowflow_client import get_knowflow_client_for_user
from app.services.ragflow_sync_service import (
    allowed_ragflow_doc_map,
    sync_document_to_knowflow,
)
from app.integrations.text_extract import local_search
from app.models.document import DocumentVersion
from app.models.org import User
from app.models.rag import RagMessage, RagSession
from app.core.permissions import PermissionLevel
from app.services.compare_service import (
    load_parsed_documents,
    validate_document_scope,
)
from app.services.document_service import get_document
from app.storage.object_store import get_object_store


def _parse_ids(ids: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(x) for x in ids]


def _sync_docs_to_knowflow(
    db: Session, user: User, docs
) -> dict[str, str]:
    """返回 platform_document_id -> ragflow_document_id"""
    mapping: dict[str, str] = {}
    for doc in docs:
        rag_id = sync_document_to_knowflow(db, user, doc)
        if rag_id:
            mapping[str(doc.id)] = rag_id
    return mapping


def create_session(
    db: Session,
    user: User,
    *,
    document_ids: list[str],
    title: str = "知识问答",
) -> RagSession:
    uuids = _parse_ids(document_ids)
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
                    "file_name": p.file_name,
                    "char_count": len(p.full_text),
                    "parse_quality": p.parse_quality,
                    "warning": p.warning,
                }
                for p in parsed
            ],
            "full_text_cache": {str(p.document_id): p.full_text for p in parsed},
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


def list_user_sessions(
    db: Session,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
) -> tuple[list[RagSession], int]:
    base = select(RagSession).where(RagSession.created_by == user_id)
    total = db.scalar(select(func.count()).select_from(base)) or 0
    items = db.scalars(
        base.order_by(RagSession.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def _build_answer(query: str, hits: list[dict], doc_titles: dict[str, str]) -> tuple[str, list[dict]]:
    if not hits:
        return (
            "在所选文档的知识库内容中未找到与问题直接相关的段落。请尝试换关键词，或扩大文档范围。",
            [],
        )
    lines = [f"根据已选文档，与「{query}」相关的要点如下：", ""]
    citations: list[dict] = []
    for i, h in enumerate(hits[:5], start=1):
        did = str(h.get("document_id", ""))
        title = doc_titles.get(did, did or "文档")
        lines.append(f"{i}. 【{title}】{h['snippet'][:280]}")
        citations.append(
            {
                "index": i,
                "document_id": did,
                "title": title,
                "snippet": h["snippet"][:500],
                "score": h.get("score"),
                "anchor_json": h.get("anchor_json"),
            }
        )
    lines.append("")
    if get_settings().knowflow_enabled and get_settings().ragflow_api_key:
        lines.append("以上内容来自知识库语义检索；请结合原文判断。")
    else:
        lines.append("以上内容来自本地关键词检索；知识服务就绪后可获得语义检索能力。")
    return "\n".join(lines), citations


def ask(
    db: Session,
    session: RagSession,
    user: User,
    question: str,
) -> RagMessage:
    from app.integrations.text_extract import ParsedDocument

    question = question.strip()
    if not question:
        from app.core.exceptions import bad_request

        raise bad_request("问题不能为空")

    db.add(RagMessage(session_id=session.id, role="user", content=question))
    db.flush()

    doc_ids = _parse_ids(session.document_ids)
    docs = validate_document_scope(
        db,
        user,
        doc_ids,
        min_count=1,
        max_count=20,
        required_level=PermissionLevel.query.value,
    )
    parsed = load_parsed_documents(db, docs)

    cache = (session.payload or {}).get("full_text_cache") or {}
    if cache:
        parsed = [
            ParsedDocument(
                document_id=uuid.UUID(did),
                file_name="",
                full_text=cache.get(did, ""),
            )
            for did in session.document_ids
        ]

    kf = get_knowflow_client_for_user(db, user)
    ragflow_map = (session.payload or {}).get("ragflow_doc_map") or {}
    if hasattr(kf, "_doc_map"):
        kf._doc_map.update(ragflow_map)

    if hasattr(kf, "_doc_map"):
        kf._doc_map.update(allowed_ragflow_doc_map(db, user, [str(x) for x in doc_ids]))
    hits = kf.retrieve(
        parsed,
        question,
        document_ids=[str(x) for x in doc_ids],
        limit=10,
    )

    doc_titles = {}
    for did in doc_ids:
        d = get_document(db, did)
        if d:
            doc_titles[str(did)] = d.title

    answer, citations = _build_answer(question, hits, doc_titles)
    msg = RagMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        citations=citations,
    )
    db.add(msg)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


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
