"""知识检索问答：混合检索 + LLM 生成带引用编号的回答。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.permissions import PermissionLevel
from app.core.platform_assistant import assistant_knowledge_qa_persona
from app.domains.knowledge import knowledge
from app.integrations.deepseek_client import chat_completion_stream
from app.integrations.ragflow_client import RagflowClient, RagflowError
from app.integrations.text_extract import local_search
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.models.rag import RagMessage, RagSession
from app.models.ragflow_document_link import RagflowDocumentLink
from app.models.ragflow_document_version_link import RagflowDocumentVersionLink
from app.services.compare_service import load_parsed_documents, validate_document_scope
from app.services.document_service import get_document, resolve_current_version
from app.services.ragflow_version_link_service import (
    ragflow_to_platform_version_map,
    resolve_index_link,
    resolve_latest_indexed_version,
)

logger = logging.getLogger(__name__)

_KNOWLEDGE_QA_SYSTEM = (
    f"{assistant_knowledge_qa_persona()}。仅根据用户提供的编号检索片段回答问题。\n"
    "要求：\n"
    "- 使用简体中文，条理清晰，可使用 Markdown 列表\n"
    "- 自我介绍或提及助手时统一使用名称「小析」\n"
    "- **信息优先级**：检索片段为唯一事实依据；若与模型自身常识冲突，**以片段为准**，不得用常识覆盖或修正片段表述\n"
    "- 引用规则：结论或要点句末标注 [1]、[2]；编号必须与下方片段 [n] **严格一一对应**，不得张冠李戴\n"
    "- 每个 [n] 只能标注确实来自该编号片段的内容；不确定时不要标注\n"
    "- 同一段落可标注多个编号；不要把每个短句都加引用\n"
    "- **禁止来源叙述**：回答中不得出现文档名、书名、「根据…文档」「参考了…」「据…显示」等；"
    "溯源只通过 [n] 完成，文档信息由界面引用区展示\n"
    "- 不要编造片段中未出现的内容；信息不足时明确说明\n"
    "- 不要输出「以上内容来自…检索」等元信息脚注\n"
    "- 界面底部会展示本次检索到的全部片段来源；请在关键结论句末尽量标注 [n]，"
    "以便读者将正文与引用卡片对应"
)

_KG_QA_SYSTEM_APPENDIX = (
    "\n\n补充说明：部分编号片段来自【本体图谱实体与关系】，描述实体之间的结构化关联；"
    "图谱事实与文档检索片段同等可作为依据，引用时同样使用 [n]。"
)


def _resolve_kg_qa_context(db: Session, user: User, question: str):
    from app.core.permissions import user_has_permission
    from app.services.kg_service import retrieve_kg_context_for_question

    if not user_has_permission(db, user, "feature.kg_palantir"):
        return None
    return retrieve_kg_context_for_question(db, user, question)


def _qa_system_prompt(*, include_kg: bool) -> str:
    if include_kg:
        return _KNOWLEDGE_QA_SYSTEM + _KG_QA_SYSTEM_APPENDIX
    return _KNOWLEDGE_QA_SYSTEM


_CITATION_REF_RE = re.compile(r"[\[【](\d{1,2})[\]】]")
_CITATION_REF_REPLACE_RE = re.compile(r"(\[|【)(\d{1,2})(\]|】)")

_NO_HIT_ANSWER = (
    "在所选文档的知识库内容中未找到与问题直接相关的段落。"
    "请尝试换关键词，或扩大文档范围。"
)


def _parse_ids(ids: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(x) for x in ids]


def _rag_clients_for_qa(db: Session, user: User) -> list[RagflowClient]:
    from app.services.model_settings_service import get_ragflow_api_key
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

    # 用户 KnowFlow 客户端优先，减少无效 fallback 探活
    kf = knowledge.client_for_user(db, user)
    if hasattr(kf, "_rag"):
        _add(kf._rag)
    auth = get_user_ragflow_auth(db, user)
    if auth:
        _add(RagflowClient(session_auth=auth))
    api_key = (get_ragflow_api_key(db) or "").strip()
    if api_key:
        _add(RagflowClient(api_key=api_key))
    priv = _privileged_rag_client(db)
    _add(priv)
    settings = get_settings()
    if settings.ragflow_api_key and settings.ragflow_api_key != api_key:
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
    platform_ids: set[str] = set()
    for h in hits:
        pid = _resolve_hit_platform_document_id(h, allowed, vmap)
        if pid:
            platform_ids.add(pid)
    docs_by_id: dict[str, Document] = {}
    if platform_ids:
        for doc in db.scalars(
            select(Document).where(
                Document.id.in_([uuid.UUID(x) for x in platform_ids])
            )
        ).all():
            docs_by_id[str(doc.id)] = doc
    version_by_doc: dict[str, DocumentVersion | None] = {}
    indexed_rag_id_by_doc: dict[str, str] = {}
    for pid, doc in docs_by_id.items():
        indexed = resolve_latest_indexed_version(db, doc)
        version_by_doc[pid] = indexed or resolve_current_version(db, doc)
        vl, _ = resolve_index_link(db, doc)
        if vl and (vl.ragflow_document_id or "").strip():
            indexed_rag_id_by_doc[pid] = str(vl.ragflow_document_id).strip()

    filtered: list[dict] = []
    for h in hits:
        rid = str(h.get("ragflow_document_id") or "")
        platform_id = _resolve_hit_platform_document_id(h, allowed, vmap)
        if not platform_id or platform_id not in docs_by_id:
            continue
        current = version_by_doc.get(platform_id)
        chunk_ver = (vmap.get(rid) or {}).get("document_version_id")
        indexed_rid = indexed_rag_id_by_doc.get(platform_id, "")
        if indexed_rid and rid and rid == indexed_rid:
            pass
        elif current and chunk_ver and chunk_ver != str(current.id):
            continue
        normalized = dict(h)
        normalized["document_id"] = platform_id
        filtered.append(normalized)
    return filtered


def _knowflow_retrieval_available(db: Session, user: User) -> bool:
    from app.integrations.ragflow_http import should_attempt_ragflow_http

    if not get_settings().knowflow_enabled:
        return False
    if not should_attempt_ragflow_http():
        return False
    return bool(_rag_clients_for_qa(db, user))


def _resolve_dataset_ids_for_ragflow_docs(
    db: Session, rag_doc_ids: list[str]
) -> list[str]:
    """按 RAGFlow 文档 ID 从索引链接表补全 dataset_id。"""
    ids = [str(x).strip() for x in rag_doc_ids if str(x).strip()]
    if not ids:
        return []
    dataset_ids: list[str] = []
    for row in db.scalars(
        select(RagflowDocumentVersionLink).where(
            RagflowDocumentVersionLink.ragflow_document_id.in_(ids)
        )
    ).all():
        ds = (row.dataset_id or "").strip()
        if ds:
            dataset_ids.append(ds)
    for row in db.scalars(
        select(RagflowDocumentLink).where(
            RagflowDocumentLink.ragflow_document_id.in_(ids)
        )
    ).all():
        ds = (row.dataset_id or "").strip()
        if ds:
            dataset_ids.append(ds)
    return list(dict.fromkeys(dataset_ids))


def _qa_retrieval_targets(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    *,
    docs_by_id: dict[str, Document] | None = None,
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
        doc = (docs_by_id or {}).get(pid)
        if not doc:
            try:
                doc = get_document(db, uuid.UUID(pid))
            except ValueError:
                continue
        if not doc:
            continue
        ds_id: str | None = None
        mirror = get_document_mirror_link(db, doc.id, user.id)
        if mirror and mirror.dataset_id:
            ds_id = str(mirror.dataset_id).strip()
        if not ds_id:
            vl, _ = resolve_index_link(db, doc)
            if vl and vl.dataset_id:
                ds_id = str(vl.dataset_id).strip()
        if not ds_id:
            link = _get_link(db, doc.id)
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
    from app.integrations.ragflow_http import should_attempt_ragflow_http

    dataset_ids, rag_doc_ids = _qa_retrieval_targets(
        db,
        user,
        doc_ids,
        docs_by_id={str(d.id): d for d in docs},
    )
    if not rag_doc_ids:
        return []
    if not dataset_ids:
        dataset_ids = _resolve_dataset_ids_for_ragflow_docs(db, rag_doc_ids)
    if not dataset_ids:
        return []

    settings = get_settings()
    top_k = max(1, min(int(limit), 20))
    threshold = float(settings.knowledge_retrieval_similarity_threshold or 0.32)
    if not should_attempt_ragflow_http():
        return []

    payload_kwargs = {
        "question": question,
        "dataset_ids": dataset_ids,
        "document_ids": rag_doc_ids or None,
        "top_k": top_k,
        "keyword": True,
        "highlight": True,
        "vector_similarity_weight": float(settings.knowledge_retrieval_vector_weight),
        "similarity_threshold": threshold,
    }
    for rag in _rag_clients_for_qa(db, user):
        try:
            raw = rag.retrieval(**payload_kwargs)
            hits = _filter_hits_by_version(db, user, raw, doc_ids)
            if hits:
                return hits[:top_k]
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
                "preview_available": False,
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
    limit: int | None = None,
    merge_nearby: bool = True,
) -> tuple[list[dict], str]:
    settings = get_settings()
    top_k = limit if limit is not None else int(settings.knowledge_retrieval_top_k or 5)
    top_k = max(1, min(top_k, 20))
    docs = validate_document_scope(
        db,
        user,
        doc_ids,
        min_count=1,
        max_count=20,
        required_level=PermissionLevel.query.value,
        allow_index_only=True,
    )

    from app.services.pageindex_service import (
        partition_documents_by_retrieval_engine,
        retrieve_pageindex_hits_for_qa,
    )

    pi_docs, kf_docs, skipped = partition_documents_by_retrieval_engine(db, docs)
    hits: list[dict] = []
    modes: list[str] = []
    kf_available = _knowflow_retrieval_available(db, user)
    total_knowflow_hits = 0

    # KnowFlow 文档优先走向量检索，避免被 PageIndex LLM 树搜索阻塞
    if kf_docs and kf_available:
        kf_ids = [d.id for d in kf_docs]
        kf_hits = _knowflow_retrieve(
            db, user, kf_docs, kf_ids, question, limit=top_k
        )
        if kf_hits:
            hits.extend(kf_hits)
            total_knowflow_hits += len(kf_hits)
            modes.append("hybrid")

    remaining = max(0, top_k - len(hits))
    pi_doc_ids_with_hits: set[str] = set()
    if pi_docs and remaining > 0:
        pi_hits = retrieve_pageindex_hits_for_qa(
            db, user, pi_docs, question, limit=remaining
        )
        if pi_hits:
            hits.extend(pi_hits)
            modes.append("pageindex_tree")
            pi_doc_ids_with_hits = {
                str(h.get("document_id"))
                for h in pi_hits
                if h.get("source") == "pageindex" and h.get("document_id")
            }

    # PageIndex 未命中时回退 KnowFlow / 本地（资讯网页等常双索引且 PageIndex 较新）
    fallback_docs = [
        doc for doc in pi_docs if str(doc.id) not in pi_doc_ids_with_hits
    ]
    remaining = max(0, top_k - len(hits))
    if fallback_docs and remaining > 0 and kf_available:
        fallback_ids = [d.id for d in fallback_docs]
        fb_hits = _knowflow_retrieve(
            db, user, fallback_docs, fallback_ids, question, limit=remaining
        )
        if fb_hits:
            hits.extend(fb_hits)
            total_knowflow_hits += len(fb_hits)
            if "hybrid" not in modes:
                modes.append("hybrid")

    remaining = max(0, top_k - len(hits))
    fallback_all = list(kf_docs) + fallback_docs + skipped
    if fallback_all and remaining > 0 and total_knowflow_hits == 0:
        fallback_ids = [d.id for d in fallback_all]
        local_hits = _local_retrieve(
            db, user, fallback_all, fallback_ids, question, limit=remaining
        )
        if local_hits:
            hits.extend(local_hits)
            modes.append("local")

    if merge_nearby:
        hits = merge_nearby_retrieval_hits(hits)
    hits = hits[:top_k]

    if len(modes) > 1:
        mode = "mixed"
    elif modes:
        mode = modes[0]
    elif hits:
        mode = "local"
    else:
        mode = "none"
    return hits, mode


def retrieval_workflow_title(mode: str) -> str:
    return {
        "pageindex_tree": "正在检索相关文档",
        "hybrid": "正在检索相关文档",
        "mixed": "正在检索相关文档",
        "local": "正在检索相关文档",
    }.get(mode, "正在检索相关文档")


def _doc_titles(db: Session, doc_ids: list[uuid.UUID]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for did in doc_ids:
        doc = get_document(db, did)
        if doc:
            titles[str(did)] = doc.title or "未命名文档"
    return titles


def _doc_citation_meta(db: Session, doc_ids: list[uuid.UUID]) -> dict[str, dict[str, Any]]:
    """引用卡片展示用：文件名与格式标签。"""
    from app.core.document_format import version_file_format_label
    from app.services.document_service import resolve_current_version
    from app.services.ragflow_version_link_service import resolve_latest_indexed_version

    meta: dict[str, dict[str, Any]] = {}
    for did in doc_ids:
        doc = get_document(db, did)
        if not doc:
            continue
        ver = resolve_latest_indexed_version(db, doc) or resolve_current_version(db, doc)
        file_name = (ver.file_name if ver else None) or doc.title or ""
        mime_type = ver.mime_type if ver else None
        meta[str(did)] = {
            "file_name": file_name,
            "file_format": version_file_format_label(file_name, mime_type),
        }
    return meta


def _normalize_highlight_snippet(text: str) -> str:
    """将检索高亮统一为 <em>…</em>，供前端溯源展示。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    if re.search(r"</?em\b", raw, flags=re.I):
        return raw
    patterns = (
        (r"<mark\b[^>]*>(.*?)</mark>", r"<em>\1</em>"),
        (
            r"<font\b[^>]*\bclass=['\"]highlight['\"][^>]*>(.*?)</font>",
            r"<em>\1</em>",
        ),
        (r"\*\*(.+?)\*\*", r"<em>\1</em>"),
    )
    for pattern, repl in patterns:
        raw = re.sub(pattern, repl, raw, flags=re.I | re.S)
    return raw


