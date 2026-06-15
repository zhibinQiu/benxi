"""PageIndex 实验性索引与树搜索检索（独立于 KnowFlow 向量库）。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import PermissionLevel
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.integrations.pageindex_bridge import (
    PAGEINDEX_SUPPORTED_SUFFIXES,
    build_pageindex_client,
    count_tree_nodes,
    create_node_mapping,
    index_file_with_pageindex,
    is_pageindex_supported_file,
    load_pageindex_doc,
    pageindex_import_error,
    pageindex_package_available,
    pageindex_supported_formats,
    prepare_pageindex_index_path,
    remove_fields,
)
from app.models.document import Document, DocumentVersion
from app.models.org import User
from app.models.pageindex_version_link import PageindexVersionLink
from app.services.compare_service import validate_document_scope
from app.services.document_service import get_document, resolve_current_version
from app.services.ragflow_version_link_service import resolve_index_link

logger = logging.getLogger(__name__)

_SUPPORTED_SUFFIXES = PAGEINDEX_SUPPORTED_SUFFIXES  # re-export for tests
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)

_TREE_SEARCH_PROMPT = """\
你是文档检索助手。根据用户问题，在下列文档树结构中找到最可能包含答案的节点。

问题：{question}

文档树（JSON，节点含 node_id、title、summary 等，不含正文）：
{tree_json}

请仅返回 JSON，格式如下：
{{
  "thinking": "简要推理过程",
  "node_list": ["node_id_1", "node_id_2"]
}}
"""

_ANSWER_PROMPT = """\
根据下列检索到的文档片段回答问题。仅依据片段内容，使用简体中文，条理清晰。

问题：{question}

片段：
{context}

