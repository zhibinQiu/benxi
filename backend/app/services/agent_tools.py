"""AI 智能体 OpenAI 兼容 tools 定义与执行（Skill 管理 / 记忆 / 加载 / 检索）。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from app.core.agent_loop_state import LoopState

from sqlalchemy.orm import Session

from app.core.permissions import user_has_permission
from app.models.org import User

_BROWSER_SESSION_TOOLS = frozenset(
    {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_fill",
        "browser_run_task",
        "browser_replay_workflow",
    }
)


def push_intermediate_progress(
    loop_state: LoopState | None,
    phase: str,
    title: str,
    detail: str = "",
    *,
    tool: str = "",
    tool_name: str = "",
) -> None:
    """工具内部调用的通用中间进度推送。

    任何工具在执行过程中可调用此函数将进度推送至前端 SSE 流。
    phase 取值: tool_call / tool_result / llm_thinking / llm_decision / info
    """
    if loop_state is None:
        return
    # 检查所有可能的 progress_queue 位置
    q: asyncio.Queue | None = loop_state.get("_progress_queue")
    if q is None:
        q = loop_state.get("_parent_progress_queue")
    if q is None:
        return
    q.put_nowait({
        "phase": phase,
        "title": title[:120],
        "detail": detail[:240],
        "tool": tool or tool_name,
        "tool_name": tool_name,
        "step_id": f"ip-{uuid.uuid4().hex[:8]}",
    })


def mark_browser_session_used(loop_state: LoopState | None) -> None:
    if loop_state is not None:
        loop_state["browser_session_used"] = True


def record_stream_screenshot_attachment(
    loop_state: LoopState | None,
    data: dict[str, Any] | None,
) -> None:
    """记录浏览器截图供流式 attachment 与最终回复 Markdown 复用。"""
    if not loop_state or not isinstance(data, dict):
        return
    api_path = str(data.get("screenshot_api_path") or "").strip()
    if not api_path:
        return
    att = {
        "type": "image",
        "url": api_path,
        "title": str(data.get("title") or "浏览器截图"),
    }
    loop_state.setdefault("stream_attachments", []).append(att)
    collected = loop_state.setdefault("collected_attachments", [])
    seen = {
        str(item.get("url") or "").strip()
        for item in collected
        if isinstance(item, dict)
    }
    if api_path not in seen:
        collected.append(dict(att))
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)
from app.core.tool_skill_taxonomy import is_global_atomic_tool
from app.tool_center.agent_bridge import execute_global_atomic_tool_json
from app.core.agent_tool_args import (
    ADMIN_DEPT_TOOL_NAMES,
    ADMIN_USER_TOOL_NAMES,
    AGENT_SKILL_TOOL_NAMES,
    BROWSER_TOOL_NAMES,
    DOCUMENT_TOOL_NAMES,
    ORCHESTRATION_TOOL_NAMES,
    PLATFORM_TOOL_NAMES,
    RETRIEVAL_TOOL_NAMES,
    build_tool_specs,
    validate_tool_arguments,
)
from app.skills.executor import invoke_skill_tool
from app.skills.types import SkillInvocationContext, SkillSource

_logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUNDLED_SKILL_DIR = _REPO_ROOT / "examples" / "agent-skills"

_SKILL_MD_AUTO_INJECT_MAX_CHARS = 12000


def fetch_uploaded_skill_md(
    db: Session,
    skill_name: str,
    *,
    user: User | None = None,
    max_chars: int = _SKILL_MD_AUTO_INJECT_MAX_CHARS,
) -> str | None:
    """读取上传型 Skill 的 SKILL.md 全文，供系统自动注入上下文。"""
    from app.skills.catalog import get_merged_skill_definition
    from app.services.agent_skill_service import get_skill_file_content

    name = (skill_name or "").strip()
    if not name:
        return None
    defn = get_merged_skill_definition(db, name, user=user)
    body: str | None = None
    if defn and defn.source == SkillSource.UPLOADED and defn.skill_id:
        try:
            file_out = get_skill_file_content(db, defn.skill_id, "SKILL.md")
            body = (file_out.text or "").strip()
        except Exception:
            _logger.debug("读取 SKILL.md 失败: %s", name, exc_info=True)
    if not body:
        bundled = _BUNDLED_SKILL_DIR / name / "SKILL.md"
        if bundled.is_file():
            try:
                body = bundled.read_text(encoding="utf-8").strip()
            except OSError:
                _logger.debug("读取内置示例 SKILL.md 失败: %s", bundled, exc_info=True)
    if not body:
        return None
    limit = max(512, int(max_chars or _SKILL_MD_AUTO_INJECT_MAX_CHARS))
    if len(body) > limit:
        body = body[: limit - 1] + "…（已截断）"
    return body


def build_skill_md_context_block(
    skill_name: str,
    skill_md: str,
    *,
    has_script: bool | None = None,
) -> str:
    """格式化为注入 tool loop 的 SKILL.md 说明块。"""
    name = (skill_name or "").strip()
    body = (skill_md or "").strip()
    if not name or not body:
        return ""
    lines = [
        f"【发展技能 `{name}` · SKILL.md（系统自动加载，无需 load_uploaded_skill）】",
        body,
    ]
    if has_script is False:
        lines.append(
            "（本包为**指令型**技能：SKILL.md 已包含完整答复指引——请直接按 SKILL.md 中的要求回答用户。"
            "SKILL.md 的内容已在上下文中供你直接引用执行。"
            "**禁止**脱离 SKILL.md 凭空编造未提及的信息和数据。"
            "**禁止**调用 run_skill_script——本技能无可执行脚本）"
        )
    elif has_script is True:
        lines.append(
            "（本包含 Python 脚本：需要执行时使用 run_skill_script，入口 main.py/run.py）"
        )
    return "\n".join(lines)


def maybe_inject_skill_dev_playbook(
    loop_state: LoopState,
    messages: list[dict[str, Any]],
    *,
    agent_id: str | None,
    skill_mgmt: bool,
) -> list[dict[str, Any]]:
    """技能开发专精：注入发展 Skill 编写规范（每轮 loop 一次）。"""
    if not skill_mgmt or (agent_id or "").strip() != "skill-dev":
        return messages
    if loop_state.get("skill_dev_playbook_injected"):
        return messages
    from app.core.skill_dev_playbook import build_skill_dev_playbook_block

    block = build_skill_dev_playbook_block()
    loop_state["skill_dev_playbook_injected"] = True
    out = [dict(m) for m in messages]
    out.append({"role": "system", "content": block})
    return out


def maybe_inject_skill_md(
    db: Session,
    user: User,
    loop_state: LoopState,
    messages: list[dict[str, Any]],
    skill_name: str,
) -> list[dict[str, Any]]:
    """若尚未注入，将 SKILL.md 追加为 system 说明。"""
    name = (skill_name or "").strip()
    if not name:
        return messages
    injected = {
        str(s).strip() for s in (loop_state.get("injected_skill_mds") or []) if str(s).strip()
    }
    if name in injected:
        return messages
    skill_md = fetch_uploaded_skill_md(db, name, user=user)
    has_script = None
    try:
        from app.services.agent_skill_service import uploaded_skill_has_script

        has_script = uploaded_skill_has_script(db, name)
    except Exception:
        has_script = None
    block = build_skill_md_context_block(name, skill_md or "", has_script=has_script)
    if not block:
        return messages
    loop_state["injected_skill_mds"] = list(injected | {name})
    loop_state["planned_uploaded_skill"] = name
    out = [dict(m) for m in messages]
    out.append({"role": "system", "content": block})
    return out


_ATOMIC_RETRIEVAL_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(RETRIEVAL_TOOL_NAMES)

_RUN_SKILL_SCRIPT_SPEC: dict[str, Any] = build_tool_specs(("run_skill_script",))[0]

_BROWSER_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(BROWSER_TOOL_NAMES)

_DOCUMENT_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(DOCUMENT_TOOL_NAMES)

_PLATFORM_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(PLATFORM_TOOL_NAMES)

_ORCHESTRATION_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(ORCHESTRATION_TOOL_NAMES)

AGENT_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(AGENT_SKILL_TOOL_NAMES)

_ADMIN_USER_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(ADMIN_USER_TOOL_NAMES)

_ADMIN_DEPT_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(ADMIN_DEPT_TOOL_NAMES)

# 父子分离的委派工具集：invoke_skill / web_search 仅子智能体可见，
# 父智能体的 build_agent_tool_specs（allowed_names=None）自然看不到，
# 子智能体通过 allowed_names 显式申请，merge 时补入。
_SUBCONTRACT_TOOL_SPECS: list[dict[str, Any]] = build_tool_specs(("invoke_skill", "web_search"))


def build_agent_tool_specs(
    db: Session,
    user: User,
    *,
    allowed_names: set[str] | None = None,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    """按用户权限与平台开关组装可用原子工具列表。

    设计原则：
    - orchestrator（调度智能体）：仅挂载通用能力——技能运行时工具 + 编排工具 + 系统通知工具。
      不挂载：联网检索(web_search)、知识图谱(kg_query)、知识库检索(knowledge_retrieve)、
      文档CRUD、浏览器、用户/部门管理等专精工具。
      这些专精操作由路由分配到对应的专精 Agent 执行。
    - 其他 Agent：挂载完整工具集。
    """
    from app.config import get_settings

    is_orchestrator = (agent_id or "").strip() == "orchestrator"

    specs: list[dict[str, Any]] = list(AGENT_TOOL_SPECS)
    specs.extend(_ORCHESTRATION_TOOL_SPECS)

    if is_orchestrator:
        # ── 调度智能体：仅系统通知工具（待办/定时提醒） ──
        NOTIFICATION_TOOL_NAMES = frozenset({
            "send_notification",
            "schedule_notification",
            "list_scheduled_notifications",
            "cancel_scheduled_notification",
        })
        for spec in _PLATFORM_TOOL_SPECS:
            name = str((spec.get("function") or {}).get("name") or "")
            if name in NOTIFICATION_TOOL_NAMES:
                specs.append(spec)
        if get_settings().agent_skill_script_enabled:
            specs.append(_RUN_SKILL_SCRIPT_SPEC)
    else:
        # ── 专精/通用路径：挂载完整工具集 ──
        specs.extend(_ATOMIC_RETRIEVAL_TOOL_SPECS)
        specs.extend(_DOCUMENT_TOOL_SPECS)
        specs.extend(_PLATFORM_TOOL_SPECS)
        if user_has_permission(db, user, "admin.user"):
            specs.extend(_ADMIN_USER_TOOL_SPECS)
        if user_has_permission(db, user, "admin.dept"):
            specs.extend(_ADMIN_DEPT_TOOL_SPECS)
        from app.domains.knowledge import knowledge

        if not knowledge.enabled():
            specs = [
                s
                for s in specs
                if str((s.get("function") or {}).get("name") or "")
                not in ("sync_document_knowledge", "reindex_document")
            ]
        if get_settings().agent_skill_script_enabled:
            specs.append(_RUN_SKILL_SCRIPT_SPEC)
        from app.integrations.browser_automation.browser_config import get_browser_rpa_config

        if get_browser_rpa_config(db).enabled:
            specs.extend(_BROWSER_TOOL_SPECS)
    if allowed_names is not None:
        _spec_name = lambda s: str((s.get("function") or {}).get("name") or "")
        specs = [s for s in specs if _spec_name(s) in allowed_names]
        # 子智能体显式申请的委派工具（invoke_skill / web_search）补入
        seen = {_spec_name(s) for s in specs}
        specs.extend(
            s for s in _SUBCONTRACT_TOOL_SPECS
            if _spec_name(s) in allowed_names and _spec_name(s) not in seen
        )
    # ── 父智能体（allowed_names=None）路径 ──
    # invoke_skill 不在 AGENT_TOOL_SPECS 中（已从 SKILL_RUNTIME_TOOL_NAMES 移除），
    # 父路径自然看不到它。web_search 仍存在于 _ATOMIC_RETRIEVAL_TOOL_SPECS 中，
    # 后续待整体迁移至委派列表后一并移除。
    return specs


def agent_tool_names() -> set[str]:
    from app.config import get_settings

    names = {
        spec["function"]["name"]
        for spec in AGENT_TOOL_SPECS
        if spec.get("function", {}).get("name")
    }
    names.update(
        spec["function"]["name"]
        for spec in _ATOMIC_RETRIEVAL_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    run_name = _RUN_SKILL_SCRIPT_SPEC.get("function", {}).get("name")
    if run_name:
        names.add(run_name)
    if get_settings().agent_browser_enabled:
        names.update(
            spec["function"]["name"]
            for spec in _BROWSER_TOOL_SPECS
            if spec.get("function", {}).get("name")
        )
    names.update(
        spec["function"]["name"]
        for spec in _ORCHESTRATION_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    names.update(
        spec["function"]["name"]
        for spec in _DOCUMENT_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    names.update(
        spec["function"]["name"]
        for spec in _PLATFORM_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    names.update(
        spec["function"]["name"]
        for spec in _ADMIN_USER_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    names.update(
        spec["function"]["name"]
        for spec in _ADMIN_DEPT_TOOL_SPECS
        if spec.get("function", {}).get("name")
    )
    return names


def _tool_result(ok: bool, summary: str, data: Any = None) -> str:
    return json.dumps(
        {"ok": ok, "summary": summary, "data": data},
        ensure_ascii=False,
    )


def _parse_extra_files(raw: Any) -> dict[str, str] | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        out = {str(k).strip(): str(v) for k, v in raw.items() if str(k).strip()}
        return out or None
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("file_path") or "").strip()
            if path:
                out[path] = str(item.get("content") or "")
        return out or None
    return None


def _extra_files_has_python(extra_files: dict[str, str] | None) -> bool:
    if not extra_files:
        return False
    return any(str(path).endswith(".py") for path in extra_files)


async def _execute_invoke_skill(
    ctx: SkillInvocationContext,
    *,
    params: dict[str, Any],
    user_message: str,
    loop_state: LoopState | None,
) -> str:
    """Skill 运行时入口：LLM 调用 invoke_skill。"""
    from app.skills.catalog import get_merged_skill_definition

    skill_name = str(params.get("skill_name") or "").strip()
    action = str(params.get("action") or "").strip()
    raw_params = params.get("params")
    skill_params = raw_params if isinstance(raw_params, dict) else {}

    if not skill_name or not action:
        return _tool_result(False, "invoke_skill 需要 skill_name 与 action")

    ctx.user_message = user_message
    ctx.loop_state = loop_state

    from app.core.tool_skill_taxonomy import SKILL_SKILL_DEV, is_skill_runtime_tool

    if is_skill_runtime_tool(skill_name):
        return _tool_result(
            False,
            f"请勿 invoke_skill(skill_name=`{skill_name}`)。"
            f"技能管理请 invoke_skill({SKILL_SKILL_DEV}, call, "
            f"{{operation: `{skill_name}`, ...}})",
        )

    if loop_state is not None and not loop_state.get("isolated_subagent"):
        allowed = loop_state.get("allowed_skill_names")
        if allowed and skill_name not in {str(x).strip() for x in allowed if str(x).strip()}:
            agent_id = str((loop_state or {}).get("agent_id") or "").strip()
            if agent_id == "skill-dev":
                if skill_name in {
                    "browser-automation",
                    "web-search",
                    "knowledge-search",
                    "kg",
                }:
                    kind = "auto" if skill_name == "browser-automation" else "search"
                    return _tool_result(
                        False,
                        f"请用 invoke_context_subagent(kind={kind}, task=...) 委托子 Agent 调用 "
                        f"`{skill_name}`，勿在本专精直接 invoke_skill 系统 Skill。",
                    )
            return _tool_result(
                False,
                f"当前智能体未绑定 Skill `{skill_name}`；"
                "本域调研请用 invoke_context_subagent(kind=search|auto)，"
                "勿直接 invoke_skill 跨域检索 Skill",
            )

    defn = get_merged_skill_definition(ctx.db, skill_name, user=ctx.user)
    if not defn:
        return _tool_result(False, f"Skill 不存在: {skill_name}")
    if defn.tools and not any(t.name == action for t in defn.tools):
        return _tool_result(False, f"Skill `{skill_name}` 无 action `{action}`")

    ctx.skill_name = skill_name
    ctx.belong_agent = str((loop_state or {}).get("agent_id") or ctx.belong_agent or "")
    result = await invoke_skill_tool(
        ctx,
        skill_name=skill_name,
        tool_name=action,
        params=skill_params,
    )
    if not result.ok:
        return _tool_result(False, result.summary or f"Skill `{skill_name}.{action}` 失败")

    # Extract citations from deep-research skill and persist to loop_state
    if result.ok and skill_name == "deep-research" and result.data and isinstance(result.data, dict):
        citations = result.data.get("citations")
        if isinstance(citations, list) and citations and loop_state is not None:
            existing = loop_state.setdefault("citations", [])
            existing.extend(citations)

    from app.core.tool_skill_taxonomy import RETRIEVAL_SKILL_ATOMIC_MAP
    from app.tool_center.agent_bridge import _format_retrieval_json, _prepare_retrieval_params

    mapped = RETRIEVAL_SKILL_ATOMIC_MAP.get(skill_name)
    if mapped and action == mapped[1]:
        atomic_name = mapped[0]
        prepared = _prepare_retrieval_params(
            atomic_name,
            skill_params,
            user_message=user_message,
            loop_state=loop_state,
        )
        query = prepared[1] if prepared else user_message
        return _format_retrieval_json(
            atomic_name,
            result=result,
            query=query or user_message,
            loop_state=loop_state,
            db=ctx.db,
        )

    extra: dict[str, Any] = {"skill_name": skill_name, "action": action}
    if result.data is not None:
        extra["data"] = result.data
    if (
        skill_name == "document-library"
        and action == "call"
        and isinstance(result.data, dict)
        and str(skill_params.get("operation") or "") == "read_document_content"
        and loop_state is not None
    ):
        full_text = str(result.data.get("full_text") or "").strip()
        if full_text:
            loop_state["agent_document_context"] = {
                "title": str(result.data.get("title") or "").strip(),
                "full_text": full_text[:40000],
                "char_count": int(result.data.get("char_count") or len(full_text)),
            }
    return _tool_result(True, result.summary, extra)


def _parse_uuid(value: Any, *, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无效的 {field}") from exc


def _execute_document_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    params: dict[str, Any],
) -> str | None:
    from app.core.exceptions import AppError
    from app.services import agent_document_service as doc_svc

    handlers = {
        "search_documents_by_name": lambda: doc_svc.search_documents_by_name_for_agent(
            db,
            user,
            name=str(params.get("name") or ""),
            scope=str(params["scope"]).strip() if params.get("scope") else None,
            limit=int(params.get("limit") or 20),
        ),
        "read_document_content": lambda: doc_svc.read_document_content_for_agent(
            db,
            user,
            document_id=_parse_uuid(params["document_id"], field="document_id")
            if params.get("document_id")
            else None,
            document_name=str(params.get("document_name") or "") or None,
            max_chars=int(params.get("max_chars") or 16000),
        ),
        "list_library_documents": lambda: doc_svc.list_library_documents_for_agent(
            db,
            user,
            scope=str(params.get("scope") or "personal").strip(),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
            keyword=params.get("keyword"),
            limit=int(params.get("limit") or 30),
        ),
        "list_manageable_documents": lambda: doc_svc.list_manageable_documents(
            db,
            user,
            keyword=params.get("keyword"),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
            scope=str(params.get("scope") or "personal").strip(),
            limit=int(params.get("limit") or 20),
        ),
        "list_document_folders": lambda: doc_svc.list_document_folders_for_agent(
            db,
            user,
            scope=str(params.get("scope") or "").strip(),
        ),
        "create_kb_folder": lambda: doc_svc.create_kb_folder_for_agent(
            db,
            user,
            name=str(params.get("name") or ""),
            scope=str(params.get("scope") or "personal").strip(),
            description=str(params.get("description") or ""),
        ),
        "create_library_document": lambda: doc_svc.create_library_document_for_agent(
            db,
            user,
            title=str(params.get("title") or ""),
            content=str(params.get("content") or ""),
            scope=str(params.get("scope") or "personal").strip(),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
            description=str(params.get("description") or ""),
            content_format=str(params.get("content_format") or "markdown"),
        ),
        "rename_document": lambda: doc_svc.rename_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            new_title=str(params.get("new_title") or ""),
        ),
        "move_document": lambda: doc_svc.move_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
        ),
        "share_document": lambda: doc_svc.share_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            user_names=list(params.get("user_names") or []),
            level=str(params.get("level") or "query"),
        ),
        "delete_document": lambda: doc_svc.delete_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            confirm=bool(params.get("confirm")),
        ),
        "update_kb_folder": lambda: doc_svc.update_kb_folder_for_agent(
            db,
            user,
            scope=str(params.get("scope") or "personal").strip(),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
            name=str(params["name"]).strip() if params.get("name") is not None else None,
            description=str(params["description"]).strip()
            if params.get("description") is not None
            else None,
        ),
        "delete_kb_folder": lambda: doc_svc.delete_kb_folder_for_agent(
            db,
            user,
            scope=str(params.get("scope") or "personal").strip(),
            folder_id=_parse_uuid(params["folder_id"], field="folder_id")
            if params.get("folder_id")
            else None,
            folder_name=str(params.get("folder_name") or "") or None,
            confirm=bool(params.get("confirm")),
        ),
        "sync_document_knowledge": lambda: doc_svc.sync_document_knowledge_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
        ),
        "reindex_document": lambda: doc_svc.reindex_document_for_agent(
            db,
            user,
            document_id=_parse_uuid(params.get("document_id"), field="document_id"),
            parser_id=str(params.get("parser_id") or "") or None,
            resync=bool(params.get("resync")),
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return None
    try:
        data = handler()
        if isinstance(data, dict) and data.get("message"):
            return _tool_result(True, str(data["message"]), data)
        if isinstance(data, list):
            return _tool_result(
                True,
                f"共 {len(data)} 条",
                {"items": data, "count": len(data)},
            )
        return _tool_result(True, "操作完成", data)
    except AppError as exc:
        detail = exc.detail
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        return _tool_result(False, msg)
    except ValueError as exc:
        return _tool_result(False, str(exc))


def _execute_platform_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    params: dict[str, Any],
) -> str | None:
    from app.core.exceptions import AppError
    from app.services import agent_platform_service as plat_svc

    handlers = {
        "list_todos": lambda: plat_svc.list_todos_for_agent(
            db,
            user,
            status=str(params["status"]).strip() if params.get("status") else None,
        ),
        "create_todo": lambda: plat_svc.create_todo_for_agent(
            db,
            user,
            title=str(params.get("title") or ""),
            note=str(params.get("note") or ""),
        ),
        "update_todo": lambda: plat_svc.update_todo_for_agent(
            db,
            user,
            todo_id=_parse_uuid(params.get("todo_id"), field="todo_id"),
            title=str(params["title"]).strip() if params.get("title") is not None else None,
            note=str(params["note"]).strip() if params.get("note") is not None else None,
            status=str(params["status"]).strip() if params.get("status") is not None else None,
        ),
        "delete_todo": lambda: plat_svc.delete_todo_for_agent(
            db,
            user,
            todo_id=_parse_uuid(params.get("todo_id"), field="todo_id"),
        ),
        "send_notification": lambda: plat_svc.send_notification_for_agent(
            db,
            user,
            title=str(params.get("title") or ""),
            body=str(params.get("body") or ""),
            link=str(params.get("link") or "") or None,
        ),
        "schedule_notification": lambda: plat_svc.schedule_notification_for_agent(
            db,
            user,
            title=str(params.get("title") or ""),
            body=str(params.get("body") or ""),
            link=str(params.get("link") or "") or None,
            scheduled_at=str(params.get("scheduled_at") or ""),
        ),
        "list_scheduled_notifications": lambda: plat_svc.list_scheduled_notifications_for_agent(
            db,
            user,
            limit=int(params.get("limit") or 20),
        ),
        "cancel_scheduled_notification": lambda: plat_svc.cancel_scheduled_notification_for_agent(
            db,
            user,
            notification_id=_parse_uuid(
                params.get("notification_id"), field="notification_id"
            ),
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return None
    try:
        data = handler()
        if isinstance(data, dict) and data.get("message"):
            return _tool_result(True, str(data["message"]), data)
        if isinstance(data, list):
            return _tool_result(
                True,
                f"共 {len(data)} 条",
                {"items": data, "count": len(data)},
            )
        return _tool_result(True, "操作完成", data)
    except AppError as exc:
        detail = exc.detail
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        return _tool_result(False, msg)
    except ValueError as exc:
        return _tool_result(False, str(exc))


def _execute_admin_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    params: dict[str, Any],
) -> str | None:
    from app.core.exceptions import AppError
    from app.services import agent_admin_service as admin_svc

    handlers = {
        "list_users": lambda: admin_svc.list_users_for_agent(
            db,
            user,
            page=int(params.get("page") or 1),
            page_size=int(params.get("page_size") or 20),
            keyword=str(params.get("keyword") or "") or None,
        ),
        "create_user": lambda: admin_svc.create_user_for_agent(
            db,
            user,
            phone=str(params.get("phone") or ""),
            email=str(params.get("email") or ""),
            display_name=str(params.get("display_name") or ""),
            password=str(params.get("password") or ""),
            status=str(params.get("status") or "active"),
            department_id=_parse_uuid(params["department_id"], field="department_id")
            if params.get("department_id")
            else None,
            department_name=str(params.get("department_name") or "") or None,
        ),
        "update_user": lambda: admin_svc.update_user_for_agent(
            db,
            user,
            user_id=_parse_uuid(params["user_id"], field="user_id")
            if params.get("user_id")
            else None,
            user_name=str(params.get("user_name") or "") or None,
            phone=str(params.get("phone") or "") or None,
            email=str(params.get("email") or "") or None,
            display_name=str(params.get("display_name") or "") or None,
            password=str(params.get("password") or "") or None,
            status=str(params.get("status") or "") or None,
            department_id=_parse_uuid(params["department_id"], field="department_id")
            if params.get("department_id")
            else None,
            department_name=str(params.get("department_name") or "") or None,
            clear_department=bool(params.get("clear_department")),
        ),
        "delete_user": lambda: admin_svc.delete_user_for_agent(
            db,
            user,
            user_id=_parse_uuid(params["user_id"], field="user_id")
            if params.get("user_id")
            else None,
            user_name=str(params.get("user_name") or "") or None,
            confirm=bool(params.get("confirm")),
        ),
        "list_departments": lambda: admin_svc.list_departments_for_agent(db, user),
        "create_department": lambda: admin_svc.create_department_for_agent(
            db,
            user,
            name=str(params.get("name") or ""),
            parent_id=_parse_uuid(params["parent_id"], field="parent_id")
            if params.get("parent_id")
            else None,
            parent_name=str(params.get("parent_name") or "") or None,
        ),
        "update_department": lambda: admin_svc.update_department_for_agent(
            db,
            user,
            department_id=_parse_uuid(params["department_id"], field="department_id")
            if params.get("department_id")
            else None,
            department_name=str(params.get("department_name") or "") or None,
            name=str(params.get("name") or "") or None,
            parent_id=_parse_uuid(params["parent_id"], field="parent_id")
            if params.get("parent_id")
            else None,
            parent_name=str(params.get("parent_name") or "") or None,
            clear_parent=bool(params.get("clear_parent")),
        ),
        "delete_department": lambda: admin_svc.delete_department_for_agent(
            db,
            user,
            department_id=_parse_uuid(params["department_id"], field="department_id")
            if params.get("department_id")
            else None,
            department_name=str(params.get("department_name") or "") or None,
            confirm=bool(params.get("confirm")),
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return None
    try:
        data = handler()
        if tool_name == "list_users" and isinstance(data, dict):
            from app.services.agent_admin_reply import summarize_user_list

            return _tool_result(True, summarize_user_list(data), data)
        if tool_name == "list_departments" and isinstance(data, list):
            return _tool_result(
                True,
                f"共 {len(data)} 个部门",
                {"items": data, "count": len(data)},
            )
        if isinstance(data, dict) and data.get("message"):
            return _tool_result(True, str(data["message"]), data)
        if isinstance(data, list):
            return _tool_result(
                True,
                f"共 {len(data)} 条",
                {"items": data, "count": len(data)},
            )
        return _tool_result(True, "操作完成", data)
    except AppError as exc:
        detail = exc.detail
        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        return _tool_result(False, msg)
    except ValueError as exc:
        return _tool_result(False, str(exc))


async def _execute_create_skill(
    db: Session,
    user: User,
    *,
    params: dict[str, Any],
    user_message: str,
    loop_state: LoopState | None,
) -> str:
    """创建发展技能（create_skill tool 实现）。"""
    from app.core.agent_tool_context import has_skill_research_context
    from app.core.skill_dev_playbook import ensure_script_extra_files, enrich_skill_repair_reason, slugify_skill_name
    from app.services import agent_skill_service as svc
    from app.services.agent_skill_router import (
        is_skill_management_message,
        skill_creation_needs_site_research,
        skill_creation_requires_python_script,
    )

    auto_creation = bool(loop_state and loop_state.get("auto_skill_creation"))
    if is_skill_management_message(user_message) and not has_skill_research_context(
        loop_state,
        needs_site_research=skill_creation_needs_site_research(user_message),
    ) and not auto_creation:
        return _tool_result(
            False,
            "创建 Skill 前须先完成调研：invoke_context_subagent"
            "（网页 browser_digest→browser-automation，浏览器未开启时自动 explore；"
            "公开信息 explore→web-search 等 + queries）。"
            "完成后 invoke_skill(skill-development, call, {operation: create_skill, ...})",
        )

    extra_files = _parse_extra_files(params.get("extra_files"))
    _orig_main = (extra_files or {}).get("main.py", "")
    has_py = _extra_files_has_python(extra_files)
    if has_py or skill_creation_requires_python_script(user_message):
        try:
            extra_files = ensure_script_extra_files(
                extra_files,
                needs_url=skill_creation_needs_site_research(user_message),
            )
        except Exception as exc:
            return _tool_result(False, enrich_skill_repair_reason(str(exc)))

    skill = svc.create_generated_skill(
        db,
        user,
        name=str(params.get("name") or ""),
        description=str(params.get("description") or ""),
        skill_md_body=str(params.get("skill_md_body") or ""),
        replace_existing=bool(params.get("replace_existing")),
        extra_files=extra_files,
        needs_review=auto_creation,
        mount_agent="orchestrator",
    )
    requested_slug = slugify_skill_name(str(params.get("name") or ""))
    create_summary = f"已创建 Skill `{skill.name}`"
    if requested_slug and skill.name != requested_slug:
        create_summary += (
            f"（`{requested_slug}` 已存在，已自动重命名为 `{skill.name}`）"
        )
    _new_main = (extra_files or {}).get("main.py", "")
    if _orig_main and _new_main and _orig_main != _new_main:
        create_summary += "（注意：传入的 main.py 未通过校验，已自动替换为平台标准脚手架，请 review 后用 update_uploaded_skill_file 自定逻辑）"
    if loop_state is not None:
        loop_state["planned_uploaded_skill"] = skill.name
        loop_state["pending_skill_md_inject"] = skill.name
        created = list(loop_state.get("created_uploaded_skills") or [])
        if skill.name not in created:
            created.append(skill.name)
        loop_state["created_uploaded_skills"] = created
    skill_md = fetch_uploaded_skill_md(db, skill.name, user=user, max_chars=4000)
    create_data: dict[str, Any] = {
        "skill_id": str(skill.id),
        "name": skill.name,
        "source_type": skill.source_type,
    }
    if skill_md:
        create_data["skill_md"] = skill_md
    return _tool_result(True, create_summary, create_data)


async def _execute_browser_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    params: dict[str, Any],
    conversation_id: str | None,
    loop_state: LoopState | None = None,
    user_message: str = "",
) -> str | None:
    from app.core.agent_tool_context import append_skill_explore_context
    from app.services import browser_rpa_service as rpa
    from app.services.agent_skill_router import (
        is_skill_management_message,
    )

    def _track_skill_explore(data: dict[str, Any] | None) -> None:
        if not loop_state or not isinstance(data, dict):
            return
        if not is_skill_management_message(user_message):
            return
        if tool_name == "browser_navigate":
            url = str(data.get("url") or "").strip()
            title = str(data.get("title") or "").strip()
            if url:
                append_skill_explore_context(
                    loop_state,
                    f"页面导航：{title or url}\nURL：{url}",
                )
            return
        if tool_name != "browser_snapshot":
            return
        url = str(data.get("url") or "").strip()
        title = str(data.get("title") or "").strip()
        preview = str(data.get("text_preview") or "").strip()
        refs = data.get("refs") or []
        ref_lines: list[str] = []
        if isinstance(refs, list):
            for item in refs[:12]:
                if not isinstance(item, dict):
                    continue
                ref_lines.append(
                    f"- {item.get('ref')}: {item.get('role')} {item.get('name') or ''}".strip()
                )
        block_parts = [f"页面快照：{title or url}"]
        if url:
            block_parts.append(f"URL：{url}")
        if preview:
            block_parts.append(f"可见文本摘要：\n{preview}")
        if ref_lines:
            block_parts.append("可交互元素（节选）：\n" + "\n".join(ref_lines))
        append_skill_explore_context(loop_state, "\n".join(block_parts))

    def _track_screenshot(data: dict[str, Any] | None) -> None:
        record_stream_screenshot_attachment(loop_state, data)

    handlers = {
        "browser_navigate": lambda: rpa.browser_navigate(
            db,
            user,
            conversation_id=conversation_id,
            url=str(params.get("url") or ""),
        ),
        "browser_snapshot": lambda: rpa.browser_snapshot(
            db, user, conversation_id=conversation_id
        ),
        "browser_click": lambda: rpa.browser_click(
            db,
            user,
            conversation_id=conversation_id,
            ref=str(params.get("ref") or ""),
        ),
        "browser_type": lambda: rpa.browser_type(
            db,
            user,
            conversation_id=conversation_id,
            ref=str(params.get("ref") or ""),
            text=str(params.get("text") or ""),
            submit=bool(params.get("submit")),
        ),
        "browser_fill": lambda: rpa.browser_fill(
            db,
            user,
            conversation_id=conversation_id,
            fields=list(params.get("fields") or []),
        ),
        "browser_screenshot": lambda: rpa.browser_screenshot(
            db,
            user,
            conversation_id=conversation_id,
            full_page=bool(params.get("full_page")),
        ),
        "browser_save_workflow": lambda: rpa.browser_save_workflow(
            db,
            user,
            conversation_id=conversation_id,
            name=str(params.get("name") or ""),
            description=str(params.get("description") or ""),
            parameters=list(params.get("parameters") or []),
            replace_existing=params.get("replace_existing", True),
        ),
        "browser_close_session": lambda: rpa.browser_close_session(
            user, conversation_id=conversation_id
        ),
        "browser_replay_workflow": lambda: rpa.browser_replay_workflow(
            db,
            user,
            skill_name=str(params.get("skill_name") or ""),
            parameters={
                str(k): str(v)
                for k, v in (params.get("parameters") or {}).items()
            }
            if isinstance(params.get("parameters"), dict)
            else {},
        ),
        "browser_run_task": lambda: rpa.browser_run_task(
            db,
            user,
            conversation_id=conversation_id,
            task=str(params.get("task") or ""),
            start_url=str(params.get("start_url") or ""),
            max_steps=int(params["max_steps"])
            if params.get("max_steps") is not None
            else None,
        ),
        "schedule_browser_workflow": lambda: rpa.schedule_browser_workflow(
            db,
            user,
            skill_name=str(params.get("skill_name") or ""),
            parameters={
                str(k): str(v)
                for k, v in (params.get("parameters") or {}).items()
            }
            if isinstance(params.get("parameters"), dict)
            else {},
            scheduled_at=str(params.get("scheduled_at") or "") or None,
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return None
    try:
        result = handler()
        import asyncio

        data = await result if asyncio.iscoroutine(result) else result
        if tool_name in _BROWSER_SESSION_TOOLS:
            mark_browser_session_used(loop_state)
        if tool_name in {"browser_navigate", "browser_snapshot"}:
            _track_skill_explore(data if isinstance(data, dict) else None)
        if tool_name in {"browser_screenshot", "browser_replay_workflow", "browser_run_task"}:
            _track_screenshot(data if isinstance(data, dict) else None)
        if isinstance(data, dict) and data.get("message"):
            return _tool_result(True, str(data["message"]), data)
        if tool_name == "browser_snapshot":
            ref_count = len((data or {}).get("refs") or [])
            return _tool_result(
                True,
                f"页面快照：{(data or {}).get('title') or ''}（{ref_count} 个可交互元素）",
                data,
            )
        if tool_name == "browser_screenshot":
            api_path = str((data or {}).get("screenshot_api_path") or "")
            summary = "截图已生成"
            if api_path:
                summary = (
                    f"截图已生成：{api_path}；"
                    "回复中请用 Markdown 图片引用此路径，勿用 screenshot_url"
                )
            compact = dict(data or {})
            compact.pop("screenshot_url", None)
            compact.pop("storage_key", None)
            return _tool_result(True, summary, compact)
        if tool_name == "browser_replay_workflow":
            conclusion = str((data or {}).get("conclusion") or "RPA 回放完成")
            return _tool_result(True, conclusion[:200], data)
        return _tool_result(True, "浏览器操作完成", data)
    except Exception as exc:
        return _tool_result(False, str(exc))


async def execute_agent_tool(
    db: Session,
    user: User,
    *,
    tool_name: str,
    arguments: dict[str, Any] | str | None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
    user_message: str = "",
    loop_state: LoopState | None = None,
    skill_name: str | None = None,
) -> str:
    name = (tool_name or "").strip()
    if name == "list_uploaded_skills":
        name = "list_agent_skills"
    tool_name = name
    params = _parse_tool_args(arguments)

    # 从 loop_state 回退 conversation_id / attachment_session_id
    if conversation_id is None and loop_state is not None:
        conversation_id = loop_state.get("conversation_id")
    if attachment_session_id is None and loop_state is not None:
        attachment_session_id = loop_state.get("attachment_session_id")

    if is_global_atomic_tool(name):
        return await execute_global_atomic_tool_json(
            db,
            user,
            name,
            params,
            conversation_id=conversation_id,
            attachment_session_id=attachment_session_id,
            user_message=user_message,
            loop_state=loop_state,
        )

    params, validation_error = validate_tool_arguments(name, params)
    if validation_error:
        return _tool_result(False, validation_error)

    ctx = SkillInvocationContext(
        db=db,
        user=user,
        conversation_id=conversation_id,
        attachment_session_id=attachment_session_id,
        belong_agent=str((loop_state or {}).get("agent_id") or "") or None,
        user_message=user_message,
        loop_state=loop_state,
        skill_name=skill_name,
    )

    try:
        if name == "fetch_url_content":
            url = str(params.get("url") or "").strip()
            max_chars = int(params.get("max_chars") or 50000)
            if not url:
                return _tool_result(False, "缺少 url 参数")
            from app.tool_center.adapters import _firecrawl_scrape

            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, _firecrawl_scrape, url)
            if not content:
                return _tool_result(False, f"无法获取网页内容: {url}")
            trimmed = content[:max_chars]
            return _tool_result(
                True, f"已获取 {len(content)} 字符",
                {"url": url, "content": trimmed, "char_count": len(trimmed)},
            )

        if name == "search_tools":
            from app.services.agent_tool_search import execute_search_skills_compat

            query = str(params.get("query") or user_message or "").strip()
            limit = int(params.get("limit") or 8)
            return await execute_search_skills_compat(
                db, user, query=query, limit=limit, loop_state=loop_state
            )

        if tool_name == "search_skills":
            from app.skills.catalog import search_skill_routes

            query = str(params.get("query") or user_message or "").strip()
            limit = int(params.get("limit") or 8)
            allowed = None
            if loop_state is not None:
                raw = loop_state.get("allowed_skill_names")
                if raw:
                    allowed = {str(x).strip() for x in raw if str(x).strip()}
            lines = search_skill_routes(db, user, query, limit=limit)
            if allowed is not None:
                lines = [ln for ln in lines if any(f"`{s}`" in ln for s in allowed)]
            text = "\n".join(lines) if lines else "未匹配到 Skill"
            return _tool_result(True, f"匹配 {len(lines)} 条 Skill 路由", {"lines": lines, "text": text})

        if tool_name == "describe_tool":
            from app.services.agent_tool_search import execute_describe_tool

            n = str(params.get("name") or "").strip()
            return await execute_describe_tool(
                db, user, name=n, loop_state=loop_state
            )

        if tool_name == "invoke_skill":
            return await _execute_invoke_skill(
                ctx,
                params=params,
                user_message=user_message,
                loop_state=loop_state,
            )

        if tool_name == "run_tool_batch":
            from app.services.agent_tool_search import execute_run_tool_batch

            raw_steps = params.get("steps") or []
            steps = raw_steps if isinstance(raw_steps, list) else []
            return await execute_run_tool_batch(
                db,
                user,
                steps=steps,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                user_message=user_message,
                loop_state=loop_state,
            )

        if tool_name == "invoke_context_subagent":
            from app.core.agent.subagent import execute_context_subagent
            from app.core.agent_tool_context import append_skill_explore_context
            from app.services.agent_skill_router import is_skill_management_message

            kind = str(params.get("kind") or "").strip()
            task = str(params.get("task") or user_message or "").strip()

            # 将子智能体开始信息存入 loop_state
            if loop_state is not None:
                subagent_progress = dict(loop_state.get("subagent_progress") or {})
                subagent_progress[kind] = {
                    "task": task[:400],
                    "status": "running",
                    "queries": [],
                    "urls": [],
                }
                loop_state["subagent_progress"] = subagent_progress

            result = await execute_context_subagent(
                db,
                user,
                kind=kind,
                task=task,
                queries=params.get("queries") if isinstance(params.get("queries"), list) else None,
                conversation_id=conversation_id,
                attachment_session_id=attachment_session_id,
                loop_state=loop_state,
            )

            # 技能管理消息的特殊处理（保持原有逻辑）
            if loop_state is not None and is_skill_management_message(user_message):
                try:
                    payload = json.loads(result)
                except json.JSONDecodeError:
                    payload = {}
                if payload.get("ok"):
                    summary = str(payload.get("summary") or "").strip()
                    if summary:
                        append_skill_explore_context(loop_state, summary)

            # 从子智能体执行步骤中提取搜索词和 URL，更新 loop_state
            sub_queries = []
            if loop_state is not None:
                sub_steps = list(loop_state.get("subagent_executed_steps") or [])
                for s in sub_steps:
                    tn = (s.get("tool_name") or "").strip()
                    ap = (s.get("args_preview") or "")
                    if tn == "web_search":
                        q = ap[:80]
                        if q and q not in sub_queries:
                            sub_queries.append(q)

            if loop_state is not None:
                sp = dict(loop_state.get("subagent_progress") or {})
                try:
                    payload = json.loads(result)
                except json.JSONDecodeError:
                    payload = {}
                sp[kind] = {
                    "task": task[:400],
                    "status": "done" if payload.get("ok") else "failed",
                    "queries": sub_queries[:5],
                    "urls": [],
                }
                loop_state["subagent_progress"] = sp

            return result

        if tool_name == "request_orchestrator_assist":
            if loop_state is None:
                loop_state = {}
            partial_lines = list(loop_state.get("tool_outcome_lines") or [])[-4:]
            loop_state["orchestrator_assist_request"] = {
                "reason": str(params.get("reason") or "").strip(),
                "needed_from": str(params.get("needed_from") or "").strip(),
                "suggested_agent_id": str(
                    params.get("suggested_agent_id") or ""
                ).strip()
                or None,
                "partial_progress": "；".join(str(x) for x in partial_lines if x)[
                    :500
                ],
            }
            return _tool_result(
                True,
                "已向调度层提交协助请求，请等待调度协调其他专精后继续本子任务",
                loop_state["orchestrator_assist_request"],
            )

        if tool_name == "list_agent_skills":
            from app.services.agent_skill_service import uploaded_skill_has_script
            from app.skills.catalog import _format_agent_catalog_prompt, _visible_catalog_skills
            from app.skills.types import SkillSource

            query = str(params.get("query") or user_message or "").strip()
            limit = int(params.get("limit") or 40)
            uploaded_only = bool(params.get("uploaded_only", True))
            visible = _visible_catalog_skills(
                db,
                user,
                query=query,
                uploaded_only=uploaded_only,
                limit=limit,
            )
            text = _format_agent_catalog_prompt(db, visible, resident_only=True)
            items: list[dict[str, Any]] = []
            for skill in visible:
                has_script: bool | None = None
                if skill.source == SkillSource.UPLOADED:
                    try:
                        has_script = uploaded_skill_has_script(db, skill.name)
                    except Exception:
                        has_script = None
                items.append(
                    {
                        "name": skill.name,
                        "title": skill.title,
                        "description": (skill.description or "")[:240],
                        "source": skill.source.value,
                        "kind": "developed"
                        if skill.source == SkillSource.UPLOADED
                        else "builtin",
                        "has_script": has_script,
                        "use_when": (skill.use_when or skill.description or "")[:160],
                    }
                )
            return _tool_result(
                True,
                f"共 {len(items)} 个技能",
                {"items": items, "count": len(items), "text": text},
            )

        if tool_name == "load_uploaded_skill":
            skill_name = str(params.get("skill_name") or "").strip()
            if not skill_name:
                return _tool_result(False, "缺少 skill_name")
            from app.services.agent_skill_router import validate_uploaded_skill_load
            from app.skills.catalog import get_merged_skill_definition

            defn = get_merged_skill_definition(db, skill_name, user=user)
            if not defn:
                return _tool_result(False, f"Skill 不存在: {skill_name}")
            planned = None
            created_skills: tuple[str, ...] = ()
            if loop_state:
                planned = str(loop_state.get("planned_uploaded_skill") or "").strip() or None
                created_skills = tuple(loop_state.get("created_uploaded_skills") or ())
            ok, reason = validate_uploaded_skill_load(
                user_message=user_message,
                skill_name=skill_name,
                skill_description=defn.description,
                skill_source=defn.source,
                planned_skill=planned,
                created_skills=created_skills,
            )
            if not ok:
                return _tool_result(False, reason)
            result = await invoke_skill_tool(
                ctx, skill_name=skill_name, tool_name="load"
            )
            return _tool_result(result.ok, result.summary, result.data)

        if tool_name == "run_skill_script":
            skill_name = str(params.get("skill_name") or "").strip()
            if not skill_name:
                return _tool_result(False, "缺少 skill_name")
            if loop_state is not None:
                loop_state["planned_uploaded_skill"] = skill_name
                invoked = list(loop_state.get("invoked_uploaded_skills") or [])
                if skill_name not in invoked:
                    invoked.append(skill_name)
                loop_state["invoked_uploaded_skills"] = invoked
            entry = str(params.get("entry") or "").strip()
            raw_args = params.get("args")
            args: list[str] = []
            if isinstance(raw_args, list):
                args = [str(a) for a in raw_args]
            elif isinstance(raw_args, str) and raw_args.strip():
                args = [raw_args.strip()]
            from app.services import agent_skill_service as svc
            from app.services.agent_skill_service import load_skill_workspace_bytes, _skill_by_name
            from app.services.agent_skill_router import (
                append_skill_repair_context,
                is_inconclusive_skill_conclusion,
            )

            skill = _skill_by_name(db, skill_name)
            files = load_skill_workspace_bytes(db, skill.id)
            from app.integrations.skill_script_executor import skill_files_have_executable_script

            if not skill_files_have_executable_script(files):
                file_names = sorted(files.keys())[:12]
                missing_msg = (
                    f"Skill `{skill_name}` 缺少 main.py，无法 run_skill_script。"
                    "请如实告知用户该技能缺少可执行脚本。"
                    "**禁止**根据技能名称或 SKILL.md 内容自行编造数据或分析结果。"
                    "无脚本时可用 update_uploaded_skill_file(skill_name, file_path='main.py', content=...) "
                    "创建入口脚本后再试。"
                )
                if file_names:
                    missing_msg += f" 当前文件: {', '.join(file_names)}"
                append_skill_repair_context(loop_state, skill_name, missing_msg[:400])
                return _tool_result(False, missing_msg)
            try:
                if b"workflow.json" in files and (
                    not entry or entry == "replay.py" or entry.endswith("replay.py")
                ):
                    from app.services.browser_rpa_service import replay_skill_workflow_script

                    payload = await replay_skill_workflow_script(
                        db, user, files=files, args=args
                    )
                else:
                    payload = svc.run_uploaded_skill_script(
                        db,
                        skill_name,
                        user=user,
                        entry=entry,
                        args=args,
                    )
            except Exception as exc:
                from app.core.skill_dev_playbook import enrich_skill_repair_reason

                reason = enrich_skill_repair_reason(str(exc))
                append_skill_repair_context(loop_state, skill_name, reason[:500])
                return _tool_result(
                    False,
                    f"Skill `{skill_name}` 执行失败：{reason}；"
                    "请用 `update_uploaded_skill_file` 修复 main.py 后再次 `run_skill_script`",
                )
            conclusion = str(payload.get("conclusion") or "")
            extra: dict[str, Any] = {
                "conclusion": conclusion,
                "entry": payload.get("entry"),
                "hint": payload.get("hint"),
            }
            skill_md = fetch_uploaded_skill_md(db, skill_name, user=user, max_chars=4000)
            if skill_md:
                extra["skill_md"] = skill_md
            if payload.get("screenshot_api_path") and loop_state is not None:
                record_stream_screenshot_attachment(
                    loop_state,
                    {
                        "screenshot_api_path": payload["screenshot_api_path"],
                        "title": "RPA 回放截图",
                    },
                )
                extra["screenshot_api_path"] = payload["screenshot_api_path"]
            if payload.get("status") == "instruction_only":
                return _tool_result(
                    True,
                    conclusion[:200] or "脚本执行完成",
                    extra,
                )
            if is_inconclusive_skill_conclusion(conclusion):
                append_skill_repair_context(
                    loop_state,
                    skill_name,
                    f"未产出有效结论：{conclusion[:240]}",
                )
                return _tool_result(
                    False,
                    f"Skill `{skill_name}` 未产出有效结论；"
                    "请用 `update_uploaded_skill_file` 修复 main.py / SKILL.md 后重试",
                    extra,
                )
            if loop_state is not None:
                loop_state.pop("pending_skill_repair", None)
                if conclusion.strip():
                    loop_state["last_skill_conclusion"] = conclusion.strip()
            return _tool_result(
                True,
                conclusion[:200] or "脚本执行完成",
                extra,
            )

        if tool_name == "create_skill":
            return await _execute_create_skill(
                db, user, params=params, user_message=user_message, loop_state=loop_state,
            )

        if tool_name == "update_uploaded_skill_file":
            from app.services import agent_skill_service as svc

            skill_name = str(params.get("skill_name") or "")
            file_path = str(params.get("file_path") or "")
            try:
                summary = svc.update_skill_file_by_name(
                    db,
                    user,
                    skill_name=skill_name,
                    file_path=file_path,
                    content=str(params.get("content") or ""),
                )
            except Exception as exc:
                from app.core.skill_dev_playbook import enrich_skill_repair_reason

                reason = enrich_skill_repair_reason(str(exc))
                return _tool_result(
                    False,
                    f"更新 `{skill_name}` / {file_path} 失败：{reason}",
                )
            return _tool_result(
                True,
                f"已更新 `{skill_name}` / {file_path}",
                {"skill_id": str(summary.id), "name": summary.name},
            )

        if tool_name == "delete_uploaded_skill":
            from app.services import agent_skill_service as svc

            svc.delete_skill_by_name(db, str(params.get("skill_name") or ""))
            return _tool_result(True, "已删除 Skill")

        return _tool_result(False, f"未知工具: {tool_name}")
    except Exception as exc:
        _logger.warning("agent tool %s failed: %s", tool_name, exc)
        return _tool_result(False, str(exc))


def _parse_tool_args(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def tool_workflow_meta(tool_name: str, raw_args: str | dict | None) -> dict[str, str]:
    """生成 workflow UI 展示用标题与 tool 键。"""
    params = _parse_tool_args(raw_args)
    name = (tool_name or "").strip()

    if name == ATOMIC_TOOL_WEB_SEARCH:
        query = str(params.get("query") or "").strip() or "?"
        return {
            "title": f"使用联网搜索查询「{query[:80]}」",
            "result_title": "联网搜索完成",
            "detail": query[:120],
            "tool": ATOMIC_TOOL_WEB_SEARCH,
        }
    if name == ATOMIC_TOOL_KNOWLEDGE_RETRIEVE:
        query = str(params.get("query") or "").strip() or "?"
        return {
            "title": f"使用知识库检索「{query[:80]}」",
            "result_title": "知识库检索完成",
            "detail": query[:120],
            "tool": ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
        }
    if name == ATOMIC_TOOL_KG_QUERY:
        question = str(params.get("question") or "").strip() or "?"
        return {
            "title": f"使用知识图谱查询「{question[:80]}」",
            "result_title": "图谱查询完成",
            "detail": question[:120],
            "tool": ATOMIC_TOOL_KG_QUERY,
        }
    if name == "search_tools":
        query = str(params.get("query") or "").strip() or "?"
        return {
            "title": f"搜索工具「{query[:80]}」",
            "result_title": "工具搜索完成",
            "detail": query[:120],
            "tool": "search_tools",
        }
    if name == "fetch_url_content":
        url = str(params.get("url") or "").strip() or "?"
        return {
            "title": f"获取网页内容：{url[:80]}",
            "result_title": "网页内容获取完成",
            "detail": url[:120],
            "tool": "fetch_url_content",
        }
    if name == "search_skills":
        query = str(params.get("query") or "").strip() or "?"
        return {
            "title": f"搜索 Skill「{query[:80]}」",
            "result_title": "Skill 搜索完成",
            "detail": query[:120],
            "tool": "skill.search",
        }
    if name == "invoke_skill":
        skill = str(params.get("skill_name") or "").strip() or "?"
        action = str(params.get("action") or "").strip() or "?"
        return {
            "title": f"使用 Skill「{skill}」{action}",
            "result_title": f"Skill 执行完成: {skill}",
            "failure_title": f"Skill 执行失败: {skill}",
            "detail": action,
            "tool": f"skill.invoke.{skill}",
        }
    if name == "run_tool_batch":
        steps = params.get("steps") or []
        count = len(steps) if isinstance(steps, list) else 0
        return {
            "title": f"批量执行 {count} 个步骤",
            "result_title": "批量执行完成",
            "failure_title": "批量执行失败",
            "detail": f"{count} 步",
            "tool": "run_tool_batch",
        }
    if name == "invoke_context_subagent":
        kind = str(params.get("kind") or "search").strip()
        task = str(params.get("task") or "").strip()
        task_short = task[:400]
        if kind == "search":
            return {
                "title": "正在多源检索…",
                "result_title": "检索完成",
                "failure_title": "检索失败",
                "detail": task_short or "并行检索多个关键词",
                "tool": "subagent.search",
            }
        return {
            "title": f"子智能体 · {kind}：{task_short}",
            "result_title": f"子智能体完成 · {kind}",
            "failure_title": f"子智能体失败 · {kind}",
            "detail": task_short or kind,
            "tool": f"subagent.{kind}",
        }
    if name == "request_orchestrator_assist":
        target = str(params.get("suggested_agent_id") or "").strip() or "调度"
        return {
            "title": f"请求调度协助 → {target}",
            "result_title": "已提交调度协助请求",
            "failure_title": "调度协助请求失败",
            "detail": str(params.get("reason") or "")[:120],
            "tool": "agent.orchestrator.assist",
        }
    if name == "ask_user_choice":
        question = str(params.get("question") or "").strip()[:100]
        return {
            "title": f"请用户选择：{question or '等待用户选择'}",
            "result_title": "用户已选择方案",
            "detail": question or "等待用户选择",
            "tool": "ask_user_choice",
        }
    if name == "list_agent_skills":
        query = str(params.get("query") or "").strip()
        return {
            "title": f"列出 Skills 目录（{query[:60] or '全部'}）",
            "result_title": "Skills 目录已列出",
            "detail": query[:80] or "全部",
            "tool": "skill.catalog",
        }
    if name == "load_uploaded_skill":
        skill = str(params.get("skill_name") or "").strip() or "?"
        return {
            "title": f"加载技能「{skill}」",
            "result_title": f"技能已加载: {skill}",
            "failure_title": f"技能加载失败: {skill}",
            "detail": skill,
            "tool": f"skill.{skill}",
        }
    if name == "run_skill_script":
        skill = str(params.get("skill_name") or "").strip() or "?"
        entry = str(params.get("entry") or "").strip() or "auto"
        return {
            "title": f"运行技能脚本「{skill}」",
            "result_title": f"脚本执行完成: {skill}",
            "failure_title": f"脚本执行失败: {skill}",
            "detail": entry,
            "tool": f"skill.run.{skill}",
        }
    if name == "create_skill":
        skill = str(params.get("name") or "").strip() or "?"
        return {
            "title": f"创建 Skill: {skill}",
            "result_title": f"Skill 已创建: {skill}",
            "detail": str(params.get("description") or "")[:120],
            "tool": "skill.create",
        }
    if name == "update_uploaded_skill_file":
        skill = str(params.get("skill_name") or "").strip() or "?"
        path = str(params.get("file_path") or "").strip() or "SKILL.md"
        return {
            "title": f"更新 Skill 文件: {skill}/{path}",
            "result_title": f"已更新: {skill}/{path}",
            "detail": path,
            "tool": "skill.update",
        }
    if name == "delete_uploaded_skill":
        skill = str(params.get("skill_name") or "").strip() or "?"
        return {
            "title": f"删除 Skill: {skill}",
            "result_title": f"Skill 已删除: {skill}",
            "detail": skill,
            "tool": "skill.delete",
        }
    if name == "read_agent_memory":
        return {
            "title": "读取 Agent 记忆",
            "result_title": "记忆已读取",
            "detail": "",
            "tool": "agent.memory",
        }
    if name == "append_agent_memory":
        note = str(params.get("note") or "").strip()[:80]
        return {
            "title": "写入 Agent 记忆",
            "result_title": "记忆已写入",
            "detail": note,
            "tool": "agent.memory",
        }
    if name == "search_documents_by_name":
        kw = str(params.get("name") or "").strip()[:80]
        scope = str(params.get("scope") or "").strip()[:40]
        detail = " / ".join(x for x in (kw, scope) if x)
        return {
            "title": f"搜索文档: {kw}" if kw else "搜索文档",
            "result_title": "文档搜索结果",
            "detail": detail,
            "tool": "document.search",
        }
    if name == "read_document_content":
        doc_id = str(params.get("document_id") or "").strip()[:36]
        doc_name = str(params.get("document_name") or "").strip()[:80]
        detail = doc_name or doc_id or "?"
        return {
            "title": f"读取文档正文: {detail}",
            "result_title": "文档正文已读取",
            "detail": detail,
            "tool": "document.read",
        }
    if name == "list_library_documents":
        folder = str(params.get("folder_name") or params.get("folder_id") or "").strip()[:80]
        kw = str(params.get("keyword") or "").strip()[:80]
        detail = " / ".join(x for x in (folder, kw) if x)
        return {
            "title": "列出文档库文档",
            "result_title": "文档列表已获取",
            "detail": detail,
            "tool": "document.list",
        }
    if name == "list_manageable_documents":
        kw = str(params.get("keyword") or "").strip()[:80]
        return {
            "title": "列出可管理文档",
            "result_title": "文档列表已获取",
            "detail": kw,
            "tool": "document.list",
        }
    if name == "list_document_folders":
        scope = str(params.get("scope") or "").strip()
        return {
            "title": f"列出文件夹: {scope}",
            "result_title": "文件夹列表已获取",
            "detail": scope,
            "tool": "document.folders",
        }
    if name == "create_kb_folder":
        folder_name = str(params.get("name") or "").strip()[:80]
        scope = str(params.get("scope") or "").strip()
        return {
            "title": "新建文件夹",
            "result_title": "文件夹已创建",
            "detail": f"{scope}/{folder_name}".strip("/"),
            "tool": "document.folder_create",
        }
    if name == "create_library_document":
        title = str(params.get("title") or "").strip()[:80]
        folder = str(params.get("folder_name") or params.get("folder_id") or "未分类")[:80]
        return {
            "title": "写入文档库",
            "result_title": "文档已写入",
            "detail": f"{title} → {folder}",
            "tool": "document.create",
        }
    if name == "rename_document":
        title = str(params.get("new_title") or "").strip()[:80]
        return {
            "title": "重命名文档",
            "result_title": "文档已重命名",
            "detail": title,
            "tool": "document.rename",
        }
    if name == "move_document":
        folder = str(params.get("folder_name") or params.get("folder_id") or "未分类")[:80]
        return {
            "title": "移动文档",
            "result_title": "文档已移动",
            "detail": folder,
            "tool": "document.move",
        }
    if name == "share_document":
        names = params.get("user_names") or []
        detail = "、".join(str(x) for x in names[:3])[:80]
        return {
            "title": "分享文档",
            "result_title": "文档已分享",
            "detail": detail,
            "tool": "document.share",
        }
    if name == "delete_document":
        return {
            "title": "删除文档",
            "result_title": "文档已删除",
            "detail": str(params.get("document_id") or "")[:36],
            "tool": "document.delete",
        }
    if name == "list_todos":
        status = str(params.get("status") or "全部")
        return {
            "title": "列出待办",
            "result_title": "待办列表已获取",
            "detail": status,
            "tool": "platform.todos",
        }
    if name == "create_todo":
        title = str(params.get("title") or "").strip()[:80]
        return {
            "title": "添加待办",
            "result_title": "待办已添加",
            "detail": title,
            "tool": "platform.todos",
        }
    if name == "update_todo":
        title = str(params.get("title") or params.get("status") or "").strip()[:80]
        return {
            "title": "更新待办",
            "result_title": "待办已更新",
            "detail": title,
            "tool": "platform.todos",
        }
    if name == "delete_todo":
        return {
            "title": "删除待办",
            "result_title": "待办已删除",
            "detail": str(params.get("todo_id") or "")[:36],
            "tool": "platform.todos",
        }
    if name == "send_notification":
        title = str(params.get("title") or "").strip()[:80]
        return {
            "title": "发送系统通知",
            "result_title": "通知已发送",
            "detail": title,
            "tool": "platform.notification",
        }
    if name == "schedule_notification":
        from app.services.notification_service import preview_scheduled_display

        title = str(params.get("title") or "").strip()[:80]
        when, boost_seconds = preview_scheduled_display(
            scheduled_at=str(params.get("scheduled_at") or ""),
        )
        detail = f"{title} · {when}" if when else title
        meta = {
            "title": "设置定时通知",
            "result_title": "定时通知已设置",
            "detail": detail[:80],
            "tool": "platform.notification",
        }
        if boost_seconds is not None:
            meta["boost_seconds"] = str(boost_seconds)
        return meta
    if name == "list_scheduled_notifications":
        return {
            "title": "列出定时通知",
            "result_title": "定时通知列表已获取",
            "detail": "",
            "tool": "platform.notification",
        }
    if name == "cancel_scheduled_notification":
        return {
            "title": "取消定时通知",
            "result_title": "定时通知已取消",
            "detail": str(params.get("notification_id") or "")[:36],
            "tool": "platform.notification",
        }
    _browser_meta = {
        "browser_navigate": ("打开网页", "browser.navigate"),
        "browser_snapshot": ("读取页面结构", "browser.snapshot"),
        "browser_click": ("点击元素", "browser.click"),
        "browser_type": ("输入文本", "browser.type"),
        "browser_fill": ("批量填表", "browser.fill"),
        "browser_screenshot": ("页面截图", "browser.screenshot"),
        "browser_save_workflow": ("保存 RPA 流程", "browser.save_workflow"),
        "browser_close_session": ("关闭浏览器", "browser.close"),
        "browser_replay_workflow": ("回放 RPA 流程", "browser.replay"),
        "browser_run_task": ("自动探索网页", "browser.auto_task"),
        "schedule_browser_workflow": ("定时 RPA 任务", "browser.schedule"),
    }
    if name in _browser_meta:
        title, tool_key = _browser_meta[name]
        detail = ""
        if name == "browser_navigate":
            detail = str(params.get("url") or "")[:120]
        elif name in {"browser_click", "browser_type"}:
            detail = str(params.get("ref") or "")[:20]
        elif name == "browser_save_workflow":
            detail = str(params.get("name") or "")[:80]
        return {
            "title": title,
            "result_title": f"{title}完成",
            "detail": detail,
            "tool": tool_key,
        }
    return {
        "title": name or "工具调用",
        "result_title": name or "工具返回",
        "detail": "",
        "tool": name or "agent.tool",
    }