def _citation_preview_available(h: dict) -> bool:
    """是否可展示页级引用截图（真实 image_id、合成 ID、KnowFlow bbox，或 PageIndex 页码）。"""
    if h.get("preview_available") is True:
        return True
    if h.get("preview_available") is False:
        return False
    if str(h.get("source") or "").strip() == "pageindex":
        did = str(h.get("document_id") or "").strip()
        if did:
            return True
    anchor = h.get("anchor_json") or {}
    bbox = anchor.get("bbox")
    if isinstance(bbox, list) and len(bbox) >= 4:
        return True
    if RagflowClient.extract_chunk_image_id(h):
        return True
    if RagflowClient.synthesize_chunk_image_id(h):
        return True
    cid = str(h.get("chunk_id") or "").strip()
    ds_id = str(h.get("dataset_id") or "").strip()
    rid = str(h.get("ragflow_document_id") or "").strip()
    return bool(cid and ds_id and rid)


def _citation_image_id(h: dict) -> str | None:
    return (
        RagflowClient.extract_chunk_image_id(h)
        or RagflowClient.synthesize_chunk_image_id(h)
        or None
    )


def _citation_anchor_key(item: dict) -> tuple:
    anchor = item.get("anchor_json") or {}
    did = str(item.get("document_id") or "")
    page_raw = anchor.get("page")
    try:
        page = int(page_raw) if page_raw is not None else 0
    except (TypeError, ValueError):
        page = 0
    bbox = anchor.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            xs = [float(x) for x in bbox[:4]]
            cx = (xs[0] + xs[2]) / 2
            cy = (xs[1] + xs[3]) / 2
            return (did, page, int(cx // 96), int(cy // 96))
        except (TypeError, ValueError):
            pass
    chunk_id = str(item.get("chunk_id") or "")
    if chunk_id:
        return (did, page, chunk_id)
    return (did, page)


def merge_nearby_retrieval_hits(hits: list[dict]) -> list[dict]:
    """合并同文档同页/邻近位置的检索 hit，减少重复引用编号。"""
    if len(hits) <= 1:
        return hits
    best_by_key: dict[tuple, dict] = {}
    order: list[tuple] = []
    for h in hits:
        key = _citation_anchor_key(h)
        prev = best_by_key.get(key)
        if prev is None:
            best_by_key[key] = h
            order.append(key)
            continue
        if float(h.get("score") or 0) > float(prev.get("score") or 0):
            best_by_key[key] = h
    return [best_by_key[k] for k in order]


def _dedupe_indexes_by_document(
    nums: list[int],
    by_index: dict[int, dict],
) -> dict[int, int]:
    """同一句内：同一文档只保留 score 最高的引用编号。"""
    best_by_doc: dict[str, int] = {}
    best_score: dict[str, float] = {}
    for num in nums:
        cite = by_index.get(num)
        if not cite:
            continue
        did = str(cite.get("document_id") or f"__idx_{num}")
        score = float(cite.get("score") or 0)
        if did not in best_by_doc or score > best_score[did]:
            best_by_doc[did] = num
            best_score[did] = score
    remap: dict[int, int] = {}
    for num in nums:
        cite = by_index.get(num)
        if not cite:
            remap[num] = num
            continue
        did = str(cite.get("document_id") or f"__idx_{num}")
        remap[num] = best_by_doc.get(did, num)
    return remap


def _sentence_chunks(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？\n；])", text)
    return parts if parts else [text]


def _collapse_sentence_citations(sentence: str, by_index: dict[int, dict]) -> str:
    nums = [int(n) for n in _CITATION_REF_RE.findall(sentence)]
    if not nums:
        return sentence
    remap = _dedupe_indexes_by_document(nums, by_index)
    seen: set[int] = set()

    def _replace_one(match: re.Match[str]) -> str:
        num = int(match.group(1))
        primary = remap.get(num, num)
        if primary in seen:
            return ""
        seen.add(primary)
        return f"[{primary}]"

    collapsed = _CITATION_REF_RE.sub(_replace_one, sentence)
    return re.sub(r"  +", " ", collapsed)


def collapse_answer_citation_refs(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """同句内同一文档只保留最高 score 的引用；跨文档综合结论保留各文档一处。"""
    if not answer or not citations:
        return answer, citations

    by_index = {
        int(c["index"]): c for c in citations if c.get("index") is not None
    }
    if not by_index:
        return answer, citations

    normalized = "".join(
        _collapse_sentence_citations(chunk, by_index)
        if _CITATION_REF_RE.search(chunk)
        else chunk
        for chunk in _sentence_chunks(answer)
    )
    used = {int(n) for n in _CITATION_REF_RE.findall(normalized)}
    kept = [c for c in citations if int(c.get("index") or 0) in used]
    kept.sort(key=lambda c: int(c.get("index") or 0))
    return normalized, kept


def filter_citations_for_display(
    citations: list[dict],
    answer: str,
    *,
    max_fallback: int | None = None,
    max_per_document: int = 1,
) -> list[dict]:
    """仅展示回答正文中实际标注 [n] 的引用条目。"""
    if not citations:
        return []

    indexes = {
        int(n)
        for n in _CITATION_REF_RE.findall(answer or "")
        if str(n).isdigit() and int(n) > 0
    }
    if not indexes:
        return []

    pool = [c for c in citations if int(c.get("index") or 0) in indexes]
    pool.sort(key=lambda c: int(c.get("index") or 0))
    return pool


def finalize_citations_for_display(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """仅保留正文 [n] 实际引用的条目；未标注则不展示引用区。"""
    return finalize_citations_preserving_index(answer, citations)


def finalize_qa_answer_and_citations(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """过滤未使用的引用，并将正文与引用编号重排为连续的 1,2,3…"""
    answer = _strip_meta_footer(answer)
    return finalize_citations_for_display(answer, citations)


def strip_answer_source_narrative(text: str) -> str:
    """移除回答中不应出现的来源说明段落/章节。"""
    lines = (text or "").splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#+\s*", stripped):
            heading = re.sub(r"^#+\s*", "", stripped)
            if re.search(
                r"(参考来源|参考文献|资料来源|引用来源|参考文档|联网来源|来源说明|资料说明)",
                heading,
            ):
                break
        if re.search(
            r"(以上内容|本报告|下文)?(主要)?(参考|引用|依据)(了|自)?",
            stripped,
        ) and re.search(r"(文档|资料|检索|知识库|网页|联网|来源)", stripped):
            continue
        if re.search(r"^(\*\*)?(参考来源|数据来源|引用说明)", stripped):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _renumber_citations_sequential(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """将正文与引用列表的编号统一重排为连续的 1,2,3…"""
    if not citations:
        return answer, []
    old_indexes = sorted(
        {int(c.get("index") or 0) for c in citations if int(c.get("index") or 0) > 0}
    )
    if not old_indexes:
        return answer, []
    remap = {old: new for new, old in enumerate(old_indexes, start=1)}
    if remap == {i: i for i in old_indexes}:
        return answer, citations

    def _replace_ref(match: re.Match[str]) -> str:
        old = int(match.group(2))
        new = remap.get(old)
        if new is None:
            return match.group(0)
        return f"{match.group(1)}{new}{match.group(3)}"

    normalized = _CITATION_REF_REPLACE_RE.sub(_replace_ref, answer)
    renumbered: list[dict] = []
    for c in citations:
        old_idx = int(c.get("index") or 0)
        if old_idx not in remap:
            continue
        item = dict(c)
        item["index"] = remap[old_idx]
        renumbered.append(item)
    renumbered.sort(key=lambda c: int(c.get("index") or 0))
    return normalized, renumbered


def finalize_citations_preserving_index(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """过滤未使用引用，并将正文与引用编号重排为连续的 1,2,3…"""
    answer = strip_answer_source_narrative(answer)
    if not answer or not citations:
        return answer, []
    indexes = {
        int(n)
        for n in _CITATION_REF_RE.findall(answer)
        if str(n).isdigit() and int(n) > 0
    }
    if not indexes:
        return answer, []
    kept = [c for c in citations if int(c.get("index") or 0) in indexes]
    kept.sort(key=lambda c: int(c.get("index") or 0))
    return _renumber_citations_sequential(answer, kept)


def _extract_qa_context_body(hit: dict) -> str:
    for key in ("highlight", "snippet", "content"):
        raw = (hit.get(key) or "").strip()
        if not raw:
            continue
        if key == "highlight":
            return _normalize_highlight_snippet(raw)
        return raw
    return ""


def build_aligned_qa_context_and_citations(
    hits: list[dict],
    doc_titles: dict[str, str],
    *,
    question: str | None = None,
    doc_meta: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, list[dict]]:
    """构建与 citations 索引严格对齐的 LLM 上下文与引用列表。"""
    included: list[dict] = []
    blocks: list[str] = []
    for h in hits:
        body = _extract_qa_context_body(h)
        if not body:
            continue
        idx = len(included) + 1
        blocks.append(f"[{idx}]\n{body}")
        included.append(h)
    context = "\n\n".join(blocks)
    citations = build_citations(
        included, doc_titles, question=question, doc_meta=doc_meta
    )
    return context, citations


def build_citations(
    hits: list[dict],
    doc_titles: dict[str, str],
    *,
    question: str | None = None,
    doc_meta: dict[str, dict[str, Any]] | None = None,
) -> list[dict]:
    from app.integrations.citation_snippet import (
        format_citation_snippet,
        query_terms_for_highlight,
    )

    citations: list[dict] = []
    meta_by_doc = doc_meta or {}
    for i, h in enumerate(hits, start=1):
        did = str(h.get("document_id") or "")
        doc_info = meta_by_doc.get(did) or {}
        pre_snippet = (h.get("snippet") or "").strip()
        snippet = format_citation_snippet(
            highlight=h.get("highlight"),
            content=h.get("content") or pre_snippet,
            question=question,
        )
        if not snippet.strip():
            snippet = pre_snippet or _normalize_highlight_snippet(
                (h.get("highlight") or "").strip()
            )
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
                "image_id": _citation_image_id(h),
                "preview_available": _citation_preview_available(h),
                "highlight_terms": query_terms_for_highlight(question),
                "ragflow_document_id": h.get("ragflow_document_id"),
                "source": h.get("source") or "knowflow",
                "file_name": doc_info.get("file_name"),
                "file_format": doc_info.get("file_format"),
            }
        )
    return citations


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


def _build_qa_llm_messages(
    *,
    question: str,
    context: str,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> list[dict[str, str]]:
    from app.core.prompt_budget import build_bounded_qa_messages

    system = _qa_system_prompt(include_kg=include_kg)
    if insufficient_note:
        system += (
            "\n\n【材料不足】当前检索材料可能不足以完整回答。"
            f"不足方面：{insufficient_note}。"
            "请基于已有片段尽力回答；并在回答**末尾**用一小段明确、友好地提示用户可补充哪些具体信息"
            "（如时间范围、指标、文档范围），不要编造缺失数据。"
        )
    return build_bounded_qa_messages(system=system, question=question, context=context)


async def _iter_llm_answer_stream_parts(
    *,
    question: str,
    context: str,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> AsyncIterator[dict[str, str]]:
    from app.integrations.deepseek_client import chat_completion_stream_parts

    async for part in chat_completion_stream_parts(
        messages=_build_qa_llm_messages(
            question=question,
            context=context,
            include_kg=include_kg,
            insufficient_note=insufficient_note,
        ),
        temperature=0.2,
    ):
        yield part


async def _iter_llm_answer_stream(
    *,
    question: str,
    context: str,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> AsyncIterator[str]:
    async for part in _iter_llm_answer_stream_parts(
        question=question,
        context=context,
        include_kg=include_kg,
        insufficient_note=insufficient_note,
    ):
        if part.get("kind") == "content" and part.get("text"):
            yield part["text"]


def _call_llm_answer(
    *,
    question: str,
    context: str,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> str | None:
    from app.integrations.deepseek_client import chat_completion_sync

    messages = _build_qa_llm_messages(
        question=question,
        context=context,
        include_kg=include_kg,
        insufficient_note=insufficient_note,
    )
    return chat_completion_sync(
        messages=messages,
        temperature=0.2,
    )


def _strip_meta_footer(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if "以上内容来自" in line and "检索" in line:
            continue
        if "知识服务就绪" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


_MINDMAP_SYSTEM = (
    "你是知识结构分析助手。根据用户问题和 AI 回答，输出 Mermaid mindmap 语法。\n"
    "要求：\n"
    "- 仅输出 mindmap 代码，不要使用 ``` 围栏\n"
    "- 第一行必须是 mindmap，根节点形如 root((问题摘要))\n"
    "- 提炼 2-3 层要点分支，节点文字简短，使用简体中文\n"
    "- 节点中避免括号、引号、尖括号等特殊符号"
)


def _normalize_mindmap_source(text: str, *, question: str) -> str:
    raw = (text or "").strip()
    fenced = re.match(r"^```(?:mermaid)?\s*\n([\s\S]*?)\n```\s*$", raw, re.I)
    if fenced:
        raw = fenced.group(1).strip()
    if raw.lower().startswith("mindmap"):
        return raw
    root = (question or "检索要点").strip()[:36] or "检索要点"
    lines = [f"mindmap", f"  root(({root}))"]
    for line in raw.splitlines():
        label = line.strip().lstrip("-*# ").strip()
        if label:
            lines.append(f"    {label[:48]}")
    return "\n".join(lines)


def generate_knowledge_mindmap(*, question: str, answer: str) -> str | None:
    """对齐 KnowFlow：将检索回答结构化为 Mermaid 思维导图。"""
    question = (question or "").strip()
    answer = _strip_meta_footer(answer or "")
    if not answer:
        return None
    from app.integrations.deepseek_client import is_configured, resolve_credentials

    from app.core.prompt_budget import llm_completion_extras, truncate_to_budget

    if not is_configured():
        return None
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return None
    user_content = (
        f"问题：{question}\n\n"
        f"回答：\n{truncate_to_budget(answer, 6000)}"
    )
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _MINDMAP_SYSTEM},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.1,
                    **llm_completion_extras(),
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
            if not content:
                return None
            return _normalize_mindmap_source(content, question=question)
    except Exception as exc:
        logger.warning("知识检索思维导图生成失败: %s", exc)
        return None


def _fallback_answer(question: str, hits: list[dict], doc_titles: dict[str, str]) -> str:
    lines = [f"根据已选文档，与「{question}」相关的要点如下：", ""]
    for i, h in enumerate(hits, start=1):
        snippet = (h.get("highlight") or h.get("snippet") or "")[:400]
        lines.append(f"- {snippet} [{i}]")
    return "\n".join(lines)


def generate_answer(
    *,
    question: str,
    hits: list[dict],
    doc_titles: dict[str, str],
    context: str | None = None,
    include_kg: bool = False,
    insufficient_note: str | None = None,
) -> str:
    if context is None:
        context, _ = build_aligned_qa_context_and_citations(
            hits,
            doc_titles,
            question=question,
        )
    if not (context or "").strip():
        if insufficient_note:
            return f"{_NO_HIT_ANSWER}\n\n如需继续，请补充：{insufficient_note}"
        return _NO_HIT_ANSWER
    llm_answer = _call_llm_answer(
        question=question,
        context=context,
        include_kg=include_kg,
        insufficient_note=insufficient_note,
    )
    if llm_answer:
        return _strip_meta_footer(llm_answer)
    if hits:
        return _fallback_answer(question, hits, doc_titles)
    return _NO_HIT_ANSWER


def resolve_citation_image_id(
    db: Session,
    user: User,
    *,
    image_id: str | None = None,
    chunk_id: str | None = None,
    dataset_id: str | None = None,
    ragflow_document_id: str | None = None,
) -> str | None:
    """解析 KnowFlow 切片截图 ID（优先检索带回的 image_id，否则按 chunk 查询）。"""
    iid = (image_id or "").strip()
    if iid:
        return iid
    cid = (chunk_id or "").strip()
    ds_id = (dataset_id or "").strip()
    rid = (ragflow_document_id or "").strip()
    if not cid or not ds_id or not rid:
        return None
    for rag in _rag_clients_for_qa(db, user):
        if not rag.health_ok():
            continue
        try:
            resolved = rag.resolve_chunk_image_id(
                dataset_id=ds_id,
                ragflow_document_id=rid,
                chunk_id=cid,
            )
            if resolved:
                return resolved
        except RagflowError as exc:
            logger.debug("按 chunk 解析截图 ID 失败 chunk=%s: %s", cid, exc)
    return None


def _resolve_chunk_anchor_for_citation(
    db: Session,
    user: User,
    *,
    chunk_id: str | None,
    dataset_id: str | None,
    ragflow_document_id: str | None,
) -> dict[str, Any]:
    """从 KnowFlow 切片列表解析页码与 bbox（KnowFlow 无截图时的兜底）。"""
    cid = (chunk_id or "").strip()
    ds_id = (dataset_id or "").strip()
    rid = (ragflow_document_id or "").strip()
    if not cid or not ds_id or not rid:
        return {}
    for rag in _rag_clients_for_qa(db, user):
        if not rag.health_ok():
            continue
        try:
            page = 1
            while page <= 20:
                chunks, total, _ = rag.list_document_chunks(
                    ds_id, rid, page=page, page_size=50
                )
                for ch in chunks:
                    ch_id = str(ch.get("chunk_id") or ch.get("id") or "").strip()
                    if ch_id != cid:
                        continue
                    anchor = RagflowClient._parse_chunk_positions(ch.get("positions"))
                    page_no = anchor.get("page") or ch.get("page_num") or ch.get("page")
                    if page_no is not None:
                        anchor["page"] = int(page_no)
                    return anchor
                if page * 50 >= int(total or 0):
                    break
                page += 1
        except RagflowError as exc:
            logger.debug("解析切片锚点失败 chunk=%s: %s", cid, exc)
    return {}


def parse_citation_bbox_param(raw: str | None) -> list[float] | None:
    """解析 ?bbox=x0,y0,x1,y1 查询参数。"""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parts = [float(x.strip()) for x in text.split(",") if x.strip()]
    except ValueError:
        return None
    if len(parts) >= 4:
        return parts[:4]
    return None


def _resolve_platform_version_for_citation(
    db: Session,
    *,
    ragflow_document_id: str,
    platform_document_id: uuid.UUID | None = None,
) -> tuple[Document, DocumentVersion] | None:
    """按 RAGFlow 文档 ID 或平台文档 ID 定位可渲染 PDF 的版本。"""
    from app.models.ragflow_document_link import RagflowDocumentLink
    from app.models.document import DocumentVersion
    from app.services.document_service import resolve_current_version
    from app.services.ragflow_version_link_service import (
        get_version_link_by_ragflow_id,
        resolve_latest_indexed_version,
    )

    def _pick_version(doc: Document) -> DocumentVersion | None:
        if not doc or doc.deleted_at:
            return None
        ver = resolve_latest_indexed_version(db, doc) or resolve_current_version(db, doc)
        if ver and ver.file_key:
            return ver
        return None

    pid = platform_document_id
    if pid:
        doc = get_document(db, pid)
        ver = _pick_version(doc) if doc else None
        if doc and ver:
            return doc, ver

    rid = (ragflow_document_id or "").strip()
    if not rid:
        return None

    link = get_version_link_by_ragflow_id(db, rid)
    if link:
        doc = get_document(db, link.platform_document_id)
        ver = db.get(DocumentVersion, link.platform_version_id)
        if doc and ver and ver.file_key and not doc.deleted_at:
            return doc, ver

    doc_link = db.scalar(
        select(RagflowDocumentLink).where(RagflowDocumentLink.ragflow_document_id == rid)
    )
    if doc_link:
        doc = get_document(db, doc_link.platform_document_id)
        ver = _pick_version(doc) if doc else None
        if doc and ver:
            return doc, ver
    return None


def _fetch_citation_pdf_page_fallback(
    db: Session,
    user: User,
    *,
    chunk_id: str | None = None,
    dataset_id: str | None = None,
    ragflow_document_id: str | None = None,
    platform_document_id: uuid.UUID | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    bbox_format: str = "auto",
    highlight_text: str | None = None,
) -> tuple[bytes, str] | None:
    """从平台文档 PDF 渲染页图，并在 bbox 处绘制半透明高亮（兜底）。"""
    from app.core.permissions import PermissionLevel, can_access_document
    from app.integrations.citation_pdf_preview import render_pdf_page_image
    from app.integrations.html_document_export import convert_file_bytes_to_pdf_for_citation
    from app.storage.object_store import get_object_store

    rid = (ragflow_document_id or "").strip()
    if not rid and not platform_document_id:
        return None

    resolved = _resolve_platform_version_for_citation(
        db,
        ragflow_document_id=rid,
        platform_document_id=platform_document_id,
    )
    if not resolved:
        return None
    doc, version = resolved
    if not can_access_document(db, user, doc, PermissionLevel.query.value):
        return None
    try:
        raw = get_object_store().get_object_bytes(version.file_key)
    except Exception as exc:
        logger.debug("读取文档文件失败 doc=%s: %s", doc.id, exc)
        return None
    try:
        converted = convert_file_bytes_to_pdf_for_citation(
            version.file_name,
            raw,
            version.mime_type or "",
            title=doc.title or "",
        )
        if not converted:
            from app.integrations.html_document_export import (
                normalize_file_for_knowflow_upload,
            )

            norm = normalize_file_for_knowflow_upload(
                version.file_name,
                raw,
                version.mime_type or "",
                title=doc.title or "",
                description=getattr(doc, "description", None) or "",
            )
            if norm[1].startswith(b"%PDF"):
                converted = norm
        if not converted:
            return None
        _, pdf_bytes, _ = converted
    except Exception as exc:
        logger.debug("转换引用预览 PDF 失败 doc=%s: %s", doc.id, exc)
        return None
    if not pdf_bytes.startswith(b"%PDF"):
        return None

    anchor = {}
    if chunk_id and dataset_id and rid:
        anchor = _resolve_chunk_anchor_for_citation(
            db,
            user,
            chunk_id=chunk_id,
            dataset_id=dataset_id,
            ragflow_document_id=rid,
        )
    page_num = page or anchor.get("page") or 1
    highlight_bbox = bbox if isinstance(bbox, list) else anchor.get("bbox")
    fmt = bbox_format if bbox_format != "auto" else str(
        anchor.get("bbox_format") or "auto"
    )
    try:
        return render_pdf_page_image(
            pdf_bytes,
            page_num=int(page_num),
            bbox=highlight_bbox if isinstance(highlight_bbox, list) else None,
            bbox_format=fmt,
            highlight_bbox=True,
            crop_to_bbox=bool(
                isinstance(highlight_bbox, list) and len(highlight_bbox) >= 4
            ),
            highlight_text=highlight_text,
        )
    except Exception as exc:
        logger.debug("渲染引用页截图失败 doc=%s page=%s: %s", doc.id, page_num, exc)
        return None


def fetch_citation_preview_bytes(
    db: Session,
    user: User,
    *,
    image_id: str | None = None,
    chunk_id: str | None = None,
    dataset_id: str | None = None,
    ragflow_document_id: str | None = None,
    platform_document_id: uuid.UUID | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    bbox_format: str = "auto",
    highlight_text: str | None = None,
) -> tuple[bytes, str] | None:
    """获取引用截图：优先 KnowFlow /v1/document/image（与 KnowFlow 查看器同源），PDF 裁剪兜底。"""
    cid = (chunk_id or "").strip()
    ds_id = (dataset_id or "").strip()
    rid = (ragflow_document_id or "").strip()

    anchor: dict[str, Any] = {}
    if cid and ds_id and rid:
        anchor = _resolve_chunk_anchor_for_citation(
            db,
            user,
            chunk_id=cid,
            dataset_id=ds_id,
            ragflow_document_id=rid,
        )
    if page is not None:
        anchor["page"] = page
    if isinstance(bbox, list) and len(bbox) >= 4:
        anchor["bbox"] = bbox
    if bbox_format != "auto":
        anchor["bbox_format"] = bbox_format

    has_bbox = isinstance(anchor.get("bbox"), list) and len(anchor["bbox"]) >= 4
    fmt = str(anchor.get("bbox_format") or bbox_format or "auto")

    # 1) KnowFlow 切片截图（/v1/document/image，与 embed 查看器同源，区域最准）
    resolved = resolve_citation_image_id(
        db,
        user,
        image_id=image_id,
        chunk_id=chunk_id,
        dataset_id=dataset_id,
        ragflow_document_id=ragflow_document_id,
    )
    if resolved:
        from app.integrations.citation_pdf_preview import apply_image_highlight_wash

        for rag in _rag_clients_for_qa(db, user):
            if not rag.health_ok():
                continue
            try:
                body, content_type = rag.get_chunk_image(resolved)
                return apply_image_highlight_wash(body, content_type)
            except RagflowError as exc:
                logger.debug("获取 KnowFlow 引用截图失败 image=%s: %s", resolved, exc)

    # 2) 平台 PDF 页图兜底（KnowFlow 无图时；Word 等会先转为 PDF）
    fallback = _fetch_citation_pdf_page_fallback(
        db,
        user,
        chunk_id=cid or None,
        dataset_id=ds_id or None,
        ragflow_document_id=rid or None,
        platform_document_id=platform_document_id,
        page=anchor.get("page"),
        bbox=anchor.get("bbox") if has_bbox else None,
        bbox_format=fmt,
        highlight_text=highlight_text,
    )
    if fallback:
        return fallback

    # 3) 无法定位引用区域
    return None


def fetch_citation_image_bytes(
    db: Session, user: User, image_id: str
) -> tuple[bytes, str] | None:
    return fetch_citation_preview_bytes(db, user, image_id=image_id)


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


def _begin_knowledge_qa_stream(
    db: Session,
    user_id: uuid.UUID,
    *,
    question: str,
    session_id: str | None,
    document_ids: list[str] | None,
) -> dict[str, Any]:
    from app.core.async_db import resolve_db_user
    from app.core.user_messages import (
        KNOWLEDGE_SERVICE_UNAVAILABLE,
        http_exception_message,
    )
    from fastapi import HTTPException

    user = resolve_db_user(db, user_id)
    try:
        session = _resolve_qa_session(
            db,
            user,
            session_id=session_id,
            document_ids=document_ids,
        )
    except HTTPException as exc:
        return {
            "error": http_exception_message(exc, fallback=KNOWLEDGE_SERVICE_UNAVAILABLE)
            or "请求失败"
        }
    except Exception:
        import logging

        logging.getLogger(__name__).exception("knowledge qa session begin failed")
        return {"error": KNOWLEDGE_SERVICE_UNAVAILABLE}

    db.add(RagMessage(session_id=session.id, role="user", content=question))
    db.flush()
    db.commit()
    return {
        "session_id": session.id,
        "doc_ids": _parse_ids(session.document_ids),
    }


def _gather_qa_agentic(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[str],
    question: str,
    *,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    from app.core.async_db import resolve_db_user
    from app.services.knowledge_agentic_service import (
        RESULT_MARKER,
        AgenticQaGatherResult,
        iter_gather_for_knowledge_qa,
    )

    user = resolve_db_user(db, user_id)
    agentic: AgenticQaGatherResult | None = None
    for item in iter_gather_for_knowledge_qa(db, user, doc_ids, question, emit=emit):
        if RESULT_MARKER in item:
            agentic = item[RESULT_MARKER]
    if agentic is None:
        agentic = AgenticQaGatherResult(
            hits=[],
            mode="none",
            kg_ctx=None,
            plan_reasoning="",
            rounds_used=0,
            sub_questions=[question],
        )
    return agentic


def _gather_qa_simple(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[str],
    question: str,
) -> AgenticQaGatherResult:
    from app.core.async_db import resolve_db_user
    from app.services.knowledge_agentic_service import AgenticQaGatherResult

    user = resolve_db_user(db, user_id)
    hits: list[dict] = []
    mode = "none"
    if doc_ids:
        hits, mode = retrieve_hits_for_qa(db, user, doc_ids, question)
    kg_ctx = _resolve_kg_qa_context(db, user, question)
    return AgenticQaGatherResult(
        hits=hits,
        mode=mode,
        kg_ctx=kg_ctx,
        plan_reasoning="",
        rounds_used=1,
        sub_questions=[question],
    )


def _prepare_qa_stream_bundle(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[str],
    question: str,
    agentic: AgenticQaGatherResult,
) -> dict[str, Any]:
    from app.core.async_db import resolve_db_user
    from app.services.kg_service import merge_kg_qa_into_context
    from app.services.knowledge_agent_service import (
        format_changelog_context,
        format_diff_summary_context,
        load_version_changelogs,
        load_version_diff_summaries,
        plan_knowledge_query,
    )

    user = resolve_db_user(db, user_id)
    hits = agentic.hits
    mode = agentic.mode
    kg_ctx = agentic.kg_ctx
    doc_titles = _doc_titles(db, doc_ids)
    doc_meta = _doc_citation_meta(db, doc_ids)
    context, all_citations = build_aligned_qa_context_and_citations(
        hits,
        doc_titles,
        question=question,
        doc_meta=doc_meta,
    )
    context, all_citations = merge_kg_qa_into_context(context, all_citations, kg_ctx)
    include_kg = bool(kg_ctx and kg_ctx.context_text)
    kf = knowledge.client_for_user(db, user)
    plan = plan_knowledge_query(
        question=question,
        document_count=len(doc_ids),
        knowflow_available=bool(kf.enabled()),
    )
    if agentic.plan_reasoning:
        plan = {**plan, "agentic_reasoning": agentic.plan_reasoning}
    changelogs = load_version_changelogs(db, doc_ids)
    diff_summaries = load_version_diff_summaries(db, doc_ids)
    prefix = _answer_prefix_blocks(
        plan=plan,
        changelog_block=format_changelog_context(changelogs, doc_titles),
        diff_summary_block=format_diff_summary_context(diff_summaries, doc_titles),
    )
    return {
        "context": context,
        "all_citations": all_citations,
        "include_kg": include_kg,
        "prefix": prefix,
        "mode": mode,
        "insufficient_note": agentic.insufficient_note,
        "kg_ctx": kg_ctx,
        "hits": hits,
        "doc_titles": doc_titles,
    }


def _persist_qa_assistant_turn(
    db: Session,
    *,
    session_id: uuid.UUID,
    answer: str,
    citations: list[dict],
) -> uuid.UUID:
    msg = RagMessage(
        session_id=session_id,
        role="assistant",
        content=answer,
        citations=citations,
    )
    db.add(msg)
    from datetime import datetime, timezone

    session = db.get(RagSession, session_id)
    if session:
        session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return session_id


async def iter_knowledge_qa_stream(
    *,
    user_id: uuid.UUID,
    question: str,
    session_id: str | None = None,
    document_ids: list[str] | None = None,
    use_agentic: bool = True,
) -> AsyncIterator[str]:
    from app.core.async_db import run_db_task
    from app.services.knowledge_agentic_service import agentic_enabled

    question = question.strip()
    if not question:
        yield json.dumps({"error": "问题不能为空"}, ensure_ascii=False)
        return

    begin = await run_db_task(
        _begin_knowledge_qa_stream,
        user_id,
        question=question,
        session_id=session_id,
        document_ids=document_ids,
    )
    if begin.get("error"):
        yield json.dumps({"error": begin["error"]}, ensure_ascii=False)
        return

    session_id_val = begin["session_id"]
    doc_ids = begin["doc_ids"]

    if use_agentic and agentic_enabled():
        loop = asyncio.get_running_loop()
        event_q: asyncio.Queue[Any] = asyncio.Queue()
        gather_holder: dict[str, Any] = {}

        def emit_workflow(ev: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(event_q.put_nowait, ev)

        async def run_agentic_gather() -> None:
            try:
                gather_holder["agentic"] = await run_db_task(
                    _gather_qa_agentic,
                    user_id,
                    doc_ids,
                    question,
                    emit=emit_workflow,
                )
            finally:
                loop.call_soon_threadsafe(event_q.put_nowait, None)

        gather_task = asyncio.create_task(run_agentic_gather())
        while True:
            item = await event_q.get()
            if item is None:
                break
            yield json.dumps({"workflow": item}, ensure_ascii=False)
            await asyncio.sleep(0)
        await gather_task
        agentic = gather_holder.get("agentic")
        if agentic is None:
            from app.services.knowledge_agentic_service import AgenticQaGatherResult

            agentic = AgenticQaGatherResult(
                hits=[],
                mode="none",
                kg_ctx=None,
                plan_reasoning="",
                rounds_used=0,
                sub_questions=[question],
            )
    else:
        yield json.dumps(
            {"workflow": {"phase": "workflow_started", "title": "开始检索"}},
            ensure_ascii=False,
        )
        await asyncio.sleep(0)
        yield json.dumps(
            {"workflow": {"phase": "node_started", "title": "正在检索相关文档"}},
            ensure_ascii=False,
        )
        await asyncio.sleep(0)
        agentic = await run_db_task(_gather_qa_simple, user_id, doc_ids, question)

    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": "正在整理检索结果"}},
        ensure_ascii=False,
    )
    await asyncio.sleep(0)
    bundle = await run_db_task(
        _prepare_qa_stream_bundle, user_id, doc_ids, question, agentic
    )
    context = bundle["context"]
    all_citations = bundle["all_citations"]
    include_kg = bundle["include_kg"]
    prefix = bundle["prefix"]
    mode = bundle["mode"]
    kg_ctx = bundle["kg_ctx"]

    if kg_ctx and getattr(kg_ctx, "matched_entity_ids", None):
        yield json.dumps(
            {
                "workflow": {
                    "phase": "node_started",
                    "title": "正在解析本体图谱关联",
                }
            },
        ensure_ascii=False,
    )

    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": retrieval_workflow_title(mode)}},
        ensure_ascii=False,
    )
    await asyncio.sleep(0)

    answer_think_id = f"answer-{uuid.uuid4().hex[:8]}"
    yield json.dumps(
        {
            "workflow": {
                "phase": "agent_thinking",
                "title": "正在组织回答",
                "detail": "分析检索材料并生成回答…",
                "tool": "llm",
                "step_id": answer_think_id,
            }
        },
        ensure_ascii=False,
    )
    await asyncio.sleep(0)

    answer_parts: list[str] = []
    if prefix:
        answer_parts.append(prefix)
        yield json.dumps({"delta": prefix}, ensure_ascii=False)

    insufficient_note = bundle["insufficient_note"]
    if not (context or "").strip():
        yield json.dumps(
            {
                "workflow": {
                    "phase": "agent_thought",
                    "title": "无需生成回答",
                    "detail": "未检索到可用材料",
                    "tool": "llm",
                    "step_id": answer_think_id,
                    "status": "done",
                }
            },
            ensure_ascii=False,
        )
        if insufficient_note:
            insuff = (
                f"{_NO_HIT_ANSWER}\n\n"
                f"如需继续，请补充：{insufficient_note}"
            )
            answer_parts.append(insuff)
            yield json.dumps({"delta": insuff}, ensure_ascii=False)
        else:
            answer_parts.append(_NO_HIT_ANSWER)
            yield json.dumps({"delta": _NO_HIT_ANSWER}, ensure_ascii=False)
    else:
        from app.services.llm_workflow_stream import iter_llm_answer_events

        streamed = False
        async for ev in iter_llm_answer_events(
            messages=_build_qa_llm_messages(
                question=question,
                context=context,
                include_kg=include_kg,
                insufficient_note=insufficient_note,
            ),
            temperature=0.2,
            think_title="正在组织回答",
            think_detail="分析检索材料并生成回答…",
            step_id=answer_think_id,
            skip_initial_thinking=True,
        ):
            if ev.get("type") == "workflow":
                yield json.dumps({"workflow": ev["data"]}, ensure_ascii=False)
                await asyncio.sleep(0)
            elif ev.get("type") == "delta" and ev.get("text"):
                streamed = True
                answer_parts.append(ev["text"])
                yield json.dumps({"delta": ev["text"]}, ensure_ascii=False)
        if not streamed:
            yield json.dumps(
                {
                    "workflow": {
                        "phase": "agent_thought",
                        "title": "模型未返回内容",
                        "detail": "使用检索摘要回退",
                        "tool": "llm",
                        "step_id": answer_think_id,
                        "status": "done",
                    }
                },
                ensure_ascii=False,
            )
            hits = bundle["hits"]
            doc_titles = bundle["doc_titles"]
            fallback = (
                _fallback_answer(question, hits, doc_titles)
                if hits
                else _NO_HIT_ANSWER
            )
            answer_parts.append(fallback)
            yield json.dumps({"delta": fallback}, ensure_ascii=False)

    answer = _strip_meta_footer("".join(answer_parts))
    answer, citations = finalize_qa_answer_and_citations(answer, all_citations)

    if citations:
        yield json.dumps({"citations": citations}, ensure_ascii=False)

    await run_db_task(
        _persist_qa_assistant_turn,
        session_id=session_id_val,
        answer=answer,
        citations=citations,
    )

    yield json.dumps(
        {"workflow": {"phase": "workflow_finished", "title": "完成"}},
        ensure_ascii=False,
    )

    yield json.dumps(
        {
            "done": True,
            "reply": answer,
            "citations": citations,
            "conversation_id": str(session_id_val),
        },
        ensure_ascii=False,
    )


def answer_knowledge_question(
    db: Session,
    session: RagSession,
    user: User,
    question: str,
    *,
    use_agentic: bool = True,
) -> RagMessage:
    question = question.strip()
    if not question:
        from app.core.exceptions import bad_request

        raise bad_request("问题不能为空")

    db.add(RagMessage(session_id=session.id, role="user", content=question))
    db.flush()

    doc_ids = _parse_ids(session.document_ids)
    from app.services.knowledge_agentic_service import (
        AgenticQaGatherResult,
        agentic_enabled,
        gather_for_knowledge_qa,
    )

    if use_agentic and agentic_enabled():
        agentic = gather_for_knowledge_qa(db, user, doc_ids, question)
    else:
        hits: list[dict] = []
        mode = "none"
        if doc_ids:
            hits, mode = retrieve_hits_for_qa(db, user, doc_ids, question)
        kg_ctx = _resolve_kg_qa_context(db, user, question)
        agentic = AgenticQaGatherResult(
            hits=hits,
            mode=mode,
            kg_ctx=kg_ctx,
            plan_reasoning="",
            rounds_used=1,
            sub_questions=[question],
        )
    hits = agentic.hits
    doc_titles = _doc_titles(db, doc_ids)
    doc_meta = _doc_citation_meta(db, doc_ids)
    kg_ctx = agentic.kg_ctx
    context, all_citations = build_aligned_qa_context_and_citations(
        hits,
        doc_titles,
        question=question,
        doc_meta=doc_meta,
    )
    from app.services.kg_service import merge_kg_qa_into_context

    context, all_citations = merge_kg_qa_into_context(
        context, all_citations, kg_ctx
    )
    include_kg = bool(kg_ctx and kg_ctx.context_text)
    answer = generate_answer(
        question=question,
        hits=hits,
        doc_titles=doc_titles,
        context=context,
        include_kg=include_kg,
        insufficient_note=agentic.insufficient_note,
    )

    from app.services.knowledge_agent_service import (
        enrich_answer_with_plan,
        format_changelog_context,
        format_diff_summary_context,
        load_version_changelogs,
        load_version_diff_summaries,
        plan_knowledge_query,
    )

    kf = knowledge.client_for_user(db, user)
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
    answer, citations = finalize_qa_answer_and_citations(answer, all_citations)

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