若片段不足以回答，请明确说明。
"""


def _platform_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def pageindex_workspace_dir() -> Path:
    settings = get_settings()
    raw = (settings.pageindex_workspace_dir or "").strip()
    if raw:
        path = Path(raw).expanduser()
    else:
        path = _platform_dir() / ".run" / "pageindex"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_meta() -> dict:
    settings = get_settings()
    ws = pageindex_workspace_dir()
    hints: list[str] = []
    if not settings.pageindex_enabled:
        hints.append("PageIndex 功能已在配置中关闭")
    if not pageindex_package_available():
        err = pageindex_import_error()
        hints.append(
            "未安装自托管 PageIndex，索引不可用。"
            "执行：pip install -e ./third_party/pageindex-upstream"
        )
        if err:
            hints.append(f"导入错误：{err[:200]}")
    if not is_configured():
        hints.append("语言模型未配置，树搜索检索不可用")
    return {
        "enabled": bool(settings.pageindex_enabled),
        "package_available": pageindex_package_available(),
        "llm_configured": is_configured(),
        "workspace_dir": str(ws),
        "supported_formats": pageindex_supported_formats(),
        "hint": "；".join(hints) if hints else None,
    }


def get_version_link_by_version_id(
    db: Session, version_id: uuid.UUID
) -> PageindexVersionLink | None:
    return db.scalar(
        select(PageindexVersionLink).where(
            PageindexVersionLink.platform_version_id == version_id
        )
    )


def get_ready_link_for_document(
    db: Session, document: Document
) -> PageindexVersionLink | None:
    rows = list(
        db.scalars(
            select(PageindexVersionLink).where(
                PageindexVersionLink.platform_document_id == document.id
            )
        ).all()
    )
    ready = [r for r in rows if r.index_completed_at]
    if ready:
        return max(
            ready,
            key=lambda item: (item.version_no or 0, item.updated_at or item.created_at),
        )
    current = resolve_current_version(db, document)
    if current:
        for row in rows:
            if row.platform_version_id == current.id:
                return row
    return rows[0] if rows else None


def batch_pageindex_links_by_document(
    db: Session, doc_ids: list[uuid.UUID]
) -> dict[str, PageindexVersionLink | None]:
    if not doc_ids:
        return {}
    rows = list(
        db.scalars(
            select(PageindexVersionLink).where(
                PageindexVersionLink.platform_document_id.in_(doc_ids)
            )
        ).all()
    )
    grouped: dict[str, list[PageindexVersionLink]] = {}
    for row in rows:
        grouped.setdefault(str(row.platform_document_id), []).append(row)
    out: dict[str, PageindexVersionLink | None] = {}
    for doc_id in doc_ids:
        did = str(doc_id)
        candidates = grouped.get(did, [])
        ready = [r for r in candidates if r.index_completed_at]
        if ready:
            out[did] = max(
                ready,
                key=lambda item: (item.version_no or 0, item.updated_at or item.created_at),
            )
        elif candidates:
            out[did] = candidates[0]
        else:
            out[did] = None
    return out


def pageindex_index_meta(link: PageindexVersionLink | None) -> dict | None:
    if not link:
        return None
    status = "已索引" if link.index_completed_at else "索引中"
    if link.error_message and not link.index_completed_at:
        status = "索引失败"
    return {
        "knowledge_synced": bool(link.index_completed_at),
        "parse_status": status,
        "parse_progress": None,
        "parse_message": link.error_message or "PageIndex 树形索引（实验）",
        "chunk_count": link.node_count,
        "ragflow_document_id": None,
        "indexed_version_id": str(link.platform_version_id)
        if link.platform_version_id
        else None,
        "indexed_version_no": link.version_no,
        "index_engine": "pageindex",
        "parser_id": "pageindex",
    }


def pageindex_retrieval_available() -> bool:
    settings = get_settings()
    return bool(settings.pageindex_enabled and is_configured())


def resolve_retrieval_engine_for_document(db: Session, doc: Document) -> str:
    """按索引记录判断文档应使用的检索后端：pageindex | knowflow | none。"""
    from app.services.ragflow_version_link_service import (
        get_version_link_by_version_id,
        resolve_latest_indexed_version,
    )

    pi = get_ready_link_for_document(db, doc)
    workspace = pageindex_workspace_dir()
    pi_ready = bool(
        pi
        and pi.index_completed_at
        and (pi.pageindex_doc_id or "").strip()
        and load_pageindex_doc(workspace, pi.pageindex_doc_id)
    )
    rag_ver = resolve_latest_indexed_version(db, doc)
    rag_ready = bool(rag_ver)

    if not pi_ready and not rag_ready:
        return "none"
    if pi_ready and not rag_ready:
        return "pageindex"
    if rag_ready and not pi_ready:
        return "knowflow"

    rag_vl = get_version_link_by_version_id(db, rag_ver.id) if rag_ver else None
    rag_at = rag_vl.index_completed_at if rag_vl else None
    pi_at = pi.index_completed_at if pi else None
    if pi_at and rag_at:
        return "pageindex" if pi_at >= rag_at else "knowflow"
    return "pageindex" if pi_at else "knowflow"


def effective_retrieval_engine(db: Session, doc: Document) -> str:
    """考虑 PageIndex 运行时可用性后的实际检索后端。"""
    from app.services.ragflow_version_link_service import resolve_latest_indexed_version

    engine = resolve_retrieval_engine_for_document(db, doc)
    if engine != "pageindex":
        return engine
    if pageindex_retrieval_available():
        return "pageindex"
    if resolve_latest_indexed_version(db, doc):
        return "knowflow"
    return "none"


def partition_documents_by_retrieval_engine(
    db: Session, docs: list[Document]
) -> tuple[list[Document], list[Document], list[Document]]:
    """返回 (PageIndex 文档, KnowFlow 文档, 不可检索文档)。"""
    pi_docs: list[Document] = []
    kf_docs: list[Document] = []
    skipped: list[Document] = []
    for doc in docs:
        engine = effective_retrieval_engine(db, doc)
        if engine == "pageindex":
            pi_docs.append(doc)
        elif engine == "knowflow":
            kf_docs.append(doc)
        else:
            skipped.append(doc)
    return pi_docs, kf_docs, skipped


def _assert_pageindex_enabled() -> None:
    if not get_settings().pageindex_enabled:
        raise bad_request("PageIndex 功能未启用")


def _supported_file_name(file_name: str) -> bool:
    return is_pageindex_supported_file(file_name)


def _upsert_version_link(
    db: Session,
    *,
    document: Document,
    version: DocumentVersion,
    user: User,
    pageindex_doc_id: str,
    file_name: str,
    node_count: int | None,
    error_message: str | None = None,
    completed: bool = True,
) -> PageindexVersionLink:
    row = get_version_link_by_version_id(db, version.id)
    if row:
        row.pageindex_doc_id = pageindex_doc_id
        row.file_name = file_name
        row.node_count = node_count
        row.error_message = error_message
        row.index_completed_at = datetime.now(timezone.utc) if completed else None
        row.platform_user_id = user.id
    else:
        row = PageindexVersionLink(
            platform_document_id=document.id,
            platform_version_id=version.id,
            version_no=version.version_no,
            platform_user_id=user.id,
            pageindex_doc_id=pageindex_doc_id,
            file_name=file_name,
            node_count=node_count,
            error_message=error_message,
            index_completed_at=datetime.now(timezone.utc) if completed else None,
        )
        db.add(row)
    db.flush()
    return row


def execute_pageindex_reindex(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
) -> dict:
    """为指定版本构建 PageIndex 树形索引（不经过 KnowFlow）。"""
    from app.services.documents.content import read_document_file_bytes

    _assert_pageindex_enabled()
    if not pageindex_package_available():
        raise bad_request(
            "未安装自托管 PageIndex。请在 platform 目录执行："
            "pip install -e ./third_party/pageindex-upstream"
        )
    if not is_configured():
        raise bad_request("语言模型未配置，无法构建 PageIndex 索引")

    doc = get_document(db, document_id)
    if not doc or doc.deleted_at:
        raise not_found()
    _version_link, version = resolve_index_link(db, doc, version_id=version_id)
    if not version:
        raise bad_request("未找到可索引的文档版本")

    docs = validate_document_scope(
        db,
        user,
        [document_id],
        min_count=1,
        max_count=1,
        required_level=PermissionLevel.query.value,
    )
    if not docs:
        raise forbidden()

    file_name = version.file_name or "document"
    if not _supported_file_name(file_name):
        raise bad_request(
            "PageIndex 实验索引支持 PDF、Markdown、Word（.doc/.docx）与纯文本（.txt）"
        )

    content, _, mime = read_document_file_bytes(db, user, doc, version_id=version.id)
    doc_title = doc.title or file_name.rsplit(".", 1)[0]
    index_path, temp_paths = prepare_pageindex_index_path(
        content=content,
        file_name=file_name,
        mime_type=mime or "",
        title=doc_title,
    )
    workspace = pageindex_workspace_dir()
    try:
        settings = get_settings()
        model = (settings.pageindex_model or "").strip() or None
        pageindex_doc_id = index_file_with_pageindex(
            workspace=workspace,
            file_path=index_path,
            model=model,
        )
        stored = load_pageindex_doc(workspace, pageindex_doc_id) or {}
        node_count = count_tree_nodes(stored.get("structure"))
        link = _upsert_version_link(
            db,
            document=doc,
            version=version,
            user=user,
            pageindex_doc_id=pageindex_doc_id,
            file_name=file_name,
            node_count=node_count,
            completed=True,
        )
        return {
            "document_id": str(document_id),
            "version_id": str(version.id),
            "version_no": version.version_no,
            "parser_id": "pageindex",
            "index_engine": "pageindex",
            "pageindex_doc_id": link.pageindex_doc_id,
            "node_count": node_count,
            "message": "PageIndex 树形索引已完成",
        }
    except Exception as exc:
        logger.exception("PageIndex 索引失败 doc=%s", document_id)
        _upsert_version_link(
            db,
            document=doc,
            version=version,
            user=user,
            pageindex_doc_id="",
            file_name=file_name,
            node_count=None,
            error_message=str(exc)[:500],
            completed=False,
        )
        raise bad_request(f"PageIndex 索引失败：{exc}") from exc
    finally:
        for path in temp_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _parse_tree_search_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("树搜索返回为空")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))


def _call_llm_sync(*, system: str, user_content: str, temperature: float = 0.2) -> str:
    api_key, base_url, model = resolve_credentials()
    settings = get_settings()
    messages = []
    if system.strip():
        messages.append({"role": "system", "content": system})
    messages.append(
        {
            "role": "user",
            "content": user_content[: settings.deepseek_max_chars],
        }
    )
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )


async def _call_llm_stream(
    *, system: str, user_content: str, temperature: float = 0.2
) -> AsyncIterator[str]:
    api_key, base_url, model = resolve_credentials()
    settings = get_settings()
    messages = []
    if system.strip():
        messages.append({"role": "system", "content": system})
    messages.append(
        {
            "role": "user",
            "content": user_content[: settings.deepseek_max_chars],
        }
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta


def _node_page(node: dict) -> int | None:
    for key in ("page_index", "start_index", "start_page"):
        value = node.get(key)
        if isinstance(value, int):
            return value
    return None


def _collect_context_for_nodes(tree: Any, node_ids: list[str]) -> tuple[str, list[dict]]:
    mapping = create_node_mapping(tree)
    parts: list[str] = []
    nodes_out: list[dict] = []
    for node_id in node_ids:
        node = mapping.get(node_id)
        if not node:
            continue
        title = (node.get("title") or "").strip()
        text = (node.get("text") or node.get("summary") or "").strip()
        if not text:
            continue
        header = title or f"节点 {node_id}"
        parts.append(f"## {header}\n\n{text}")
        nodes_out.append(
            {
                "node_id": node_id,
                "title": title or None,
                "page": _node_page(node),
                "snippet": text[:400],
            }
        )
    return "\n\n".join(parts), nodes_out


def _tree_search_single_document(
    structure: Any,
    question: str,
) -> tuple[list[str], str]:
    tree_json = json.dumps(
        remove_fields(structure, fields={"text"}),
        ensure_ascii=False,
        indent=2,
    )
    prompt = _TREE_SEARCH_PROMPT.format(question=question, tree_json=tree_json)
    raw = _call_llm_sync(system="", user_content=prompt, temperature=0.0)
    parsed = _parse_tree_search_json(raw)
    thinking = str(parsed.get("thinking") or "").strip()
    node_list = [str(x) for x in (parsed.get("node_list") or []) if str(x).strip()]
    return node_list, thinking


def retrieve_pageindex_hits_for_qa(
    db: Session,
    user: User,
    docs: list[Document],
    question: str,
    *,
    limit: int = 5,
) -> list[dict]:
    """将 PageIndex 树搜索命中转为知识问答统一的 hit 结构。"""
    if not docs or limit <= 0:
        return []
    if not pageindex_retrieval_available():
        return []

    question = question.strip()
    if not question:
        return []

    workspace = pageindex_workspace_dir()
    hits: list[dict] = []
    for doc in docs:
        if effective_retrieval_engine(db, doc) != "pageindex":
            continue
        link = get_ready_link_for_document(db, doc)
        if not link or not link.pageindex_doc_id:
            continue
        stored = load_pageindex_doc(workspace, link.pageindex_doc_id) or {}
        structure = stored.get("structure") or []
        if not structure:
            continue
        try:
            node_list, _thinking = _tree_search_single_document(structure, question)
        except Exception as exc:
            logger.warning("PageIndex 树搜索失败 doc=%s: %s", doc.id, exc)
            continue
        mapping = create_node_mapping(structure)
        for node_id in node_list:
            node = mapping.get(node_id)
            if not node:
                continue
            text = (node.get("text") or node.get("summary") or "").strip()
            if not text:
                continue
            page = _node_page(node)
            title = (node.get("title") or "").strip()
            anchor: dict = {"page": page} if page else {}
            hit: dict = {
                "document_id": str(doc.id),
                "content": text,
                "snippet": text[:500],
                "source": "pageindex",
                "anchor_json": anchor,
                "node_id": node_id,
                "section_title": title or None,
            }
            if page:
                hit["preview_available"] = True
            hits.append(hit)
            if len(hits) >= limit:
                return hits[:limit]
    return hits[:limit]


def _resolve_search_targets(
    db: Session,
    user: User,
    document_ids: list[uuid.UUID],
) -> list[tuple[Document, PageindexVersionLink]]:
    docs = validate_document_scope(
        db,
        user,
        document_ids,
        min_count=1,
        max_count=5,
        required_level=PermissionLevel.query.value,
        allow_index_only=True,
    )
    targets: list[tuple[Document, PageindexVersionLink]] = []
    workspace = pageindex_workspace_dir()
    for doc in docs:
        link = get_ready_link_for_document(db, doc)
        if not link or not link.index_completed_at or not link.pageindex_doc_id:
            raise bad_request(f"文档「{doc.title or doc.id}」尚未完成 PageIndex 索引")
        if not load_pageindex_doc(workspace, link.pageindex_doc_id):
            raise bad_request(f"文档「{doc.title or doc.id}」的 PageIndex 索引文件缺失，请重新索引")
        targets.append((doc, link))
    return targets


def search_with_pageindex(
    db: Session,
    user: User,
    *,
    question: str,
    document_ids: list[str],
) -> dict:
    _assert_pageindex_enabled()
    if not is_configured():
        raise bad_request("语言模型未配置，无法进行 PageIndex 树搜索")

    question = question.strip()
    if not question:
        raise bad_request("问题不能为空")

    doc_uuids = [uuid.UUID(x) for x in document_ids]
    targets = _resolve_search_targets(db, user, doc_uuids)
    workspace = pageindex_workspace_dir()

    all_citations: list[dict] = []
    contexts: list[str] = []
    thinking_parts: list[str] = []
    node_ids_all: list[str] = []

    for doc, link in targets:
        stored = load_pageindex_doc(workspace, link.pageindex_doc_id) or {}
        structure = stored.get("structure") or []
        node_list, thinking = _tree_search_single_document(structure, question)
        if thinking:
            thinking_parts.append(f"【{doc.title or doc.id}】{thinking}")
        node_ids_all.extend(node_list)
        context, nodes = _collect_context_for_nodes(structure, node_list)
        if context:
            contexts.append(f"### 文档：{doc.title or doc.id}\n\n{context}")
        for idx, node in enumerate(nodes, start=len(all_citations) + 1):
            all_citations.append(
                {
                    "index": idx,
                    "document_id": str(doc.id),
                    "document_title": doc.title or "",
                    "node_id": node.get("node_id"),
                    "title": node.get("title"),
                    "page": node.get("page"),
                    "snippet": node.get("snippet"),
                }
            )

    merged_context = "\n\n".join(contexts).strip()
    if not merged_context:
        return {
            "answer": "在 PageIndex 树结构中未定位到与问题相关的章节，请换种问法或扩大文档范围。",
            "thinking": "\n".join(thinking_parts) or None,
            "retrieval_mode": "pageindex_tree",
            "citations": [],
            "node_ids": node_ids_all,
        }

    answer = _call_llm_sync(
        system="你是企业文档问答助手。",
        user_content=_ANSWER_PROMPT.format(question=question, context=merged_context),
        temperature=0.2,
    )
    return {
        "answer": answer,
        "thinking": "\n".join(thinking_parts) or None,
        "retrieval_mode": "pageindex_tree",
        "citations": all_citations,
        "node_ids": node_ids_all,
    }


async def iter_pageindex_search_stream(
    db: Session,
    user: User,
    *,
    question: str,
    document_ids: list[str],
) -> AsyncIterator[str]:
    try:
        result = search_with_pageindex(
            db, user, question=question, document_ids=document_ids
        )
    except Exception as exc:
        from app.core.exceptions import HTTPException
        from app.core.user_messages import sanitize_user_message

        msg = sanitize_user_message(str(exc), fallback="检索失败")
        if isinstance(exc, HTTPException):
            detail = exc.detail
            if isinstance(detail, dict):
                msg = str(detail.get("message") or msg)
            else:
                msg = str(detail)
        yield json.dumps({"error": msg}, ensure_ascii=False)
        return

    yield json.dumps(
        {
            "workflow": {
                "phase": "node_started",
                "title": "PageIndex 树搜索完成",
            }
        },
        ensure_ascii=False,
    )
    if result.get("thinking"):
        yield json.dumps(
            {"workflow": {"phase": "node_started", "title": "推理定位相关章节"}},
            ensure_ascii=False,
        )
    citations = result.get("citations") or []
    if citations:
        yield json.dumps({"citations": citations}, ensure_ascii=False)

    answer_prompt = result.get("answer") or ""
    # 已在 search_with_pageindex 生成完整答案；为兼容面板仍按 delta 推送
    chunk_size = 48
    for i in range(0, len(answer_prompt), chunk_size):
        yield json.dumps({"delta": answer_prompt[i : i + chunk_size]}, ensure_ascii=False)

    yield json.dumps(
        {
            "message": {
                "role": "assistant",
                "content": answer_prompt,
                "citations": citations,
            },
            "retrieval_mode": result.get("retrieval_mode"),
            "thinking": result.get("thinking"),
        },
        ensure_ascii=False,
    )
