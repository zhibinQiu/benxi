"""Agentic RAG 工具封装：检索、图谱、联网、版本元数据等能力统一出口。"""

from __future__ import annotations

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


@dataclass
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
            )
            from app.services.report_generation_service import merge_retrieval_hits

            self._local_hits = merge_retrieval_hits(
                self._local_hits + list(hits),
                max_total=max(20, (limit or self.retrieve_limit) * 4),
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
        except Exception as exc:
            logger.warning("Agentic retrieve 失败 q=%r: %s", q, exc)
            return ToolResult("retrieve", False, f"检索失败：{exc}", error=str(exc))

    def kg_planning_context(self, question: str) -> ToolResult:
        if not self.include_kg:
            return ToolResult("kg_context", True, "未启用本体图谱", data=None)
        try:
            from app.core.permissions import user_has_permission
            from app.services.kg_service import retrieve_kg_context_for_question

            if not user_has_permission(self.db, self.user, "feature.kg_palantir"):
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
        q = (query or "").strip()
        if not q:
            return ToolResult("web_search", False, "联网检索词为空", error="empty_query")
        if not self.web_enabled:
            return ToolResult("web_search", True, "联网检索未开启", data=[])
        try:
            from app.services.searxng_service import (
                SearxngNotConfiguredError,
                SearxngSearchError,
                search_web,
            )

            cap = max_items or self.web_max_items
            items, _ = search_web(q, page_size=cap, db=self.db)
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
                "web_search",
                True,
                f"联网「{q[:36]}」新增 {added} 条（累计 {len(self._web_items)} 条）",
                data={"items": items, "query": q},
            )
        except (SearxngNotConfiguredError, SearxngSearchError) as exc:
            return ToolResult("web_search", False, str(exc), error=str(exc))
        except Exception as exc:
            logger.warning("Agentic web_search 失败 q=%r: %s", q, exc)
            return ToolResult("web_search", False, f"联网检索失败：{exc}", error=str(exc))

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