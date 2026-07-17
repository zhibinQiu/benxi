"""Agent 工具动态发现 — search_tools、示例与 loop 可见集。"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from app.core.agent_loop_state import LoopState

from sqlalchemy.orm import Session

from app.core.agent_tool_args import (
    DescribeToolArgs,
    RunToolBatchArgs,
    SearchSkillsArgs,
    TOOL_DEFINITIONS,
    TOOL_ARG_MODELS,
    build_function_tool_spec,
)
from app.core.tool_def_loader import get_tool_description
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)
from app.models.org import User

# 主 Agent 默认可见的超核心工具集，其余工具通过 describe_tool 按需发现
CORE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_skills",       # 技能发现
        "describe_tool",       # 工具发现（按需加载完整 schema）
        "web_search",          # 联网检索
        "knowledge_retrieve",  # 知识库检索
        "kg_query",            # 图谱查询
        "invoke_context_subagent",  # 子智能体（深度研究/并行检索）
        "send_notification",   # 即时通知
        "schedule_notification",  # 定时通知
    }
)

# run_tool_batch 允许的工具（只读/检索类，中间结果不进 LLM）
BATCH_SAFE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "web_search",
        "knowledge_retrieve",
        "kg_query",
        "invoke_context_subagent",
        "list_document_folders",
        "list_library_documents",
        "search_documents_by_name",
        "read_document_content",
        "list_todos",
        "read_agent_memory",
    }
)

TOOL_USE_EXAMPLES: dict[str, list[dict[str, Any]]] = {
    "describe_tool": [
        {"name": "rename_document", "note": "查 rename_document 的参数结构"},
        {"name": "create_library_document", "note": "查创建文档需要哪些必填参数"},
        {"name": "schedule_notification", "note": "了解通知工具的详细信息"},
    ],
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
        {"query": "2026年新能源车销量数据", "read_full": 5},
        {"query": "比亚迪 2026 年 6 月交付量", "read_full": 3},
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
    "invoke_context_subagent": [
        {"kind": "search", "task": "2026年全球新能源车销量趋势，包含主要品牌数据对比"},
        {"kind": "search", "task": "了解某网站的技术架构", "queries": ["网站技术栈", "架构设计"]},
        {"kind": "auto", "task": "提取页面表单字段结构"},
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

DESCRIBE_TOOL_SPEC: dict[str, Any] = build_function_tool_spec(
    name="describe_tool",
    description="查看任意工具的完整定义（描述 + 参数 schema + 使用示例），查看后该工具会在下一轮对话变为可用",
    args_model=DescribeToolArgs,
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
        seen.add("search_skills")
    if "describe_tool" not in seen:
        # 放在 search_skills 之后
        insert_pos = 1 if len(out) >= 1 else len(out)
        out.insert(insert_pos, attach_tool_examples(DESCRIBE_TOOL_SPEC))
        seen.add("describe_tool")
    aid = (agent_id or "").strip()
    # skill-dev 等专精须直接 tool_calls（run_skill_script 等），勿走 batch
    if aid not in ("skill-dev", "report", "rpa") and "run_tool_batch" not in seen:
        # 放在 describe_tool 之后
        insert_pos = 2 if len(out) >= 2 else len(out)
        out.insert(insert_pos, attach_tool_examples(RUN_TOOL_BATCH_SPEC))
    return out


def register_unlocked_tools(loop_state: LoopState | None, names: list[str]) -> None:
    if loop_state is None:
        return
    bucket: set[str] = loop_state.setdefault("unlocked_tools", set())
    for name in names:
        n = str(name or "").strip()
        if n:
            bucket.add(n)


async def execute_describe_tool(
    db: Session,
    user: User,
    *,
    name: str,
    loop_state: LoopState | None = None,
) -> str:
    """describe_tool 处理器：返回工具的完整定义并解锁。"""
    n = (name or "").strip()
    if not n:
        return json.dumps({"ok": False, "summary": "工具名不能为空"}, ensure_ascii=False)

    definition = TOOL_DEFINITIONS.get(n)
    if not definition:
        # 不是工具？检查是否为 Skill
        from app.skills.catalog import get_merged_skill_definition

        skill_def = get_merged_skill_definition(db, n, user=user) if db else None
        if skill_def:
            from app.skills.routing import format_skill_route_line

            route_line = format_skill_route_line(skill_def)
            full_desc = (
                f"## {n}（Skill）\n\n"
                f"{skill_def.description}\n\n"
                f"## 路由\n{route_line}\n\n"
            )
            if skill_def.tools:
                tool_names = ", ".join(
                    str(getattr(t, "name", t) if hasattr(t, "name") else t)
                    for t in skill_def.tools
                )
                full_desc += f"## 底层工具\n{tool_names}\n\n"
            return json.dumps(
                {
                    "ok": True,
                    "tool_type": "skill",
                    "summary": f"`{n}` 是一个 Skill 而非原子工具，已返回定义",
                    "definition": full_desc,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {"ok": False, "summary": f"未找到工具 `{n}`"},
            ensure_ascii=False,
        )

    # 可见性检查：非 orchestrator 不可发现管理员工具
    from app.core.tool_skill_taxonomy import is_tool_visible_to_agent

    agent_id = None
    if loop_state:
        agent_id = str(loop_state.get("agent_id") or "").strip() or None
    if not is_tool_visible_to_agent(n, agent_id):
        return json.dumps(
            {
                "ok": False,
                "summary": f"工具 `{n}` 不在你的可见范围内，请确认是否需要路由到对应专精处理",
            },
            ensure_ascii=False,
        )

    hardcoded_desc, model_cls = definition
    md_desc = get_tool_description(n)
    desc = md_desc if md_desc else hardcoded_desc

    # 构建 JSON Schema
    schema = model_cls.model_json_schema() if hasattr(model_cls, "model_json_schema") else {}
    required = sorted(schema.get("required", []))
    properties = schema.get("properties", {})

    # 参数描述表格（文本，方便 LLM 阅读）
    param_lines = []
    for pname, pinfo in sorted(properties.items()):
        ptype = pinfo.get("type", "any")
        pdesc = str(pinfo.get("description") or "").strip()
        preq = "必填" if pname in required else "可选"
        default = ""
        if "default" in pinfo and pinfo["default"] is not None:
            default = f" 默认: {pinfo['default']}"
        line = f"  - {pname} ({ptype}, {preq})"
        if pdesc:
            line += f" — {pdesc}"
        if default:
            line += default
        param_lines.append(line)

    params_text = "\n".join(param_lines) if param_lines else "  无参数"

    # 示例
    examples = TOOL_USE_EXAMPLES.get(n, [])
    examples_text = ""
    if examples:
        import json as _json

        ex_lines = []
        for ex in examples[:3]:
            ex_lines.append(f"  {_json.dumps(ex, ensure_ascii=False)}")
        examples_text = "\n## Examples\n" + "\n".join(ex_lines)

    # 注册到 unlocked_tools——下一轮 LLM 调用时该工具变为可用
    register_unlocked_tools(loop_state, [n])

    # 构建返回文本
    full_desc = (
        f"## {n}\n\n"
        f"{desc}\n\n"
        f"## Parameters\n{params_text}"
        f"{examples_text}\n\n"
        f"---\n"
        f"✅ 工具 `{n}` 已被解锁，下一轮你可以直接调用它。"
    )
    return json.dumps(
        {
            "ok": True,
            "summary": f"已加载工具 `{n}` 的定义（{len(params_text)} 个参数行），已解锁可用",
            "data": {
                "tool": n,
                "description": desc,
                "parameters": properties,
                "required": required,
                "examples": examples[:3],
            },
        },
        ensure_ascii=False,
    )


async def execute_search_skills_compat(
    db: Session,
    user: User,
    *,
    query: str,
    limit: int = 8,
    loop_state: LoopState | None = None,
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


# ── 批量执行单步进度推送 ───────────────────────────────────────


def _resolve_queue(loop_state: LoopState | None) -> asyncio.Queue | None:
    """从 loop_state 解析 progress_queue：支持 _progress_queue 和 _parent_progress_queue。"""
    if loop_state is None:
        return None
    q: asyncio.Queue | None = loop_state.get("_progress_queue")
    if q is not None:
        return q
    q = loop_state.get("_parent_progress_queue")
    return q


def _push_batch_start(
    loop_state: LoopState | None,
    idx: int,
    tool_name: str,
    raw_args: dict[str, Any],
) -> None:
    q = _resolve_queue(loop_state)
    if q is None:
        return
    from app.services.agent_tools import tool_workflow_meta

    meta = tool_workflow_meta(tool_name, raw_args)
    step_id = f"batch-start-{uuid.uuid4().hex[:8]}"
    args_preview = _batch_args_preview(raw_args)
    q.put_nowait({
        "phase": "tool_call",
        "title": f"开始并行检索 [{idx}]：{meta.get('detail') or tool_name}",
        "detail": args_preview,
        "callDetail": args_preview,
        "tool": "web.search" if tool_name == "web_search" else tool_name,
        "tool_name": tool_name,
        "step_id": step_id,
        "status": "running",
    })


def _push_batch_progress(
    raw: str,
    loop_state: LoopState | None,
    tool_name: str,
    raw_args: dict[str, Any],
) -> None:
    """将 run_tool_batch 中单个步骤的完成推送到父 loop_state 的 progress_queue。"""
    q = _resolve_queue(loop_state)
    if q is None:
        return
    from app.services.agent_tools import tool_workflow_meta

    step_id = f"batch-progress-{uuid.uuid4().hex[:8]}"
    try:
        body = json.loads(raw)
        ok = bool(body.get("ok"))
        summary = str(body.get("summary") or "")[:240]
    except json.JSONDecodeError:
        ok = False
        summary = str(raw)[:240]
    meta = tool_workflow_meta(tool_name, raw_args)
    q.put_nowait({
        "phase": "tool_result",
        "title": meta.get("result_title") or (f"{tool_name} 完成" if ok else f"{tool_name} 失败"),
        "detail": summary or ("完成" if ok else "失败"),
        "resultDetail": summary[:400],
        "tool": "web.search" if tool_name == "web_search" else tool_name,
        "tool_name": tool_name,
        "step_id": step_id,
        "status": "done" if ok else "failed",
    })


def _batch_args_preview(raw_args: dict[str, Any]) -> str:
    parts = []
    for k, v in raw_args.items():
        vs = str(v)[:80]
        parts.append(f"{k}={vs}")
    return ", ".join(parts)[:200]


async def execute_run_tool_batch(
    db: Session,
    user: User,
    *,
    steps: list[dict[str, Any]],
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    user_message: str = "",
    loop_state: LoopState | None = None,
) -> str:
    from app.services.agent_tools import execute_agent_tool

    if not steps:
        return json.dumps({"ok": False, "summary": "steps 为空"}, ensure_ascii=False)
    if len(steps) > 6:
        return json.dumps(
            {"ok": False, "summary": "单次 batch 最多 6 步"},
            ensure_ascii=False,
        )

    # 先校验所有步骤合法性
    validated: list[tuple[int, str, dict[str, Any]]] = []
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
        validated.append((idx, tool, args if isinstance(args, dict) else {}))

    if not validated:
        return json.dumps({"ok": False, "summary": "无有效步骤"}, ensure_ascii=False)

    # 并行执行所有步骤，依次记录每个完成的结果（as_completed 使各步骤按其完成顺序自然出现）
    async def _run_one(idx: int, tool: str, args: dict[str, Any]) -> str:
        from app.core.agent_tool_context import record_executed_tool_call

        step_id = f"batch-{uuid.uuid4().hex[:8]}"
        _push_batch_start(loop_state, idx, tool, args)
        raw = await execute_agent_tool(
            db,
            user,
            tool_name=tool,
            arguments=args,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            user_message=user_message,
            loop_state=loop_state,
        )
        # 记录到 loop_state，便于子智能体完成后展示为独立步骤
        if loop_state is not None:
            try:
                body = json.loads(raw)
                ok = bool(body.get("ok"))
                summary = str(body.get("summary") or "")[:240]
            except json.JSONDecodeError:
                ok = False
                summary = str(raw)[:240]
            record_executed_tool_call(
                loop_state,
                tool_name=tool,
                raw_args=args,
                result_text=raw,
                summary=summary or ("完成" if ok else "失败"),
                step_id=step_id,
            )
        # 实时推送：单个 batch 步骤完成 → 父 loop_state 的 progress_queue
        _push_batch_progress(raw, loop_state, tool, args)
        try:
            body = json.loads(raw)
            return f"[{idx}] {tool}: {str(body.get('summary') or raw)[:240]}"
        except json.JSONDecodeError:
            return f"[{idx}] {tool}: {raw[:240]}"

    tasks = [_run_one(idx, tool, args) for idx, tool, args in validated]
    summaries: list[str] = []
    for coro in asyncio.as_completed(tasks):
        try:
            r = await coro
            summaries.append(r)
        except Exception as e:
            summaries.append(f"[x] 执行异常：{e}")

    text = "\n".join(summaries)
    return json.dumps(
        {"ok": True, "summary": text[:1200], "step_count": len(summaries)},
        ensure_ascii=False,
    )
