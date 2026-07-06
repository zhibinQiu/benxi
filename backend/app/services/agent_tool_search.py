"""Agent 工具动态发现 — search_tools、示例与 loop 可见集。"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.agent_tool_args import (
    RunToolBatchArgs,
    SearchSkillsArgs,
    build_function_tool_spec,
)
from app.models.org import User

# 主 Agent 默认可见；扩展能力通过 search_skills 发现
CORE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_skills",
        "run_tool_batch",
        "invoke_skill",
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "search_documents_by_name",
        "read_document_content",
        "read_agent_memory",
        "append_agent_memory",
    }
)

# run_tool_batch 允许的工具（只读/检索类，中间结果不进 LLM）
BATCH_SAFE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "list_document_folders",
        "list_library_documents",
        "search_documents_by_name",
        "read_document_content",
        "list_todos",
        "read_agent_memory",
    }
)

TOOL_USE_EXAMPLES: dict[str, list[dict[str, Any]]] = {
    "search_tools": [
        {"query": "文档 文件夹", "note": "找文档库相关工具"},
        {"query": "定时 提醒", "note": "找 schedule_notification"},
    ],
    "knowledge_retrieve": [
        {"query": "采购审批流程"},
        {"query": "信息安全管理制度", "limit": 5},
    ],
    "web_search": [
        {"query": "行业政策最新动态"},
    ],
    "kg_query": [
        {"question": "某公司与子公司之间的持股关系"},
    ],
    "search_documents_by_name": [
        {"name": "采购制度"},
        {"name": "可行性", "scope": "company", "limit": 10},
    ],
    "read_document_content": [
        {"document_id": "00000000-0000-0000-0000-000000000001"},
        {"document_name": "采购制度", "max_chars": 12000},
    ],
    "list_document_folders": [
        {},
        {"parent_id": "00000000-0000-0000-0000-000000000000"},
    ],
    "create_kb_folder": [
        {"name": "项目资料", "parent_id": None},
    ],
    "schedule_notification": [
        {
            "title": "跟进待办",
            "body": "查看今日待办事项",
            "scheduled_at": "2026-06-26T09:00:00+08:00",
        }
    ],
    "run_tool_batch": [
        {
            "steps": [
                {"tool": "list_document_folders", "arguments": {}},
                {"tool": "knowledge_retrieve", "arguments": {"query": "制度"}},
            ]
        }
    ],
    "list_users": [
        {"page": 1, "page_size": 20},
        {"keyword": "张三"},
    ],
    "list_departments": [
        {},
    ],
    "kg_query": [
        {"question": "本析产品分部有哪些成员"},
        {"question": "系统中有哪些用户"},
    ],
}

SEARCH_SKILLS_SPEC: dict[str, Any] = build_function_tool_spec(
    name="search_skills",
    description="按关键词搜索可用 Skill 路由",
    args_model=SearchSkillsArgs,
)

RUN_TOOL_BATCH_SPEC: dict[str, Any] = build_function_tool_spec(
    name="run_tool_batch",
    description="批量执行只读/检索工具，中间结果不进上下文",
    args_model=RunToolBatchArgs,
)


def tool_spec_name(spec: dict[str, Any]) -> str:
    return str((spec.get("function") or {}).get("name") or "")


def attach_tool_examples(spec: dict[str, Any]) -> dict[str, Any]:
    """复制 spec 并附加 examples 字段（OpenAI 兼容）。"""
    name = tool_spec_name(spec)
    examples = TOOL_USE_EXAMPLES.get(name)
    if not examples:
        return spec
    out = json.loads(json.dumps(spec, ensure_ascii=False))
    fn = out.setdefault("function", {})
    fn["examples"] = examples[:5]
    desc = str(fn.get("description") or "").strip()
    if examples and "示例" not in desc:
        sample = json.dumps(examples[0], ensure_ascii=False)
        fn["description"] = f"{desc} 示例: {sample[:180]}"
    return out


def _tokenize_query(query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return []
    parts = re.split(r"[\s,，、/]+", q)
    return [p for p in parts if len(p) >= 2]


def search_tool_definitions(
    all_specs: list[dict[str, Any]],
    query: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    tokens = _tokenize_query(query)
    if not tokens:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for spec in all_specs:
        name = tool_spec_name(spec)
        if not name or name in ("search_tools", "search_skills"):
            continue
        fn = spec.get("function") or {}
        hay = f"{name} {fn.get('description') or ''}".lower()
        score = sum(2 if t in name else 1 for t in tokens if t in hay)
        if score > 0:
            scored.append((score, attach_tool_examples(spec)))
    scored.sort(key=lambda x: (-x[0], tool_spec_name(x[1])))
    return [spec for _, spec in scored[: max(1, limit)]]


def select_visible_tool_specs(
    all_specs: list[dict[str, Any]],
    unlocked: set[str] | None,
    *,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    """主 Agent loop：核心工具 + 已解锁 + search/batch meta 工具。"""
    unlocked = unlocked or set()
    visible_names = CORE_TOOL_NAMES | unlocked
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in all_specs:
        name = tool_spec_name(spec)
        if name in seen:
            continue
        if name in visible_names:
            out.append(attach_tool_examples(spec))
            seen.add(name)
    if "search_skills" not in seen:
        out.insert(0, attach_tool_examples(SEARCH_SKILLS_SPEC))
    aid = (agent_id or "").strip()
    # skill-dev 等专精须直接 tool_calls（run_skill_script 等），勿走 batch
    if aid not in ("skill-dev", "report", "rpa") and "run_tool_batch" not in seen:
        out.insert(1, attach_tool_examples(RUN_TOOL_BATCH_SPEC))
    return out


def register_unlocked_tools(loop_state: dict[str, Any] | None, names: list[str]) -> None:
    if loop_state is None:
        return
    bucket: set[str] = loop_state.setdefault("unlocked_tools", set())
    for name in names:
        n = str(name or "").strip()
        if n:
            bucket.add(n)


async def execute_search_skills_compat(
    db: Session,
    user: User,
    *,
    query: str,
    limit: int = 8,
    loop_state: dict[str, Any] | None = None,
) -> str:
    """search_tools 兼容入口 — 统一走 Skill 路由搜索。"""
    from app.skills.catalog import search_skill_routes

    lines = search_skill_routes(db, user, query, tier=None, limit=limit)
    if loop_state is not None and lines:
        loop_state.setdefault("discovered_skill_routes", []).extend(lines[:limit])
    text = "\n".join(lines) if lines else "未匹配到 Skill"
    return json.dumps(
        {
            "ok": True,
            "summary": f"匹配 {len(lines)} 条 Skill 路由",
            "data": {"lines": lines, "text": text},
        },
        ensure_ascii=False,
    )


async def execute_run_tool_batch(
    db: Session,
    user: User,
    *,
    steps: list[dict[str, Any]],
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    user_message: str = "",
    loop_state: dict[str, Any] | None = None,
) -> str:
    from app.services.agent_tools import execute_agent_tool

    if not steps:
        return json.dumps({"ok": False, "summary": "steps 为空"}, ensure_ascii=False)
    if len(steps) > 6:
        return json.dumps(
            {"ok": False, "summary": "单次 batch 最多 6 步"},
            ensure_ascii=False,
        )
    summaries: list[str] = []
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        tool = str(step.get("tool") or "").strip()
        args = step.get("arguments") or {}
        if tool not in BATCH_SAFE_TOOL_NAMES:
            return json.dumps(
                {
                    "ok": False,
                    "summary": f"步骤 {idx} 工具 `{tool}` 不允许 batch（请单独调用该工具）",
                },
                ensure_ascii=False,
            )
        raw = await execute_agent_tool(
            db,
            user,
            tool_name=tool,
            arguments=args if isinstance(args, dict) else {},
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            user_message=user_message,
            loop_state=loop_state,
        )
        try:
            body = json.loads(raw)
            summaries.append(
                f"[{idx}] {tool}: {str(body.get('summary') or raw)[:240]}"
            )
        except json.JSONDecodeError:
            summaries.append(f"[{idx}] {tool}: {raw[:240]}")
    text = "\n".join(summaries)
    return json.dumps(
        {"ok": True, "summary": text[:1200], "step_count": len(summaries)},
        ensure_ascii=False,
    )
