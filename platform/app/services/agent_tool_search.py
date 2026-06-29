"""Agent 工具动态发现 — search_tools、示例与 loop 可见集。"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.agent_tool_args import (
    RunToolBatchArgs,
    SearchToolsArgs,
    build_function_tool_spec,
    validate_tool_arguments,
)
from app.models.org import User

# 主 Agent 默认可见；其余通过 search_tools 解锁
CORE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_tools",
        "run_tool_batch",
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "search_documents_by_name",
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
        {"query": "碳排放配额管理办法"},
        {"query": "采购审批流程", "limit": 5},
    ],
    "web_search": [
        {"query": "全国碳市场最新成交价"},
    ],
    "kg_query": [
        {"question": "某公司与子公司之间的持股关系"},
    ],
    "search_documents_by_name": [
        {"name": "采购制度"},
        {"name": "可行性", "scope": "company", "limit": 10},
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
            "title": "跟进碳价",
            "body": "查看今日碳价",
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
        {"question": "智碳产品分部有哪些成员"},
        {"question": "系统中有哪些用户"},
    ],
}

SEARCH_TOOLS_SPEC: dict[str, Any] = build_function_tool_spec(
    name="search_tools",
    description="按关键词搜索可用工具定义；不确定工具名时先调用",
    args_model=SearchToolsArgs,
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
        if not name or name == "search_tools":
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
    if "search_tools" not in seen:
        out.insert(0, attach_tool_examples(SEARCH_TOOLS_SPEC))
    if "run_tool_batch" not in seen:
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


async def execute_search_tools(
    db: Session,
    user: User,
    *,
    all_specs: list[dict[str, Any]],
    query: str,
    limit: int = 8,
    loop_state: dict[str, Any] | None = None,
) -> str:
    from app.services.agent_tools import build_agent_tool_specs
    from app.skills.catalog import search_skill_routes

    if not all_specs:
        all_specs = build_agent_tool_specs(db, user)
    matches = search_tool_definitions(all_specs, query, limit=limit)
    names = [tool_spec_name(s) for s in matches]
    register_unlocked_tools(loop_state, names)
    skill_lines = []
    if re.search(r"skill|技能|脚本", query, re.I):
        skill_lines = search_skill_routes(db, user, query, tier="extended", limit=3)
    payload = [
        {
            "name": tool_spec_name(s),
            "description": (s.get("function") or {}).get("description"),
            "examples": (s.get("function") or {}).get("examples"),
        }
        for s in matches
    ]
    summary = f"找到 {len(payload)} 个工具" if payload else "无匹配工具，请换关键词"
    if skill_lines:
        summary += f"；{len(skill_lines)} 条扩展 Skill 路由"
    return json.dumps(
        {
            "ok": True,
            "summary": summary,
            "tools": payload,
            "skills": skill_lines,
            "unlocked": names,
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
                    "summary": f"步骤 {idx} 工具 `{tool}` 不允许 batch（仅只读/检索）",
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
