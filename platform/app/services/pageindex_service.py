"""PageIndex 树形索引与知识检索集成（独立于 KnowFlow 向量库）。

职责：
- 本地 workspace 建树（``execute_pageindex_reindex``）
- 按文档选择检索后端（``effective_retrieval_engine``）
- 树搜索问答片段（供 ``knowledge_qa_service`` 调用）

栈启用检查复用 ``knowledge_parser_service.assert_index_stack_ready``，
不在此重复 ``pageindex_enabled`` 判断逻辑。详见 knowledge-implementation.md §4.3。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import bad_request, forbidden, not_found
from app.core.permissions import PermissionLevel
from app.integrations.deepseek_client import is_configured
from app.integrations.pageindex_bridge import (
    count_tree_nodes,
    create_node_mapping,
    index_file_with_pageindex,
    is_pageindex_supported_file,
    load_pageindex_doc,
    pageindex_package_available,
    pageindex_stack_block_reason,
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

_PAGEINDEX_TREE_SEARCH_MAX_WORKERS = 4

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
    from app.services.knowledge_parser_service import PARSER_PAGEINDEX

    if not link:
        return None
    status = "已索引" if link.index_completed_at else "索引中"
    parse_message = link.error_message or "已建立文档索引"
    if link.error_message and not link.index_completed_at:
        status = "索引失败"
    elif link.index_completed_at:
        doc_id = (link.pageindex_doc_id or "").strip()
        if doc_id and not load_pageindex_doc(pageindex_workspace_dir(), doc_id):
            status = "索引失效"
            parse_message = "PageIndex 索引文件不可读（API/Worker 未共享存储时请重新索引）"
    return {
        "knowledge_synced": bool(link.index_completed_at) and status != "索引失效",
        "parse_status": status,
        "parse_progress": None,
        "parse_message": parse_message,
        "chunk_count": link.node_count,
        "ragflow_document_id": None,
        "indexed_version_id": str(link.platform_version_id)
        if link.platform_version_id
        else None,
        "indexed_version_no": link.version_no,
        "index_engine": PARSER_PAGEINDEX,
        "parser_id": PARSER_PAGEINDEX,
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


def load_deepdoc_markdown_for_pageindex(
    db: Session,
    user: User,
    doc: Document,
    *,
    version_id: uuid.UUID | None = None,
) -> str | None:
    """DeepDOC 解析完成后，用 KnowFlow 切片正文供 PageIndex（比 PDF 目录 LLM 更快）。"""
    from app.services.knowledge_library_service import list_document_chunks

    title = (doc.title or "文档").strip() or "文档"
    parts: list[str] = [f"# {title}"]
    page = 1
    try:
        while True:
            data = list_document_chunks(
                db,
                user,
                doc.id,
                version_id=version_id,
                page=page,
                page_size=100,
            )
            items = data.get("items") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                text = (
                    item.get("content")
                    or item.get("content_with_weight")
                    or item.get("text")
                    or ""
                ).strip()
                if text:
                    parts.append(text)
            total = int(data.get("total") or 0)
            if not items or page * 100 >= total:
                break
            page += 1
    except Exception as exc:
        logger.debug("读取 DeepDOC 切片供 PageIndex 跳过 doc=%s: %s", doc.id, exc)
        return None

    body = "\n\n".join(parts).strip()
    return body if len(body) >= 80 else None


def build_subscription_article_markdown_from_payload(payload: dict | None) -> str | None:
    """资讯导入任务 payload 中的 HTML 正文，供 PageIndex 跳过 PDF 目录 LLM。"""
    if not payload:
        return None
    html_body = (payload.get("article_html_body") or "").strip()
    if not html_body:
        return None
    from app.integrations.html_document_export import build_substantive_article_markdown

    title = (
        (payload.get("article_title") or payload.get("document_title") or "")
        .strip()
        or "文档"
    )
    md = build_substantive_article_markdown(
        title,
        html_body,
        summary=(payload.get("article_summary") or "").strip(),
        link=(payload.get("article_link") or "").strip(),
        source_label=(payload.get("article_source_label") or "").strip(),
    )
    body = md.strip()
    return body if len(body) >= 80 else None


def resolve_pageindex_markdown_for_reindex(
    db: Session,
    user: User,
    doc: Document,
    *,
    version_id: uuid.UUID | None = None,
) -> str | None:
    """重新索引时优先用 KnowFlow/DeepDOC 切片，跳过 PDF 目录 LLM。"""
    markdown_text = load_deepdoc_markdown_for_pageindex(
        db, user, doc, version_id=version_id
    )
    if markdown_text:
        logger.info("PageIndex 重新索引使用 DeepDOC 切片 Markdown doc=%s", doc.id)
        return markdown_text
    return None


def resolve_pageindex_markdown_for_subscription(
    db: Session,
    user: User,
    doc: Document,
    *,
    version_id: uuid.UUID | None = None,
    job_payload: dict | None = None,
) -> str | None:
    """优先 DeepDOC 切片，其次资讯 HTML 转 Markdown，否则回退 PDF 索引。"""
    markdown_text = load_deepdoc_markdown_for_pageindex(
        db, user, doc, version_id=version_id
    )
    if markdown_text:
        logger.info("PageIndex 使用 DeepDOC 切片 Markdown doc=%s", doc.id)
        return markdown_text
    markdown_text = build_subscription_article_markdown_from_payload(job_payload)
    if markdown_text:
        logger.info("PageIndex 使用资讯原文 Markdown doc=%s", doc.id)
        return markdown_text
    logger.info("PageIndex 无 Markdown 可用，回退 PDF 索引 doc=%s", doc.id)
    return None


def execute_pageindex_reindex(
    db: Session,
    user: User,
    document_id: uuid.UUID,
    *,
    version_id: uuid.UUID | None = None,
    markdown_text: str | None = None,
) -> dict:
    """为指定版本构建 PageIndex 树形索引（不经过 KnowFlow）。"""
    from app.services.documents.content import read_document_file_bytes
    from app.services.knowledge_parser_service import (
        PARSER_PAGEINDEX,
        assert_index_stack_ready,
    )

    assert_index_stack_ready(PARSER_PAGEINDEX)
    block_reason = pageindex_stack_block_reason()
    if block_reason:
        raise bad_request(block_reason)

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
    mime = version.mime_type or ""
    if not is_pageindex_supported_file(file_name, mime):
        raise bad_request(
            "该格式暂不支持索引。请使用 PDF、Markdown、Word（.doc/.docx）或纯文本（.txt），"
            "并确认文件扩展名正确。"
        )

    if not (markdown_text and markdown_text.strip()):
        markdown_text = resolve_pageindex_markdown_for_reindex(
            db, user, doc, version_id=version.id
        )

    content, _, mime = read_document_file_bytes(db, user, doc, version_id=version.id)
    doc_title = doc.title or file_name.rsplit(".", 1)[0]
    temp_paths: list[Path] = []
    if markdown_text and markdown_text.strip():
        from app.integrations.pageindex_bridge import write_temp_file

        md_path = write_temp_file(
            markdown_text.strip().encode("utf-8"),
            f"{doc_title}.md",
        )
        index_path = md_path
        temp_paths.append(md_path)
    else:
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
            "parser_id": PARSER_PAGEINDEX,
            "index_engine": PARSER_PAGEINDEX,
            "pageindex_doc_id": link.pageindex_doc_id,
            "node_count": node_count,
            "message": "文档索引已完成",
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
        raise bad_request(f"文档索引失败：{exc}") from exc
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
    from app.integrations.deepseek_client import chat_completion_sync

    messages = []
    if system.strip():
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})
    content = chat_completion_sync(
        messages=messages,
        temperature=temperature,
        timeout=120.0,
    )
    if not content:
        raise RuntimeError("语言模型未返回有效内容")
    return content


def _node_page(node: dict) -> int | None:
    for key in ("page_index", "start_index", "start_page"):
        value = node.get(key)
        if isinstance(value, int):
            return value
    return None


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


@dataclass(frozen=True)
class _PageIndexTreeSearchJob:
    doc: Document
    structure: Any


def _collect_pageindex_tree_search_jobs(
    db: Session,
    docs: list[Document],
) -> list[_PageIndexTreeSearchJob]:
    workspace = pageindex_workspace_dir()
    jobs: list[_PageIndexTreeSearchJob] = []
    for doc in docs:
        if effective_retrieval_engine(db, doc) != "pageindex":
            continue
        link = get_ready_link_for_document(db, doc)
        if not link or not link.pageindex_doc_id:
            continue
        stored = load_pageindex_doc(workspace, link.pageindex_doc_id) or {}
        structure = stored.get("structure") or []
        if structure:
            jobs.append(_PageIndexTreeSearchJob(doc=doc, structure=structure))
    return jobs


def _pageindex_hits_for_document(
    doc: Document,
    structure: Any,
    node_list: list[str],
) -> list[dict]:
    mapping = create_node_mapping(structure)
    hits: list[dict] = []
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
        hits.append(
            {
                "document_id": str(doc.id),
                "content": text,
                "snippet": text[:500],
                "source": "pageindex",
                "anchor_json": anchor,
                "node_id": node_id,
                "section_title": title or None,
                "preview_available": True,
            }
        )
    return hits


def _run_pageindex_tree_search_job(
    job: _PageIndexTreeSearchJob,
    question: str,
) -> tuple[str, list[str] | None]:
    try:
        node_list, _thinking = _tree_search_single_document(job.structure, question)
        return str(job.doc.id), node_list
    except Exception as exc:
        logger.warning("PageIndex 树搜索失败 doc=%s: %s", job.doc.id, exc)
        return str(job.doc.id), None


def _merge_pageindex_tree_search_results(
    docs: list[Document],
    jobs_by_doc_id: dict[str, _PageIndexTreeSearchJob],
    node_lists_by_doc_id: dict[str, list[str]],
    *,
    limit: int,
) -> list[dict]:
    hits: list[dict] = []
    for doc in docs:
        doc_id = str(doc.id)
        job = jobs_by_doc_id.get(doc_id)
        node_list = node_lists_by_doc_id.get(doc_id)
        if not job or not node_list:
            continue
        hits.extend(_pageindex_hits_for_document(doc, job.structure, node_list))
        if len(hits) >= limit:
            return hits[:limit]
    return hits[:limit]


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

    jobs = _collect_pageindex_tree_search_jobs(db, docs)
    if not jobs:
        return []

    jobs_by_doc_id = {str(job.doc.id): job for job in jobs}

    if len(jobs) == 1:
        doc_id, node_list = _run_pageindex_tree_search_job(jobs[0], question)
        if not node_list:
            return []
        job = jobs_by_doc_id[doc_id]
        return _pageindex_hits_for_document(job.doc, job.structure, node_list)[:limit]

    max_workers = min(_PAGEINDEX_TREE_SEARCH_MAX_WORKERS, len(jobs))
    node_lists_by_doc_id: dict[str, list[str]] = {}
    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="pageindex-tree",
    ) as pool:
        futures = {
            pool.submit(_run_pageindex_tree_search_job, job, question): job
            for job in jobs
        }
        for future in as_completed(futures):
            doc_id, node_list = future.result()
            if node_list:
                node_lists_by_doc_id[doc_id] = node_list

    return _merge_pageindex_tree_search_results(
        docs,
        jobs_by_doc_id,
        node_lists_by_doc_id,
        limit=limit,
    )
