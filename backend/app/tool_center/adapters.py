"""ToolCenter 底层适配 — 直连原子实现，不经 Skill 路由（避免循环）。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
    ATOMIC_TOOL_ONTOLOGY_QUERY,
)
from app.tool_center.context import ToolRuntimeContext

logger = logging.getLogger(__name__)


def _tool_result(ok: bool, summary: str, data: Any = None) -> tuple[bool, str, dict[str, Any] | None]:
    if isinstance(data, dict):
        return ok, summary, data
    if data is not None:
        return ok, summary, {"payload": data}
    return ok, summary, {}


def _firecrawl_scrape(url: str) -> str | None:
    """用 FireCrawl 抓取网页全文，返回 Markdown；FireCrawl 不可用时 fallback 到内置 web_article_fetcher。"""
    from app.services.model_settings_service import get_effective_model_config

    merged = get_effective_model_config()
    api_key = (merged.get("firecrawl_api_key") or "").strip()
    api_url = (merged.get("firecrawl_api_url") or "https://api.firecrawl.dev").rstrip("/")

    if api_key:
        try:
            import requests
            resp = requests.post(
                f"{api_url}/v1/scrape",
                json={"url": url, "formats": ["markdown"]},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            md = data.get("data", {}).get("markdown") or data.get("markdown")
            if md and isinstance(md, str) and md.strip():
                return md.strip()
        except Exception as exc:
            logger.debug("FireCrawl scrape failed %s: %s", url, exc)

    # Fallback: 内置 web_article_fetcher
    try:
        from app.integrations.web_article_fetcher import fetch_web_article
        entry = fetch_web_article(url, timeout=15.0)
        if entry and entry.content_html:
            from app.integrations.html_markdown import html_to_markdown
            return html_to_markdown(entry.content_html)
    except Exception as exc:
        logger.debug("web_article_fetcher fallback failed %s: %s", url, exc)
    return None


async def _enrich_items_with_full_text(items: list[dict], read_full: int) -> list[dict]:
    """并行抓取前 read_full 条链接的全文，附加到 items。"""
    targets = [(i, item) for i, item in enumerate(items[:read_full]) if item.get("url")]
    if not targets:
        return items

    async def _fetch_one(idx: int, item: dict) -> None:
        url = (item.get("url") or "").strip()
        if not url:
            return
        loop = asyncio.get_running_loop()
        full = await loop.run_in_executor(None, _firecrawl_scrape, url)
        if full:
            items[idx]["full_text"] = full

    await asyncio.gather(*[_fetch_one(idx, it) for idx, it in targets], return_exceptions=True)
    return items


async def _run_web_search(ctx: ToolRuntimeContext, params: dict[str, Any]) -> tuple[bool, str, dict | None]:
    query = str(params.get("query") or "").strip()
    max_items = int(params.get("max_items") or 8)
    read_full = int(params.get("read_full") or 3)
    from app.services.searxng_service import (
        SearxngNotConfiguredError,
        SearxngSearchError,
        search_web,
    )

    try:
        items, _ = search_web(query, page_size=max_items, db=ctx.db)
    except (SearxngNotConfiguredError, SearxngSearchError) as exc:
        return _tool_result(False, str(exc))
    except Exception as exc:
        return _tool_result(False, f"联网检索失败：{exc}")

    # Phase 1: 读前 N 条全文
    if read_full > 0 and items:
        items = await _enrich_items_with_full_text(items, read_full)
        read_count = sum(1 for it in items[:read_full] if it.get("full_text"))
    else:
        read_count = 0

    result: dict[str, Any] = {
        "query": query,
        "items": items,
        "read_full": read_count,
        "read_full_enabled": read_full > 0,
    }

    # Phase 3: 交叉验证（仅当 read_full >= 2 条时有意义）
    if read_full >= 2:
        verification = _cross_validate_items(items, top_n=read_full)
        if verification:
            result["verification"] = verification

    return _tool_result(
        True,
        f"联网检索返回 {len(items)} 条，已读全文 {read_count} 条",
        result,
    )


# ── Phase 3: 信息交叉验证 ──


def _extract_key_claims_from_text(text: str) -> list[dict]:
    """从全文/snippet 中提取有数字/断言的关键行（快速规则法，无需 LLM）。"""
    import re
    claims: list[dict] = []
    lines = re.split(r"[。\n]", text)
    for line in lines:
        line = line.strip()
        if not line or len(line) < 12:
            continue
        # 提取包含数字的主张
        if re.search(r"[百千万亿\d]+", line):
            claims.append({
                "text": line[:200],
                "has_number": True,
            })
        # 提取含"是/为/达/突破/下降/增长"等断言动词的主张
        elif re.search(r"(?:是|为|达|突破|达到|下降|增长|减少|预计|同比|环比)", line):
            claims.append({
                "text": line[:200],
                "has_number": False,
            })
    return claims[:10]


def _normalize_claim_text(text: str) -> str:
    """归一化主张文本用于对比。"""
    import re
    t = re.sub(r"[^\u4e00-\u9fff\w\d.%-]", "", text)
    t = re.sub(r"\s+", "", t)[:80]
    return t


def _cross_validate_items(items: list[dict], top_n: int = 3) -> list[dict]:
    """对多条结果提取主张并交叉比对，返回一致性分析结果。"""
    all_claims: list[dict] = []
    for item in items[:top_n]:
        source = (item.get("full_text") or item.get("snippet") or "").strip()
        if not source:
            continue
        claims = _extract_key_claims_from_text(source)
        for c in claims:
            c["source_url"] = item.get("url", "")
            c["source_title"] = item.get("title", "")
        all_claims.extend(claims)

    if not all_claims:
        return []

    # 按归一化文本分组
    groups: dict[str, list[dict]] = {}
    for c in all_claims:
        key = _normalize_claim_text(c["text"])
        if not key or len(key) < 6:
            continue
        groups.setdefault(key, []).append(c)

    verifications: list[dict] = []
    for norm_key, sources in groups.items():
        if len(sources) < 2:
            continue
        unique_sources = list({s["source_url"] for s in sources if s.get("source_url")})
        has_numbers = any(s["has_number"] for s in sources)
        sample_text = sources[0]["text"]

        # 检查数字一致性
        import re
        numbers = set()
        for s in sources:
            nums = re.findall(r"\d+[\.\d]*(?:万|亿|%|倍)?", s["text"])
            numbers.update(nums)

        verifications.append({
            "claim": sample_text[:200],
            "source_count": len(unique_sources),
            "sources": unique_sources,
            "has_number": has_numbers,
            "value_count": len(numbers),
            "consistent": len(numbers) <= 2,
        })

    verifications.sort(key=lambda v: -v["source_count"])
    return verifications[:10]


def _queryable_doc_ids(ctx: ToolRuntimeContext) -> list[uuid.UUID]:
    from app.services.document_service import list_queryable_documents

    docs, _ = list_queryable_documents(ctx.db, ctx.user, page=1, page_size=100)
    return [d.id for d in docs]


async def _run_knowledge_retrieve(
    ctx: ToolRuntimeContext, params: dict[str, Any]
) -> tuple[bool, str, dict | None]:
    query = str(params.get("query") or "").strip()
    limit = int(params.get("limit") or 8)
    raw_ids = params.get("doc_ids")
    doc_ids: list[uuid.UUID] = []
    if isinstance(raw_ids, list):
        for item in raw_ids:
            try:
                doc_ids.append(uuid.UUID(str(item)))
            except ValueError:
                continue
    if not doc_ids:
        doc_ids = _queryable_doc_ids(ctx)
    if not doc_ids:
        return _tool_result(False, "未指定 doc_ids，且用户权限内暂无可检索文档")
    from app.services.knowledge_qa_service import retrieve_hits_for_qa

    hits, mode = retrieve_hits_for_qa(
        ctx.db, ctx.user, doc_ids, query, limit=limit, merge_nearby=True
    )
    return _tool_result(
        True,
        f"知识库检索命中 {len(hits)} 段",
        {"query": query, "hits": hits, "mode": mode, "doc_ids": [str(x) for x in doc_ids]},
    )


async def _run_kg_query(ctx: ToolRuntimeContext, params: dict[str, Any]) -> tuple[bool, str, dict | None]:
    """Neo4j 版知识图谱查询 — 本体感知的多跳推理。"""
    question = str(params.get("question") or params.get("query") or "").strip()
    from app.core.neo4j import get_neo4j
    from app.core.permissions import user_has_permission

    has_ontology = user_has_permission(ctx.db, ctx.user, "feature.ontology")
    has_kg = user_has_permission(ctx.db, ctx.user, "feature.kg")
    if not (has_ontology or has_kg):
        return _tool_result(False, "无知识图谱权限，请前往「语义管理」开启功能权限")

    try:
        driver = await get_neo4j()
        from app.services.kg_reasoning import KGReasoningEngine

        engine = KGReasoningEngine(driver)
        context = await engine.reason(
            question=question,
            user_id=str(ctx.user.id),
            max_depth=3,
            include_inferred=True,
        )
        if not context or not context.context_text:
            return _tool_result(True, "未匹配到图谱实体", {})
        return _tool_result(
            True,
            f"图谱上下文 {context.entity_count} 个实体，{context.relation_count} 条关系",
            {
                "context_text": context.context_text,
                "entity_count": context.entity_count,
                "relation_count": context.relation_count,
                "matched_entity_ids": context.matched_entity_ids,
                "citations": context.citations,
                "reasoning_hops": context.reasoning_hops,
                "inferred_entities": context.inferred_entities,
            },
        )
    except Exception as exc:
        return _tool_result(False, f"图谱查询失败: {exc}")


async def _run_ontology_query(ctx: ToolRuntimeContext, params: dict[str, Any]) -> tuple[bool, str, dict | None]:
    """查询本体定义：实体类型列表、关系类型约束、属性模式等。"""
    question = str(params.get("question") or params.get("query") or "").strip()
    from app.core.neo4j import get_neo4j
    from app.core.permissions import user_has_permission

    if not user_has_permission(ctx.db, ctx.user, "feature.ontology"):
        return _tool_result(False, "无知识图谱权限")

    try:
        driver = await get_neo4j()
        from app.services.kg_reasoning import KGReasoningEngine

        engine = KGReasoningEngine(driver)
        ontology_text = await engine.query_ontology(question)
        if not ontology_text.strip():
            ontology_text = "当前本体为空，建议先通过「语义管理 > 本体定义」初始化默认本体"

        from app.schemas.kg import KgQaContext
        context = KgQaContext(
            context_text=ontology_text,
            citations=[],
            entity_count=0,
            relation_count=0,
        )
        return _tool_result(
            True,
            "本体查询完成",
            {
                "context_text": context.context_text,
                "entity_count": context.entity_count,
                "relation_count": context.relation_count,
                "citations": context.citations,
            },
        )
    except Exception as exc:
        return _tool_result(False, f"本体查询失败: {exc}")


async def _run_knowledge_folder_search(
    ctx: ToolRuntimeContext, params: dict[str, Any]
) -> tuple[bool, str, dict | None]:
    """在 Agent 已挂载的知识库文件夹内检索文档。"""
    query = str(params.get("query") or "").strip()
    limit = int(params.get("limit") or 8)
    if not query:
        return _tool_result(False, "检索词为空")

    from app.services.agent_knowledge_mount_service import (
        list_mounts,
        resolve_mounts_to_doc_ids,
    )

    agent_id = (ctx.loop_state or {}).get("agent_id") or "orchestrator"
    mounts = list_mounts(ctx.db, agent_id)
    if not mounts:
        return _tool_result(False, "当前 Agent 未挂载任何知识库文件夹，请先用 list_mounted_folders 查看")

    doc_ids = resolve_mounts_to_doc_ids(ctx.db, ctx.user, mounts)
    if not doc_ids:
        return _tool_result(
            True,
            "挂载文件夹中暂无可检索的文档",
            {"query": query, "hits": [], "mode": "none"},
        )

    from app.services.knowledge_qa_service import retrieve_hits_for_qa

    uuid_ids = [uuid.UUID(d) for d in doc_ids]
    hits, mode = retrieve_hits_for_qa(
        ctx.db, ctx.user, uuid_ids, query, limit=limit, merge_nearby=True
    )
    return _tool_result(
        True,
        f"挂载文件夹检索命中 {len(hits)} 段",
        {"query": query, "hits": hits, "mode": mode, "doc_ids": doc_ids},
    )


def _run_list_mounted_folders(
    ctx: ToolRuntimeContext,
) -> tuple[bool, str, dict | None]:
    """列出当前 Agent 已挂载的知识库文件夹。"""
    from app.services.agent_knowledge_mount_service import list_mounts

    agent_id = (ctx.loop_state or {}).get("agent_id") or "orchestrator"
    mounts = list_mounts(ctx.db, agent_id)
    if not mounts:
        return _tool_result(True, "当前 Agent 未挂载任何知识库文件夹", {"folders": []})

    items = []
    for m in mounts:
        items.append({
            "id": m.get("id"),
            "dataset_id": m.get("dataset_id"),
            "folder_id": m.get("folder_id"),
            "scope": m.get("scope"),
            "label": m.get("label", "文件夹"),
        })
    return _tool_result(
        True,
        f"已挂载 {len(items)} 个知识库文件夹",
        {"folders": items},
    )


async def run_global_atomic_tool(
    ctx: ToolRuntimeContext,
    tool_id: str,
    params: dict[str, Any],
) -> tuple[bool, str, dict[str, Any] | None]:
    """全局原子 Tool 执行 — Tool 层不感知 Skill / Agent / LLM。"""
    name = (tool_id or "").strip()

    if name == ATOMIC_TOOL_WEB_SEARCH:
        return await _run_web_search(ctx, params)
    if name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        if ctx.loop_state and ctx.loop_state.get("local_kb_disabled"):
            return _tool_result(True, "已跳过知识库检索", {"context": "", "skipped": True})
        if ctx.loop_state:
            scoped = ctx.loop_state.get("scoped_doc_ids")
            if scoped is not None and not params.get("doc_ids"):
                params = {**params, "doc_ids": [str(x) for x in scoped]}
        return await _run_knowledge_retrieve(ctx, params)
    if name == ATOMIC_TOOL_KG_QUERY:
        return await _run_kg_query(ctx, params)
    if name == ATOMIC_TOOL_ONTOLOGY_QUERY:
        return await _run_ontology_query(ctx, params)
    if name == "knowledge_folder_search":
        return await _run_knowledge_folder_search(ctx, params)
    if name == "list_mounted_folders":
        return _run_list_mounted_folders(ctx)

    from app.services.agent_tools import (
        _execute_admin_tool,
        _execute_browser_tool,
        _execute_document_tool,
        _execute_platform_tool,
    )
    from app.services.agent_memory_service import append_user_memory, read_user_memory
    from app.services.agent_skill_router import extract_memory_note

    if name == "read_agent_memory":
        body = read_user_memory(ctx.user.id)
        if not body:
            from app.services.agent_memory_service import MEMORY_TEMPLATE

            body = MEMORY_TEMPLATE
        return _tool_result(True, "已读取记忆", {"memory": body})
    if name == "append_agent_memory":
        note = str(params.get("note") or "").strip()
        if not note:
            return _tool_result(False, "note 不能为空")
        ok = append_user_memory(ctx.user.id, extract_memory_note(note, max_len=500))
        return _tool_result(ok, "已写入记忆" if ok else "写入失败")

    doc_raw = _execute_document_tool(ctx.db, ctx.user, tool_name=name, params=params)
    if doc_raw is not None:
        if name == "read_document_content" and ctx.loop_state is not None:
            try:
                body = json.loads(doc_raw)
                data = body.get("data") if isinstance(body, dict) else None
                if body.get("ok") and isinstance(data, dict):
                    full_text = str(data.get("full_text") or "").strip()
                    if full_text:
                        ctx.loop_state["agent_document_context"] = {
                            "title": str(data.get("title") or "").strip(),
                            "full_text": full_text[:40000],
                            "char_count": int(data.get("char_count") or len(full_text)),
                        }
            except json.JSONDecodeError:
                pass
        try:
            body = json.loads(doc_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, doc_raw[:300], None

    plat_raw = _execute_platform_tool(ctx.db, ctx.user, tool_name=name, params=params)
    if plat_raw is not None:
        try:
            body = json.loads(plat_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, plat_raw[:300], None

    admin_raw = _execute_admin_tool(ctx.db, ctx.user, tool_name=name, params=params)
    if admin_raw is not None:
        try:
            body = json.loads(admin_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, admin_raw[:300], None

    browser_raw = await _execute_browser_tool(
        ctx.db,
        ctx.user,
        tool_name=name,
        params=params,
        conversation_id=ctx.conversation_id,
        loop_state=ctx.loop_state,
        user_message=ctx.user_message,
    )
    if browser_raw is not None:
        try:
            body = json.loads(browser_raw)
            if isinstance(body, dict):
                return bool(body.get("ok")), str(body.get("summary") or ""), (
                    body.get("data") if isinstance(body.get("data"), dict) else {}
                )
        except json.JSONDecodeError:
            pass
        return False, browser_raw[:300], None

    return False, f"unknown global atomic tool: {name}", None
