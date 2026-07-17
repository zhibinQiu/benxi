"""Agentic RAG 工具封装：检索、图谱、联网、版本元数据等能力统一出口。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.org import User
from app.services.knowledge_qa_service import (
    _doc_titles,
    retrieve_hits_for_qa,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolResult:
    name: str
    ok: bool
    summary: str
    data: Any = None
    error: str | None = None


@dataclass
class KnowledgeAgenticToolkit:
    """报告生成与知识检索共用的 Agent 工具集。"""

    db: Session
    user: User
    doc_ids: list[uuid.UUID]
    web_enabled: bool = False
    include_kg: bool = True
    retrieve_limit: int = 8
    web_max_items: int = 10
    narrow_by_name: bool = True

    _local_hits: list[dict] = field(default_factory=list, init=False)
    _web_items: list[dict] = field(default_factory=list, init=False)
    _web_urls_seen: set[str] = field(default_factory=set, init=False)

    def doc_titles(self) -> dict[str, str]:
        if not self.doc_ids:
            return {}
        return _doc_titles(self.db, self.doc_ids)

    def retrieve(self, query: str, *, limit: int | None = None) -> ToolResult:
        q = (query or "").strip()
        if not q:
            return ToolResult("retrieve", False, "检索词为空", error="empty_query")
        if not self.doc_ids:
            return ToolResult("retrieve", False, "未选择文档", data=[])
        try:
            hits, mode = retrieve_hits_for_qa(
                self.db,
                self.user,
                self.doc_ids,
                q,
                limit=limit or self.retrieve_limit,
                merge_nearby=True,
                narrow_by_name=self.narrow_by_name,
            )
            return self._finalize_retrieve_result(q, hits, mode)
        except Exception as exc:
            logger.warning("Agentic retrieve 失败 q=%r: %s", q, exc)
            return ToolResult("retrieve", False, f"检索失败：{exc}", error=str(exc))

    def retrieve_many(
        self,
        queries: list[str],
        *,
        limit: int | None = None,
    ) -> list[ToolResult]:
        """并行检索多个子问题，返回与 queries 顺序对应的结果列表。"""
        cleaned = [(q or "").strip() for q in queries]
        if not self.doc_ids:
            return [
                ToolResult("retrieve", False, "未选择文档", data=[])
                for _ in cleaned
            ]

        per_limit = limit or self.retrieve_limit
        unique = list(dict.fromkeys(q for q in cleaned if q))
        hits_by_query: dict[str, tuple[list[dict], str]] = {}

        if unique:
            from app.services.knowledge_qa.retrieval import retrieve_hits_by_queries

            hits_by_query = retrieve_hits_by_queries(
                self.db,
                self.user,
                self.doc_ids,
                unique,
                limit_per_query=per_limit,
                merge_nearby=True,
            )

        results: list[ToolResult] = []
        for q in cleaned:
            if not q:
                results.append(
                    ToolResult("retrieve", False, "检索词为空", error="empty_query")
                )
                continue
            hits, mode = hits_by_query.get(q, ([], "none"))
            results.append(self._finalize_retrieve_result(q, hits, mode))
        return results

    def _finalize_retrieve_result(
        self,
        q: str,
        hits: list[dict],
        mode: str,
    ) -> ToolResult:
        from app.services.report_generation_service import merge_retrieval_hits

        self._local_hits = merge_retrieval_hits(
            self._local_hits + list(hits),
            max_total=max(20, self.retrieve_limit * 4),
        )
        summary = f"检索「{q[:40]}」命中 {len(hits)} 段（累计 {len(self._local_hits)} 段）"
        detail_lines = [summary]
        mode_label = {
            "hybrid": "混合检索（语义+关键词）",
            "pageindex_tree": "PageIndex 树检索",
            "local": "本地全文检索",
            "mixed": "多路混合",
            "none": "未命中",
        }.get(str(mode or ""), str(mode or ""))
        if mode_label:
            detail_lines.append(f"检索模式：{mode_label}")
        previews: list[str] = []
        for hit in hits[:2]:
            snip = (
                (hit.get("snippet") or hit.get("highlight") or hit.get("content") or "")
                .strip()
                .replace("\n", " ")
            )
            if snip:
                previews.append(snip[:100])
        if previews:
            detail_lines.append("片段预览：" + " | ".join(previews))
        return ToolResult(
            "retrieve",
            True,
            "\n".join(detail_lines),
            data={"hits": hits, "mode": mode, "query": q},
        )

    def kg_planning_context(self, question: str) -> ToolResult:
        if not self.include_kg:
            return ToolResult("kg_context", True, "未启用知识图谱", data=None)
        try:
            from app.core.permissions import user_has_permission
            from app.services.kg_service import retrieve_kg_context_for_question

            if not user_has_permission(self.db, self.user, "feature.kg"):
                return ToolResult("kg_context", True, "无图谱权限", data=None)
            ctx = retrieve_kg_context_for_question(self.db, self.user, question)
            if not ctx or not ctx.context_text:
                return ToolResult("kg_context", True, "未匹配到图谱实体", data=None)
            return ToolResult(
                "kg_context",
                True,
                f"图谱上下文 {ctx.entity_count} 个实体",
                data=ctx,
            )
        except Exception as exc:
            logger.warning("Agentic kg_context 失败: %s", exc)
            return ToolResult("kg_context", False, "图谱上下文获取失败", error=str(exc))

    def web_search(self, query: str, *, max_items: int | None = None) -> ToolResult:
        """（已弃用）逐查询联网检索。

        报告生成请使用 deep_research() 方法统一调研，不再逐条查询调用 web_search。
        保留此方法仅用于兼容旧调用方，内部仍走 deep_research 子智能体。
        """
        return self.deep_research(query, max_items=max_items)

    def deep_research(self, topic: str, *, max_items: int | None = None) -> ToolResult:
        """统一联网调研入口：走 deep_research 子智能体进行多轮检索与综合分析。

        取代逐条 web_search 调用，一次传入完整主题/问题，
        子智能体自主分析意图、多关键词搜索、FireCrawl 读全文、交叉验证。
        """
        q = (topic or "").strip()
        if not q:
            return ToolResult("web_search", False, "联网调研主题为空", error="empty_query")
        if not self.web_enabled:
            return ToolResult("web_search", True, "联网检索未开启", data=[])
        try:
            cap = max_items or self.web_max_items
            items = _deep_research_via_subagent_sync(self.db, self.user, q)
            if items is None:
                raise RuntimeError("deep_research 子智能体返回空")
            added = 0
            for row in items:
                url = (row.get("url") or "").strip()
                if not url or url in self._web_urls_seen:
                    continue
                self._web_urls_seen.add(url)
                self._web_items.append(row)
                added += 1
                if len(self._web_items) >= cap:
                    break
            return ToolResult(
                "deep_research",
                True,
                f"联网调研「{q[:36]}」新增 {added} 条（累计 {len(self._web_items)} 条）",
                data={"items": items, "query": q},
            )
        except Exception as exc:
            logger.warning("deep_research 失败 topic=%r: %s", q, exc)
            return ToolResult("deep_research", False, f"联网调研失败：{exc}", error=str(exc))

    def version_metadata(self) -> ToolResult:
        if not self.doc_ids:
            return ToolResult("version_metadata", True, "无文档", data={})
        try:
            from app.services.knowledge_agent_service import (
                format_changelog_context,
                format_diff_summary_context,
                load_version_changelogs,
                load_version_diff_summaries,
            )

            titles = self.doc_titles()
            changelogs = load_version_changelogs(self.db, self.doc_ids)
            diffs = load_version_diff_summaries(self.db, self.doc_ids)
            return ToolResult(
                "version_metadata",
                True,
                "已加载版本变更与 diff 摘要",
                data={
                    "changelog_block": format_changelog_context(changelogs, titles),
                    "diff_block": format_diff_summary_context(diffs, titles),
                },
            )
        except Exception as exc:
            logger.warning("Agentic version_metadata 失败: %s", exc)
            return ToolResult("version_metadata", False, "版本元数据加载失败", error=str(exc))

    @property
    def accumulated_local_hits(self) -> list[dict]:
        return list(self._local_hits)

    @property
    def accumulated_web_items(self) -> list[dict]:
        return list(self._web_items)


ToolRunner = Callable[[KnowledgeAgenticToolkit, str], ToolResult]


def _deep_research_via_subagent_sync(
    db: Session,
    user: User,
    query: str,
) -> list[dict] | None:
    """Sync wrapper: invoke deep_research subagent and return web items.

    所有联网检索统一走 deep_research 子智能体（而非直接调用 web-search skill），
    子智能体内部调用 web_search 进行多轮搜索与全文阅读，返回结构化研究报告。
    本函数解析研究报告中的来源链接，提取为 web_items 格式供调用方使用。

    Runs via asyncio.run() since callers (report gathering, knowledge QA)
    execute in thread pools (run_db_task) where no event loop is active.
    """
    from app.core.agent.subagent import execute_context_subagent

    q = (query or "").strip()
    if not q:
        return None

    try:
        result_text = asyncio.run(
            execute_context_subagent(
                db,
                user,
                kind="search",
                task=q,
            )
        )
    except Exception:
        logger.warning("search subagent 调用失败 q=%r", q, exc_info=True)
        return None

    if not result_text or not result_text.strip():
        return None

    # execute_context_subagent 返回结构化 JSON，提取实际报告文本
    try:
        payload = json.loads(result_text)
    except json.JSONDecodeError:
        payload = {}
    report = (payload.get("data") or {}).get("result") or payload.get("summary") or result_text

    return _deep_research_output_to_web_items(report)


def _deep_research_output_to_web_items(text: str) -> list[dict]:
    """解析 deep_research 子智能体输出，提取来源链接为 web_items 格式。

    deep_research 输出为结构化研究报告，含 inline citations / markdown links。
    提取其中的 URL 与其周边上下文作为 web item 的 title/snippet/full_text。
    """
    import re

    items: list[dict] = []
    seen_urls: set[str] = set()
    limit = 10

    # 提取 markdown 链接 [title](url)
    for m in re.finditer(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)', text):
        title = (m.group(1) or "").strip()
        url = m.group(2).strip().rstrip(".)")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        start = max(0, m.start() - 120)
        end = min(len(text), m.end() + 120)
        snippet = text[start:end].replace("\n", " ")
        items.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet[:600],
                "full_text": snippet[:3000],
            }
        )
        if len(items) >= limit:
            break

    # 无 markdown 链接时回退：裸 URL + 周边上下文
    if not items:
        for m in re.finditer(r'(https?://[^\s\)\]<>"\']+)', text):
            url = m.group(1).strip().rstrip(".,;:)!?")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            start = max(0, m.start() - 100)
            end = min(len(text), m.end() + 100)
            snippet = text[start:end].replace("\n", " ")
            items.append(
                {
                    "title": url,
                    "url": url,
                    "snippet": snippet[:600],
                    "full_text": snippet[:3000],
                }
            )
            if len(items) >= limit:
                break

    return items