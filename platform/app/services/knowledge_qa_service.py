"""知识检索问答：混合检索 + LLM 生成带引用编号的回答。"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import PermissionLevel
from app.integrations.knowflow_client import get_knowflow_client_for_user, knowflow_stack_reachable
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.integrations.text_extract import local_search
from app.models.org import User
from app.models.rag import RagMessage, RagSession
from app.services.compare_service import load_parsed_documents, validate_document_scope
from app.services.document_service import get_document, resolve_current_version
from app.services.ragflow_version_link_service import (
    ragflow_to_platform_version_map,
    resolve_latest_indexed_version,
)

logger = logging.getLogger(__name__)

_KNOWLEDGE_QA_SYSTEM = (
    "你是企业知识库问答助手。仅根据用户提供的检索片段回答问题。\n"
    "要求：\n"
    "- 使用简体中文，条理清晰，可使用 Markdown 列表\n"
    "- 引用片段中的事实时，必须在句末标注引用编号，格式为 [1]、[2]\n"
    "- 同一句话可标注多个引用，如 [1][2]\n"
    "- 不要编造片段中未出现的内容；信息不足时明确说明\n"
    "- 不要输出「以上内容来自…检索」等元信息脚注"
)

_NO_HIT_ANSWER = (
    "在所选文档的知识库内容中未找到与问题直接相关的段落。"
    "请尝试换关键词，或扩大文档范围。"
)


def _parse_ids(ids: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(x) for x in ids]


def _rag_clients_for_qa(db: Session, user: User) -> list[RagflowClient]:
    from app.integrations.knowflow_client import get_knowflow_client_for_user
    from app.services.ragflow_identity_service import get_user_ragflow_auth
    from app.services.ragflow_scope_service import _privileged_rag_client

    clients: list[RagflowClient] = []
    seen: set[str] = set()

    def _add(client: RagflowClient | None) -> None:
        if client is None:
            return
        key = (client.session_auth or "") + "|" + (client.api_key or "")
        if key in seen:
            return
        seen.add(key)
        clients.append(client)

    kf = get_knowflow_client_for_user(db, user)
    if hasattr(kf, "_rag"):
        _add(kf._rag)
    auth = get_user_ragflow_auth(db, user)
    if auth:
        _add(RagflowClient(session_auth=auth))
    priv = _privileged_rag_client(db)
    _add(priv)
    settings = get_settings()
    if settings.ragflow_api_key:
        _add(RagflowClient(api_key=settings.ragflow_api_key))
    return clients


def _resolve_hit_platform_document_id(
    h: dict,
    allowed: set[str],
    vmap: dict[str, dict],
) -> str | None:
    """将检索命中映射为平台 document_id（RAGFlow 切片常只有 ragflow_document_id）。"""
    rid = str(h.get("ragflow_document_id") or "")
    did_raw = h.get("document_id")
    if did_raw:
        try:
            did_str = str(uuid.UUID(str(did_raw)))
            if did_str in allowed:
                return did_str
        except ValueError:
            pass
    if rid and rid in vmap:
        pid = vmap[rid].get("platform_document_id")
        if pid and pid in allowed:
            return pid
    return None


def _filter_hits_by_version(
    db: Session,
    user: User,
    hits: list[dict],
    doc_ids: list[uuid.UUID],
) -> list[dict]:
    allowed = {str(d) for d in doc_ids}
    rag_ids = [
        str(h.get("ragflow_document_id") or h.get("document_id") or "") for h in hits
    ]
    vmap = ragflow_to_platform_version_map(db, [x for x in rag_ids if x])
    filtered: list[dict] = []
    for h in hits:
        rid = str(h.get("ragflow_document_id") or "")
        platform_id = _resolve_hit_platform_document_id(h, allowed, vmap)
        if not platform_id:
            continue
        doc = get_document(db, uuid.UUID(platform_id))
        if not doc:
            continue
        indexed = resolve_latest_indexed_version(db, doc)
        current = indexed or resolve_current_version(db, doc)
        chunk_ver = (vmap.get(rid) or {}).get("document_version_id")
        if current and chunk_ver and chunk_ver != str(current.id):
            continue
        normalized = dict(h)
        normalized["document_id"] = platform_id
        filtered.append(normalized)
    return filtered


def _qa_retrieval_targets(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
) -> tuple[list[str], list[str]]:
    """按最后索引成功版本收集 RAG 检索目标（复用文档对比/同步映射）。"""
    from app.services.ragflow_sync_service import (
        _get_link,
        allowed_ragflow_doc_map,
        get_document_mirror_link,
    )
    from app.services.ragflow_version_link_service import resolve_index_link

    platform_ids = [str(d) for d in doc_ids]
    ragflow_map = allowed_ragflow_doc_map(db, user, platform_ids)
    dataset_ids: list[str] = []
    rag_doc_ids: list[str] = []

    for pid in platform_ids:
        rag_id = ragflow_map.get(pid)
        if not rag_id:
            continue
        rag_doc_ids.append(str(rag_id).strip())
        try:
            did = uuid.UUID(pid)
        except ValueError:
            continue
        doc = get_document(db, did)
        if not doc:
            continue
        ds_id: str | None = None
        mirror = get_document_mirror_link(db, did, user.id)
        if mirror and mirror.dataset_id:
            ds_id = str(mirror.dataset_id).strip()
        if not ds_id:
            vl, _ = resolve_index_link(db, doc)
            if vl and vl.dataset_id:
                ds_id = str(vl.dataset_id).strip()
        if not ds_id:
            link = _get_link(db, did)
            if link and link.dataset_id:
                ds_id = str(link.dataset_id).strip()
        if ds_id:
            dataset_ids.append(ds_id)

    return list(dict.fromkeys(dataset_ids)), list(dict.fromkeys(rag_doc_ids))


def _knowflow_retrieve(
    db: Session,
    user: User,
    docs,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int,
) -> list[dict]:
    dataset_ids, rag_doc_ids = _qa_retrieval_targets(db, user, doc_ids)
    if not dataset_ids or not rag_doc_ids:
        return []

    settings = get_settings()
    for rag in _rag_clients_for_qa(db, user):
        if not rag.health_ok():
            continue
        try:
            raw = rag.retrieval(
                question=question,
                dataset_ids=dataset_ids,
                document_ids=rag_doc_ids or None,
                top_k=max(limit * 2, 12),
                keyword=True,
                highlight=True,
                vector_similarity_weight=float(
                    settings.knowledge_retrieval_vector_weight
                ),
            )
            hits = _filter_hits_by_version(db, user, raw, doc_ids)
            if hits:
                return hits[:limit]
        except RagflowError as exc:
            logger.debug("知识检索 KnowFlow 检索失败: %s", exc)
    return []


def _local_retrieve(
    db: Session,
    user: User,
    docs,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int,
) -> list[dict]:
    try:
        parsed = load_parsed_documents(db, docs)
    except Exception:
        return []
    scope_ids = [str(d.id) for d in docs]
    hits = local_search(
        [p for p in parsed if str(p.document_id) in scope_ids],
        question,
        limit=limit,
    )
    out: list[dict] = []
    for h in hits:
        pid = str(h.get("document_id", ""))
        if pid not in scope_ids:
            continue
        doc = get_document(db, uuid.UUID(pid))
        if not doc:
            continue
        out.append(
            {
                "document_id": pid,
                "snippet": h.get("snippet") or "",
                "highlight": h.get("snippet") or "",
                "score": h.get("score"),
                "anchor_json": h.get("anchor_json"),
                "source": "local",
            }
        )
    return out[:limit]


def retrieve_hits_for_qa(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    question: str,
    *,
    limit: int = 8,
) -> tuple[list[dict], str]:
    docs = validate_document_scope(
        db,
        user,
        doc_ids,
        min_count=1,
        max_count=20,
        required_level=PermissionLevel.query.value,
    )
    settings = get_settings()
    stack_on = settings.knowflow_enabled and knowflow_stack_reachable()
    kf = get_knowflow_client_for_user(db, user)

    if stack_on and kf.enabled():
        hits = _knowflow_retrieve(db, user, docs, doc_ids, question, limit=limit)
        if hits:
            return hits, "hybrid"

    hits = _local_retrieve(db, user, docs, doc_ids, question, limit=limit)
    return hits, "local"


def _doc_titles(db: Session, doc_ids: list[uuid.UUID]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for did in doc_ids:
        doc = get_document(db, did)
        if doc:
            titles[str(did)] = doc.title or "未命名文档"
    return titles


def build_citations(hits: list[dict], doc_titles: dict[str, str]) -> list[dict]:
    citations: list[dict] = []
    for i, h in enumerate(hits, start=1):
        did = str(h.get("document_id") or "")
        snippet = (h.get("highlight") or h.get("snippet") or "").strip()
        citations.append(
            {
                "index": i,
                "document_id": did or None,
                "title": doc_titles.get(did, did or "文档"),
                "snippet": snippet[:2000],
                "score": h.get("score"),
                "anchor_json": h.get("anchor_json"),
                "chunk_id": h.get("chunk_id"),
                "dataset_id": h.get("dataset_id"),
                "image_id": (h.get("image_id") or "").strip() or None,
                "ragflow_document_id": h.get("ragflow_document_id"),
                "source": h.get("source") or "knowflow",
            }
        )
    return citations


def _build_context_block(hits: list[dict], doc_titles: dict[str, str]) -> str:
    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        did = str(h.get("document_id") or "")
        title = doc_titles.get(did, "文档")
        body = (h.get("highlight") or h.get("snippet") or "").strip()
        page = (h.get("anchor_json") or {}).get("page")
        page_hint = f"（约第 {page} 页）" if page else ""
        blocks.append(f"[{i}] 《{title}》{page_hint}\n{body}")
    return "\n\n".join(blocks)


def _answer_prefix_blocks(
    *,
    plan: dict[str, Any],
    changelog_block: str,
    diff_summary_block: str,
) -> str:
    parts: list[str] = []
    if diff_summary_block and "version_compare" in plan.get("intents", []):
        parts.append(diff_summary_block)
    if changelog_block and "version_compare" in plan.get("intents", []):
        parts.append(changelog_block)
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


async def _iter_llm_answer_stream(*, question: str, context: str) -> AsyncIterator[str]:
    from app.integrations.deepseek_client import is_configured, resolve_credentials

    if not is_configured():
        return
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return
    settings = get_settings()
    user_content = f"问题：{question.strip()}\n\n检索片段：\n{context}"
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _KNOWLEDGE_QA_SYSTEM},
                        {
                            "role": "user",
                            "content": user_content[: settings.deepseek_max_chars],
                        },
                    ],
                    "temperature": 0.2,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        if raw == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        yield delta
    except Exception as exc:
        logger.warning("知识检索 LLM 流式生成失败: %s", exc)


def _call_llm_answer(*, question: str, context: str) -> str | None:
    from app.integrations.deepseek_client import is_configured, resolve_credentials

    if not is_configured():
        return None
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return None
    settings = get_settings()
    user_content = f"问题：{question.strip()}\n\n检索片段：\n{context}"
    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _KNOWLEDGE_QA_SYSTEM},
                        {
                            "role": "user",
                            "content": user_content[: settings.deepseek_max_chars],
                        },
                    ],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return content or None
    except Exception as exc:
        logger.warning("知识检索 LLM 生成失败: %s", exc)
        return None


def _strip_meta_footer(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if "以上内容来自" in line and "检索" in line:
            continue
        if "知识服务就绪" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _fallback_answer(question: str, hits: list[dict], doc_titles: dict[str, str]) -> str:
    lines = [f"根据已选文档，与「{question}」相关的要点如下：", ""]
    for i, h in enumerate(hits, start=1):
        did = str(h.get("document_id") or "")
        title = doc_titles.get(did, did or "文档")
        snippet = (h.get("highlight") or h.get("snippet") or "")[:400]
        lines.append(f"- {snippet} [{i}]（《{title}》）")
    return "\n".join(lines)


def generate_answer(
    *,
    question: str,
    hits: list[dict],
    doc_titles: dict[str, str],
) -> str:
    if not hits:
        return _NO_HIT_ANSWER
    context = _build_context_block(hits, doc_titles)
    llm_answer = _call_llm_answer(question=question, context=context)
    if llm_answer:
        return _strip_meta_footer(llm_answer)
    return _fallback_answer(question, hits, doc_titles)


def fetch_citation_image_bytes(
    db: Session, user: User, image_id: str
) -> tuple[bytes, str] | None:
    image_id = (image_id or "").strip()
    if not image_id:
        return None
    for rag in _rag_clients_for_qa(db, user):
        if not rag.health_ok():
            continue
        try:
            return rag.get_chunk_image(image_id)
        except RagflowError as exc:
            logger.debug("获取引用截图失败 image=%s: %s", image_id, exc)
    return None


def _resolve_qa_session(
    db: Session,
    user: User,
    *,
    session_id: str | None,
    document_ids: list[str] | None,
) -> RagSession:
    from app.core.exceptions import bad_request, not_found

    if session_id:
        sid = uuid.UUID(session_id)
        session = db.get(RagSession, sid)
        if not session or session.created_by != user.id:
            raise not_found("会话不存在")
        return session
    if not document_ids:
        raise bad_request("请从左侧选择知识库或文档")
    from app.services import rag_service

    return rag_service.create_session(
        db,
        user,
        document_ids=document_ids,
        title="知识检索",
    )


async def iter_knowledge_qa_stream(
    db: Session,
    user: User,
    *,
    question: str,
    session_id: str | None = None,
    document_ids: list[str] | None = None,
) -> AsyncIterator[str]:
    from fastapi import HTTPException

    question = question.strip()
    if not question:
        yield json.dumps({"error": "问题不能为空"}, ensure_ascii=False)
        return

    try:
        session = _resolve_qa_session(
            db,
            user,
            session_id=session_id,
            document_ids=document_ids,
        )
    except HTTPException as exc:
        detail = exc.detail
        msg = (
            detail.get("message")
            if isinstance(detail, dict)
            else str(detail)
        )
        yield json.dumps({"error": msg or "请求失败"}, ensure_ascii=False)
        return

    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": "正在检索相关文档"}},
        ensure_ascii=False,
    )

    db.add(RagMessage(session_id=session.id, role="user", content=question))
    db.flush()

    doc_ids = _parse_ids(session.document_ids)
    hits, _mode = retrieve_hits_for_qa(db, user, doc_ids, question, limit=8)
    doc_titles = _doc_titles(db, doc_ids)
    citations = build_citations(hits, doc_titles)
    yield json.dumps({"citations": citations}, ensure_ascii=False)

    from app.services.knowledge_agent_service import (
        format_changelog_context,
        format_diff_summary_context,
        load_version_changelogs,
        load_version_diff_summaries,
        plan_knowledge_query,
    )

    kf = get_knowflow_client_for_user(db, user)
    plan = plan_knowledge_query(
        question=question,
        document_count=len(doc_ids),
        knowflow_available=bool(kf.enabled()),
    )
    changelogs = load_version_changelogs(db, doc_ids)
    diff_summaries = load_version_diff_summaries(db, doc_ids)
    prefix = _answer_prefix_blocks(
        plan=plan,
        changelog_block=format_changelog_context(changelogs, doc_titles),
        diff_summary_block=format_diff_summary_context(diff_summaries, doc_titles),
    )

    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": "正在生成回答"}},
        ensure_ascii=False,
    )

    answer_parts: list[str] = []
    if prefix:
        answer_parts.append(prefix)
        yield json.dumps({"delta": prefix}, ensure_ascii=False)

    if not hits:
        answer_parts.append(_NO_HIT_ANSWER)
        yield json.dumps({"delta": _NO_HIT_ANSWER}, ensure_ascii=False)
    else:
        context = _build_context_block(hits, doc_titles)
        streamed = False
        async for delta in _iter_llm_answer_stream(question=question, context=context):
            streamed = True
            answer_parts.append(delta)
            yield json.dumps({"delta": delta}, ensure_ascii=False)
        if not streamed:
            fallback = _fallback_answer(question, hits, doc_titles)
            answer_parts.append(fallback)
            yield json.dumps({"delta": fallback}, ensure_ascii=False)

    answer = _strip_meta_footer("".join(answer_parts))

    msg = RagMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        citations=citations,
    )
    db.add(msg)
    from datetime import datetime, timezone

    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)

    yield json.dumps(
        {
            "done": True,
            "reply": answer,
            "citations": citations,
            "conversation_id": str(session.id),
        },
        ensure_ascii=False,
    )


def answer_knowledge_question(
    db: Session,
    session: RagSession,
    user: User,
    question: str,
) -> RagMessage:
    question = question.strip()
    if not question:
        from app.core.exceptions import bad_request

        raise bad_request("问题不能为空")

    db.add(RagMessage(session_id=session.id, role="user", content=question))
    db.flush()

    doc_ids = _parse_ids(session.document_ids)
    hits, _mode = retrieve_hits_for_qa(db, user, doc_ids, question, limit=8)
    doc_titles = _doc_titles(db, doc_ids)
    citations = build_citations(hits, doc_titles)
    answer = generate_answer(question=question, hits=hits, doc_titles=doc_titles)

    from app.services.knowledge_agent_service import (
        enrich_answer_with_plan,
        format_changelog_context,
        format_diff_summary_context,
        load_version_changelogs,
        load_version_diff_summaries,
        plan_knowledge_query,
    )

    kf = get_knowflow_client_for_user(db, user)
    plan = plan_knowledge_query(
        question=question,
        document_count=len(doc_ids),
        knowflow_available=bool(kf.enabled()),
    )
    changelogs = load_version_changelogs(db, doc_ids)
    diff_summaries = load_version_diff_summaries(db, doc_ids)
    answer = enrich_answer_with_plan(
        answer,
        plan=plan,
        changelog_block=format_changelog_context(changelogs, doc_titles),
        diff_summary_block=format_diff_summary_context(diff_summaries, doc_titles),
    )
    answer = _strip_meta_footer(answer)

    msg = RagMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        citations=citations,
    )
    db.add(msg)
    from datetime import datetime, timezone

    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg
