"""AI 智能体执行规划 — 工具 loop 前的轻量规划阶段（方案 A）。

架构原则 — 子智能体执行隔离（代码强制，非提示词软约束）
────────────────────────────────────────────────────
父智能体（调度层/通用层）的职责是「找到应该用哪个技能 / 工具」，
但不得直接调用任何技能或工具。所有实际执行必须委托给子智能体：

  ✅ invoke_context_subagent(kind=search, task=用户查询)
  ✅ invoke_context_subagent(kind=auto, task=用户需求)
  ✅ invoke_context_subagent(kind=search, queries=[...])
  ✅ invoke_context_subagent(kind=use, task=技能任务)

已通过 build_agent_tool_specs 代码级拦截：
  - allowed_names=None（父智能体工具集构建）时，invoke_skill 自动从可见工具列表中移除。
  - 子智能体有自己的 allowed_names 限制集，invoke_skill 仍可在其中正常使用。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent_runtime import format_planning_datetime_block
from app.core.llm_parse import parse_llm_json
from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.agentkit.loop.plan import AgentExecutionPlan
from app.services.agent_intent import AgentToolPlan, plan_agent_tools
from app.services.agent_skill_router import (
    MERMAID_DIAGRAM_SKILL,
    is_diagram_generation_message,
    is_platform_system_data_message,
    is_skill_management_message,
    matches_browser_intent,
    matches_browser_site_search,
    matches_research_intent,
    matches_research_signal,
    message_has_page_intent,
    message_has_url,
    user_wants_browser_screenshot,
)
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
)
from app.skills.catalog import list_all_skill_definitions
from app.skills.types import SkillReadiness

_logger = logging.getLogger(__name__)

RETRIEVAL_ATOMIC_TOOLS = frozenset(
    {
        ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
        ATOMIC_TOOL_KG_QUERY,
    }
)
SKILL_LOAD_TOOL = "load_uploaded_skill"
SKILL_SCRIPT_TOOL = "run_skill_script"





SKILL_MGMT_INTENT = "创建或管理 Agent 发展技能"


def _execution_plan_intent_label(plan: AgentExecutionPlan) -> str:
    labels = {
        SKILL_MGMT_INTENT: "技能开发",
        "执行发展技能": "执行发展技能",
        "平台操作": "平台操作",
        "浏览器操作": "浏览器操作",
    }
    return labels.get(plan.intent or "", plan.intent or "")


def _execution_plan_step_summary(plan: AgentExecutionPlan) -> str:
    if plan.intent == SKILL_MGMT_INTENT:
        has_browser = any("browser" in str(s).lower() for s in plan.steps)
        if has_browser:
            return "调研页面 → 直接创建技能包 → 脚本验证"
        return "澄清需求 → 直接创建技能包 → 脚本验证"
    if plan.intent == "执行发展技能" and plan.uploaded_skill:
        return f"执行「{plan.uploaded_skill}」"
    if plan.steps:
        return " → ".join(plan.steps[:4])
    if plan.allowed_tools:
        return "、".join(plan.allowed_tools[:4])
    return ""


def execution_plan_summary_for_ui(plan: AgentExecutionPlan) -> str:
    parts: list[str] = []
    if plan.source == "cache":
        parts.append("命中问题缓存")
    if plan.intent:
        parts.append(_execution_plan_intent_label(plan))
    if plan.direct_answer:
        parts.append("直接回答")
    else:
        step_summary = _execution_plan_step_summary(plan)
        if step_summary:
            parts.append(step_summary)
    if plan.uploaded_skill and plan.intent != "执行发展技能":
        parts.append(f"匹配技能「{plan.uploaded_skill}」")
    if plan.reasoning and len(parts) < 2:
        parts.append(plan.reasoning[:120])
    return "；".join(parts)[:240] or "已规划"


def plan_blocks_all_retrieval(plan: AgentExecutionPlan) -> bool:
    return RETRIEVAL_ATOMIC_TOOLS.issubset(set(plan.blocked_tools))


def _make_plan(
    reasoning: str,
    intent: str = "",
    *,
    direct_answer: bool = False,
    allowed_tools: tuple[str, ...] = (),
    blocked_tools: tuple[str, ...] = (),
    uploaded_skill: str | None = None,
    steps: tuple[str, ...] = (),
    source: str = "rule",
) -> AgentExecutionPlan:
    """创建 AgentExecutionPlan 的便捷工厂函数，减少重复的构造参数。"""
    return AgentExecutionPlan(
        reasoning=reasoning,
        intent=intent,
        direct_answer=direct_answer,
        allowed_tools=allowed_tools,
        blocked_tools=blocked_tools,
        uploaded_skill=uploaded_skill,
        steps=steps,
        source=source,
    )


def _make_direct_answer_plan(
    reasoning: str,
    intent: str = "直接回答",
    *,
    steps: tuple[str, ...] = (),
    source: str = "rule",
) -> AgentExecutionPlan:
    """直接回答模式的工厂函数：禁止检索，不暴露原子工具。"""
    return _make_plan(
        reasoning=reasoning,
        intent=intent,
        direct_answer=True,
        blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
        steps=steps,
        source=source,
    )

_SPECIALIST_DOMAIN_AGENTS = frozenset(
    {
        "report",
        "skill-dev",
        "platform",
        "rpa",
    }
)


def _skill_management_plan_instruction() -> str:
    return (
        "Skill 管理：直接 invoke_skill(skill-development, call, operation=create_skill)"
        " 创建新包，然后 operation=run_skill_script 验证。"
        " 用 invoke_context_subagent(kind=auto, task=...) 自主完成，"
        " 需检索多关键词用 invoke_context_subagent(kind=search, queries=[...])。"
    )


def build_plan_context_instruction(
    plan: AgentExecutionPlan,
    *,
    uploaded_skill_has_script: bool | None = None,
) -> str:
    """注入 tool loop 的短计划。"""
    if plan.direct_answer:
        return ""
    parts: list[str] = []
    if plan.steps:
        parts.append("步骤：" + " → ".join(plan.steps[:5]))
    elif plan.intent:
        parts.append(plan.intent)
    if plan.intent == SKILL_MGMT_INTENT:
        parts.append(_skill_management_plan_instruction())
    if plan.uploaded_skill:
        if uploaded_skill_has_script is True:
            parts.append(f"执行技能：{plan.uploaded_skill}")
        elif uploaded_skill_has_script is False:
            parts.append(f"技能：{plan.uploaded_skill}")
    if not parts:
        return ""
    return "【计划】" + "；".join(parts)


def filter_tool_specs_by_plan(
    specs: list[dict[str, Any]],
    plan: AgentExecutionPlan,
) -> list[dict[str, Any]]:
    """按规划裁剪可用 tools；检索类原子工具与发展技能 load 分别控制。"""
    skip = set(plan.blocked_tools)
    allow_retrieval = set(plan.allowed_tools) if plan.allowed_tools else None

    filtered: list[dict[str, Any]] = []
    for spec in specs:
        fn = spec.get("function") or {}
        name = str(fn.get("name") or "")
        if not name:
            continue
        if name in ("search_tools", "run_tool_batch"):
            filtered.append(spec)
            continue
        if name in skip:
            continue
        if name in RETRIEVAL_ATOMIC_TOOLS:
            if allow_retrieval is not None and name not in allow_retrieval:
                continue
            if allow_retrieval is None and plan_blocks_all_retrieval(plan):
                continue
        if name == SKILL_LOAD_TOOL:
            continue
        if name in ("list_agent_skills", SKILL_LOAD_TOOL):
            continue
        if name == "create_skill" and plan.intent != SKILL_MGMT_INTENT:
            continue
        needs_script = bool(plan.uploaded_skill) or plan.intent == SKILL_MGMT_INTENT
        if name == SKILL_SCRIPT_TOOL and not needs_script:
            continue
        filtered.append(spec)
    return filtered


def _rule_plan_for_skill_management(message: str) -> AgentExecutionPlan | None:
    """创建/更新/删除发展技能必须走 tool loop，禁止 direct_answer。"""
    if not is_skill_management_message(message):
        return None
    msg = (message or "").strip()
    needs_browser = bool(message_has_url(msg) or message_has_page_intent(msg))
    if needs_browser:
        steps = (
            "invoke_context_subagent(kind=auto, task=用户需求) 调研页面结构",
            "澄清目标字段与验收标准",
            "invoke_skill(skill-development, call, operation=create_skill)",
            "invoke_skill(skill-development, call, operation=run_skill_script) 验证新包",
            "向用户说明结果与用法",
        )
    else:
        steps = (
            "澄清需求、输入输出与验收标准",
            "必要时 invoke_context_subagent(kind=search, queries=[...])",
            "invoke_skill(skill-development, call, operation=create_skill)",
            "invoke_skill(skill-development, call, operation=run_skill_script) 验证新包",
            "向用户说明结果与用法",
        )
    blocked_extra: tuple[str, ...] = ()
    if not user_wants_browser_screenshot(msg):
        blocked_extra = ("browser_screenshot",)
    return _make_plan(
        reasoning=(
            "发展技能：经 invoke_skill(skill-development, call, ...) 创建与验证，"
            "勿查目录或 load/run 已有包；须先调研再动手"
        ),
        intent=SKILL_MGMT_INTENT,
        blocked_tools=blocked_extra,
        steps=steps,
    )


def _infer_uploaded_skill_followup(
    message: str,
    history: list[AiChatMessage] | None,
    uploaded_names: set[str],
) -> str | None:
    """短跟贴：上文出现 skill slug 时继承执行。"""
    from app.core.conversation_turn_context import is_likely_follow_up
    from app.services.agent_intent import is_chitchat_message

    msg = (message or "").strip()
    if not msg or len(msg) > 24 or is_skill_management_message(msg):
        return None
    if is_chitchat_message(msg, history):
        return None
    if not is_likely_follow_up(msg, history):
        return None
    if not uploaded_names:
        return None
    recent = _history_snippet(history, limit=6)
    if not recent:
        return None
    recent_fold = recent.casefold()
    for name in sorted(uploaded_names, key=len, reverse=True):
        if name.casefold() in recent_fold:
            return name
    return None


def _rule_plan_for_uploaded_skill_followup(
    db: Session,
    user: User,
    message: str,
    history: list[AiChatMessage] | None,
    uploaded_names: set[str],
) -> AgentExecutionPlan | None:
    skill = match_uploaded_skill_for_message(
        message,
        history,
        uploaded_names=uploaded_names,
        exclude_research_context=True,
    )
    if not skill:
        return None
    from app.services.agent_skill_service import uploaded_skill_has_script

    try:
        has_script = uploaded_skill_has_script(db, skill)
    except Exception:
        has_script = False
    if has_script:
        steps = (f"run_skill_script({skill}) 获取结果",)
        reasoning = f"已有发展技能 `{skill}`（脚本型），run_skill_script 执行"
    else:
        steps = ("按 SKILL.md 指引直接回复，勿 run_skill_script",)
        reasoning = f"已有发展技能 `{skill}`（指令型），按 SKILL.md 答复"
    return _make_plan(
        reasoning=reasoning,
        intent="执行发展技能",
        blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
        uploaded_skill=skill,
        steps=steps,
    )


def match_uploaded_skill_for_message(
    message: str,
    history: list[AiChatMessage] | None,
    *,
    uploaded_names: set[str],
    exclude_research_context: bool = True,
) -> str | None:
    """规则匹配已有发展技能 slug；复杂流程优先于原子工具。"""
    from app.services.agent_intent import is_chitchat_message

    msg = (message or "").strip()
    if not msg or is_skill_management_message(msg) or not uploaded_names:
        return None
    if is_chitchat_message(msg, history):
        return None

    skill = _infer_uploaded_skill_followup(msg, history, uploaded_names)
    if skill:
        return skill

    if exclude_research_context and matches_research_signal(msg):
        return None

    msg_fold = msg.casefold()
    for name in sorted(uploaded_names, key=len, reverse=True):
        if name.casefold() in msg_fold:
            return name

    return None


def _rule_plan_for_platform_system_data(
    db: Session,
    user: User,
    message: str,
) -> AgentExecutionPlan | None:
    """平台用户/部门等系统数据：必须调 list_users / list_departments 或 kg_query。"""
    from app.services.agent_skill_router import is_org_member_list_question

    if not is_platform_system_data_message(message):
        return None
    if is_org_member_list_question(message):
        return _make_plan(
            reasoning="部门成员须来自知识图谱 employs 关系，禁止臆造姓名",
            intent="查询部门成员",
            allowed_tools=(ATOMIC_TOOL_KG_QUERY,),
            blocked_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,),
            steps=(
                "kg_query 从知识图谱读取该部门 employs 关系",
                "仅根据工具返回数据作答，禁止编造姓名或邮箱",
            ),
        )
    from app.core.permissions import user_has_permission

    msg = (message or "").strip().casefold()
    dept_focus = any(k in msg for k in ("部门", "组织", "架构"))
    can_admin_user = user_has_permission(db, user, "admin.user")
    can_admin_dept = user_has_permission(db, user, "admin.dept")
    steps: list[str] = []
    if dept_focus and can_admin_dept:
        steps.append(
            "invoke_skill(dept-administration, call, {operation: list_departments})"
        )
    elif can_admin_user:
        steps.append(
            "invoke_skill(user-administration, call, {operation: list_users, params: {page_size: 100}})"
        )
    else:
        steps.append(
            "invoke_skill(kg, query_entities, {question: ...})"
        )
    steps.append("仅根据 Skill 返回数据作答，禁止编造姓名或邮箱")
    allowed_tools = (ATOMIC_TOOL_KG_QUERY,) if not can_admin_user else ()
    return _make_plan(
        reasoning="系统数据须经 user-administration / dept-administration / kg Skill，禁止臆造",
        intent="查询平台用户/组织数据",
        allowed_tools=allowed_tools,
        blocked_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,),
        steps=tuple(steps),
    )


def _rule_plan_for_web_research(
    message: str,
) -> AgentExecutionPlan | None:
    """无其他规则匹配的联网检索/查询意图 → invoke_context_subagent(kind=search)。"""
    msg = (message or "").strip()
    if not msg:
        return None
    if is_skill_management_message(msg):
        return None
    # 用户明确指定站点（如 "bing 搜索 X"）时走浏览器操作，非联网检索
    if matches_browser_site_search(msg):
        return None
    if not matches_research_intent(msg):
        return None
    return _make_plan(
        reasoning="用户需要查询实时信息或获取最新数据，需联网检索",
        intent="联网检索",
        blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
        steps=(
            "invoke_context_subagent(kind=search, task=用户查询)",
            "根据联网结果整理回答",
        ),
    )


def _rule_plan_for_browser_operation(message: str) -> AgentExecutionPlan | None:
    """浏览器操作意图（站点搜索/截图/页面访问）→ 委托 auto 子智能体。"""
    msg = (message or "").strip()
    if not msg:
        return None
    if not (
        matches_browser_site_search(msg)
        or user_wants_browser_screenshot(msg)
        or message_has_url(msg)
    ):
        return None
    return _make_plan(
        reasoning="用户需要进行浏览器操作，委托浏览器取证子智能体执行",
        intent="浏览器操作",
        blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
        steps=(
            "invoke_context_subagent(kind=auto, task=用户需求描述)",
            "根据子智能体返回结果整理回答",
        ),
    )




def _build_specialist_domain_plan(
    db: Session,
    user: User,
    *,
    agent_id: str,
    message: str,
    history: list[AiChatMessage] | None = None,
) -> AgentExecutionPlan | None:
    """专精 hop 内规划：根据专精 metadata 声明式构建执行计划。

    不硬编码每个专精的 tool/skill 列表，而是从 AGENT_DEFAULT_SKILLS
    提取默认 Skill，依 Skill 类型自动推断 plan。
    """
    from app.core.agent_profiles import get_agent_profile
    from app.core.tool_skill_taxonomy import AGENT_DEFAULT_SKILLS

    aid = (agent_id or "").strip()
    profile = get_agent_profile(aid)
    if not profile:
        return None

    default_skills = AGENT_DEFAULT_SKILLS.get(aid, ())
    all_names = _all_available_skill_names(db, user)

    # skill-dev 是特例：管理 Skill 包，不 load 任何现有 Skill
    if aid == "skill-dev":
        plan = _rule_plan_for_skill_management(message)
        if plan is not None:
            return plan
        return _make_plan(
            reasoning="技能开发专精：生成请求直接 create_skill，勿复用已有 Skill",
            intent=SKILL_MGMT_INTENT,
            blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            steps=(
                "调研（invoke_context_subagent(kind=auto, task=...)；"
                "否则 invoke_context_subagent(kind=search, queries=[...])）",
                "create_skill 直接生成新包",
                "run_skill_script 验证",
            ),
            source="specialist",
        )

    # platform：系统数据类走 _rule_plan_for_platform_system_data
    if aid == "platform":
        plan = _rule_plan_for_platform_system_data(db, user, message)
        if plan is not None:
            return plan
        return _make_plan(
            reasoning="平台操作专精：调用文档/待办/系统数据工具",
            intent="平台操作",
            blocked_tools=(),
            steps=("按诉求调用平台域原子工具（文档/待办/用户部门）",),
            source="specialist",
        )

    # 其他领域专精（rpa 等）：使用默认 Skill，不 load 任何 SKILL.md
    # 这些专精的 domain Skill（browser-automation/platform-ops）是纯编排型，
    # 无需 load_uploaded_skill，LLM 通过 invoke_skill 直接调用
    domain_intents = {
        "rpa": ("浏览器 RPA 专精", "浏览器操作",
                ("browser_navigate → browser_snapshot → 交互",)),
    }
    entry = domain_intents.get(aid)
    if entry is not None:
        return _make_plan(
            reasoning=entry[0],
            intent=entry[1],
            blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            steps=entry[2],
            source="specialist",
        )

    return None


# 兼容旧导出名
_rule_plan_for_specialist_domain = _build_specialist_domain_plan


def _coerce_skill_first_plan(
    message: str,
    plan: AgentExecutionPlan,
    *,
    history: list[AiChatMessage] | None = None,
    uploaded_names: set[str] | None = None,
) -> AgentExecutionPlan:
    """非 Skill 管理：先匹配已有发展技能，无匹配再保留原子工具路径。"""
    msg = (message or "").strip()
    if plan.intent == SKILL_MGMT_INTENT or is_skill_management_message(msg):
        return plan

    uploaded = plan.uploaded_skill
    if not uploaded and uploaded_names:
        uploaded = match_uploaded_skill_for_message(
            msg,
            history,
            uploaded_names=uploaded_names,
            exclude_research_context=True,
        )

    if uploaded and uploaded.lower() not in msg.lower():
        keep = uploaded == MERMAID_DIAGRAM_SKILL and (
            is_diagram_generation_message(msg) or plan.source == "rule"
        )
        if not keep and uploaded_names and uploaded in uploaded_names:
            keep = bool(
                match_uploaded_skill_for_message(
                    msg,
                    history,
                    uploaded_names=uploaded_names,
                    exclude_research_context=True,
                )
                == uploaded
            )
        if not keep:
            uploaded = None

    allowed = list(plan.allowed_tools)
    blocked = list(plan.blocked_tools)
    if uploaded:
        if RETRIEVAL_ATOMIC_TOOLS.intersection(allowed):
            allowed = [t for t in allowed if t not in RETRIEVAL_ATOMIC_TOOLS]
        for tool in RETRIEVAL_ATOMIC_TOOLS:
            if tool not in blocked:
                blocked.append(tool)

    if uploaded == plan.uploaded_skill and tuple(allowed) == plan.allowed_tools and tuple(blocked) == plan.blocked_tools:
        return plan

    return _make_plan(
        reasoning=plan.reasoning,
        intent=plan.intent,
        direct_answer=plan.direct_answer,
        allowed_tools=tuple(allowed),
        blocked_tools=tuple(blocked),
        uploaded_skill=uploaded,
        steps=plan.steps,
        source=plan.source,
    )



def _coerce_skill_management_plan(
    message: str, plan: AgentExecutionPlan
) -> AgentExecutionPlan:
    """修正规划器/缓存将 Skill 管理误判为 direct_answer 的情况。"""
    if not plan.direct_answer or not is_skill_management_message(message):
        return plan
    fixed = _rule_plan_for_skill_management(message)
    if fixed is None:
        return plan
    return AgentExecutionPlan(
        reasoning=fixed.reasoning,
        intent=plan.intent or fixed.intent,
        direct_answer=False,
        allowed_tools=plan.allowed_tools,
        blocked_tools=fixed.blocked_tools or plan.blocked_tools,
        uploaded_skill=plan.uploaded_skill,
        steps=fixed.steps or plan.steps,
        source=plan.source,
    )


def _rule_plan_from_intent(intent_plan: AgentToolPlan) -> AgentExecutionPlan | None:
    if intent_plan.use_attachment:
        return _make_plan(
            reasoning="用户已提供临时附件，优先依据附件正文作答",
            intent=intent_plan.intent_label,
            blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            steps=("阅读附件上下文", "依据附件回答"),
        )
    return None


def _rule_plan_for_chitchat(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> AgentExecutionPlan | None:
    """寒暄 / 简单直答：跳过 LLM 规划，直接进入流式作答。"""
    from app.services.agent_intent import is_chitchat_message
    from app.services.agent_skill_router import is_trivial_direct_question

    text = (message or "").strip()
    if not text:
        return None
    if is_chitchat_message(text, history):
        return _make_direct_answer_plan(
            reasoning="日常寒暄或简短交流，无需检索与工具",
            intent="日常交流",
        )
    if is_trivial_direct_question(text):
        return _make_direct_answer_plan(
            reasoning="简单问题，模型可直接作答",
            intent="简要回答",
        )
    return None


def _normalize_tool_names(raw: Any, *, allowed: set[str]) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        name = str(item or "").strip()
        if name in allowed and name not in out:
            out.append(name)
    return tuple(out)


def _parse_llm_plan(
    data: dict[str, Any] | None,
    *,
    allowed_atomic: set[str],
    allowed_uploaded: set[str],
) -> AgentExecutionPlan | None:
    if not data:
        return None
    direct = bool(data.get("direct_answer"))
    reasoning = str(data.get("reasoning") or "").strip()
    intent = str(data.get("intent") or reasoning or "执行任务").strip()
    steps_raw = data.get("steps") or []
    steps = tuple(str(s).strip() for s in steps_raw if str(s).strip())[:6]

    allowed_names = _normalize_tool_names(
        data.get("allowed_tools") or data.get("need_tools"),
        allowed=allowed_atomic,
    )
    blocked_names = _normalize_tool_names(
        data.get("blocked_tools") or data.get("skip_atomic_tools"),
        allowed=allowed_atomic,
    )
    if allowed_names and blocked_names:
        blocked_set = set(blocked_names)
        allowed_names = tuple(t for t in allowed_names if t not in blocked_set)

    uploaded_raw = data.get("uploaded_skill")
    uploaded = str(uploaded_raw).strip() if uploaded_raw else ""
    uploaded_skill = uploaded if uploaded in allowed_uploaded else None
    if uploaded and not uploaded_skill:
        _logger.debug("规划中的 uploaded_skill 不在目录中: %s", uploaded)

    if direct:
        return _make_direct_answer_plan(
            reasoning=reasoning or "可直接回答",
            intent=intent,
            steps=steps,
            source="llm",
        )

    return _make_plan(
        reasoning=reasoning or intent,
        intent=intent,
        allowed_tools=tuple(allowed_names),
        blocked_tools=tuple(blocked_names),
        uploaded_skill=uploaded_skill,
        steps=steps,
        source="llm",
    )


def _fallback_plan(intent_label: str = "") -> AgentExecutionPlan:
    """无规则匹配时的安全兜底：直接回答，不暴露任何 Tool。

    direct_answer=True 确保 LLM 不会在无边界约束下调用跨域工具
    （如浏览器自动化等），从根本上避免了「画流程图 → 调用浏览器」类误判。
    """
    return _make_direct_answer_plan(
        reasoning=intent_label or "由智能体直接回答",
        intent=intent_label or "直接回答",
        source="fallback",
    )


def _all_available_skill_names(db: Session, user: User) -> set[str]:
    """返回所有可用的 Skill 名称（合并内置+上传+MCP，不区分类别）。

    这是查询可用 Skill 的唯一入口。调用方不应再分别查 builtin/uploaded，
    避免因 Source 分类遗漏技能导致路由跳过。
    """
    all_skills: set[str] = set()
    for skill in list_all_skill_definitions(db, user=user, admin_view=False, catalog_only=True):
        if skill.readiness in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION):
            continue
        all_skills.add(skill.name)
    return all_skills

# 兼容旧导入：部分外部代码仍用 `_skill_name_sets`（rst 中的 `_` 前缀表示私有）
_skill_name_sets = _all_available_skill_names  # type: ignore[assignment]


_KG_PLANNING_USER_LABEL = "【知识图谱关联（规划参考，非检索结果）】"


async def resolve_kg_planning_context(
    db: Session,
    user: User,
    question: str,
    history: list[AiChatMessage] | None = None,
) -> str:
    """规划前从问题匹配实体并扩展子图，供消歧与工具选型参考。"""
    from app.core.conversation_turn_context import effective_question_for_retrieval
    from app.core.permissions import user_has_permission

    if not user_has_permission(db, user, "feature.kg"):
        return ""
    text = effective_question_for_retrieval(question, history).strip()
    if not text:
        return ""
    try:
        from app.services.kg_service import retrieve_kg_context_for_question_async

        ctx = await retrieve_kg_context_for_question_async(db, user, text)
        if ctx and ctx.context_text:
            return ctx.context_text.strip()[:1800]
    except Exception as exc:
        _logger.warning("Agent 规划前知识图谱加载失败: %s", exc)
    return ""


def _planning_system_prompt(
    *,
    allowed_atomic: set[str],
    uploaded_names: set[str],
    include_kg_reference: bool = False,
) -> str:
    atomic_list = "、".join(sorted(allowed_atomic)) or "无"
    uploaded_list = "、".join(sorted(uploaded_names)) or "无"
    kg_block = ""
    if include_kg_reference:
        kg_block = "若有图谱上下文，先消歧再选工具。\n"
    return (
        "任务规划器。只输出 JSON。\n"
        + kg_block
        + f"原子工具示例：{atomic_list}。发展技能：{uploaded_list}。\n"
        '{"reasoning":"…","intent":"…","direct_answer":true|false,'
        '"allowed_tools":[],"blocked_tools":[],"uploaded_skill":null,'
        '"steps":[]}\n'
        "规则：闲聊/够答→direct_answer；"
        "够用即停。"
        "若存在近期对话，须结合上文理解当前短句/追问的真实意图，勿孤立看待本轮输入。"
        "但若当前句为完整独立问题或寒暄，以当前句为准，勿强行绑定上一轮话题或 Skill。"
    )


def _history_snippet(history: list[AiChatMessage] | None, *, limit: int = 8) -> str:
    from app.core.conversation_turn_context import format_conversation_snippet

    return format_conversation_snippet(history, limit=limit, per_message_chars=240)


async def resolve_execution_plan(
    db: Session,
    user: User,
    *,
    message: str,
    history: list[AiChatMessage] | None = None,
    intent_plan: AgentToolPlan | None = None,
    available_atomic_tools: set[str] | None = None,
    kg_planning_context: str | None = None,
    prior_outcomes: list[str] | None = None,
    prior_plan: AgentExecutionPlan | None = None,
    force_replan: bool = False,
    agent_id: str | None = None,
) -> AgentExecutionPlan:
    """规则 fast path → 可选 LLM 规划 → fallback。专精 hop 传入 agent_id 时仅域内规划。"""
    settings = get_settings()
    if intent_plan is None:
        attach_count = 0
        intent_plan = plan_agent_tools(
            message,
            attach_count=attach_count,
            history=history,
        )

    specialist_id = (agent_id or "").strip()
    if specialist_id in _SPECIALIST_DOMAIN_AGENTS and not force_replan:
        domain_plan = _rule_plan_for_specialist_domain(
            db,
            user,
            agent_id=specialist_id,
            message=message,
            history=history,
        )
        if domain_plan is not None:
            return domain_plan

    rule_plan = _rule_plan_from_intent(intent_plan)
    if rule_plan is not None:
        return rule_plan

    chitchat_plan = _rule_plan_for_chitchat(message, history)
    if chitchat_plan is not None and not force_replan:
        return chitchat_plan

    skill_mgmt_plan = _rule_plan_for_skill_management(message)
    if skill_mgmt_plan is not None and not force_replan:
        return skill_mgmt_plan

    all_skill_names = _all_available_skill_names(db, user)
    followup_plan = _rule_plan_for_uploaded_skill_followup(
        db, user, message, history, all_skill_names
    )
    if followup_plan is not None and not force_replan:
        return followup_plan

    platform_data_plan = _rule_plan_for_platform_system_data(db, user, message)
    if platform_data_plan is not None and not force_replan:
        return platform_data_plan

    browser_plan = _rule_plan_for_browser_operation(message)
    if browser_plan is not None and not force_replan:
        return browser_plan

    web_research_plan = _rule_plan_for_web_research(message)
    if web_research_plan is not None and not force_replan:
        return web_research_plan

    if not settings.agent_planning_enabled or not is_configured():
        return _coerce_skill_first_plan(
            message,
            _fallback_plan(intent_plan.intent_label),
            history=history,
            uploaded_names=all_skill_names,
        )

    allowed_atomic = set(available_atomic_tools or RETRIEVAL_ATOMIC_TOOLS)
    allowed_atomic &= RETRIEVAL_ATOMIC_TOOLS

    from app.services.agent_plan_cache_service import (
        PLAN_TYPE_AGENT_EXECUTION,
        agent_execution_scope_key,
        cache_hit_summary,
        execution_plan_from_payload,
        execution_plan_to_payload,
        lookup_cached_payload,
        store_cached_payload,
    )

    scope_key = agent_execution_scope_key(
        user.id,
        available_atomic_tools=allowed_atomic,
        uploaded_skills=all_skill_names,
    )
    cached = None
    if not force_replan:
        from app.core.conversation_turn_context import plan_cache_applicable

        if plan_cache_applicable(message, history):
            cached = lookup_cached_payload(
                scope_key,
                message,
                plan_type=PLAN_TYPE_AGENT_EXECUTION,
            )
    if cached:
        plan = execution_plan_from_payload(cached["payload"], source="cache")
        cached["lookup_question"] = message
        reasoning = cache_hit_summary(cached)
        if reasoning and reasoning not in plan.reasoning:
            plan = AgentExecutionPlan(
                reasoning=reasoning,
                intent=plan.intent,
                direct_answer=plan.direct_answer,
                allowed_tools=plan.allowed_tools,
                blocked_tools=plan.blocked_tools,
                uploaded_skill=plan.uploaded_skill,
                steps=plan.steps,
                source="cache",
            )
        return _coerce_skill_first_plan(
            message,
            _coerce_skill_management_plan(message, plan),
            history=history,
            uploaded_names=all_skill_names,
        )

    kg_text = (kg_planning_context or "").strip()
    if not kg_text:
        kg_text = resolve_kg_planning_context(db, user, message, history=history)

    system = _planning_system_prompt(
        allowed_atomic=allowed_atomic,
        uploaded_names=all_skill_names,
        include_kg_reference=bool(kg_text),
    )
    from app.core.conversation_turn_context import build_turn_planning_context

    user_parts = [
        format_planning_datetime_block(),
        build_turn_planning_context(message, history),
    ]
    if prior_plan is not None:
        user_parts.append(
            "上一轮规划："
            f"intent={prior_plan.intent}；"
            f"uploaded_skill={prior_plan.uploaded_skill or '无'}；"
            f"direct_answer={prior_plan.direct_answer}"
        )
    if prior_outcomes:
        lines = [str(x).strip() for x in prior_outcomes if str(x).strip()][-8:]
        if lines:
            user_parts.append(
                "上一轮执行结果（用户任务若未完成，须据此调整方案并继续，禁止重复无效路径）：\n"
                + "\n".join(f"- {line}" for line in lines)
            )
    if kg_text:
        user_parts.append(f"{_KG_PLANNING_USER_LABEL}\n{kg_text}")

    choice = await chat_completion_message_async(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        tools=None,
        temperature=0.1,
        timeout=35.0,
    )
    content = (((choice or {}).get("message") or {}).get("content") or "").strip()
    parsed = _parse_llm_plan(
        parse_llm_json(content),
        allowed_atomic=allowed_atomic,
        allowed_uploaded=all_skill_names,
    )
    if parsed:
        parsed = _coerce_skill_first_plan(
            message,
            _coerce_skill_management_plan(message, parsed),
            history=history,
            uploaded_names=all_skill_names,
        )
        from app.core.conversation_turn_context import plan_cache_applicable

        if plan_cache_applicable(message, history):
            store_cached_payload(
                scope_key,
                message,
                plan_type=PLAN_TYPE_AGENT_EXECUTION,
                intent=parsed.intent,
                payload=execution_plan_to_payload(parsed),
            )
        return parsed
    _logger.debug("Agent 规划 JSON 解析失败，回退按需执行")
    return _coerce_skill_first_plan(
        message,
        _fallback_plan(intent_plan.intent_label),
        history=history,
        uploaded_names=all_skill_names,
    )
