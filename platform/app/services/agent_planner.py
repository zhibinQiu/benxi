"""AI 智能体执行规划 — 工具 loop 前的轻量规划阶段（方案 A）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.llm_parse import parse_llm_json
from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_intent import AgentToolPlan, plan_agent_tools
from app.services.agent_skill_router import (
    _PAGE_INTENT_RE,
    _URL_IN_MESSAGE_RE,
    is_skill_management_message,
    user_wants_browser_screenshot,
)
from app.services.skill_chat_service import (
    ATOMIC_TOOL_KG_QUERY,
    ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
    ATOMIC_TOOL_WEB_SEARCH,
)
from app.skills.catalog import list_all_skill_definitions
from app.skills.types import SkillReadiness, SkillSource

_logger = logging.getLogger(__name__)

RETRIEVAL_ATOMIC_TOOLS = frozenset(
    {
        ATOMIC_TOOL_WEB_SEARCH,
        ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
        ATOMIC_TOOL_KG_QUERY,
    }
)
SKILL_LOAD_TOOL = "load_uploaded_skill"
SKILL_SCRIPT_TOOL = "run_skill_script"


@dataclass(frozen=True)
class AgentExecutionPlan:
    """规划结果：区分原子工具调用与发展技能 load。"""

    reasoning: str
    intent: str
    direct_answer: bool
    atomic_tools: tuple[str, ...]
    skip_tools: tuple[str, ...]
    uploaded_skill: str | None
    builtin_orchestration: str | None
    steps: tuple[str, ...]
    source: str

    def summary_for_ui(self) -> str:
        parts: list[str] = []
        if self.source == "cache":
            parts.append("命中问题缓存")
        if self.intent:
            parts.append(self.intent)
        if self.direct_answer:
            parts.append("直接回答，不调用工具")
        elif self.steps:
            parts.append(" → ".join(self.steps[:4]))
        elif self.atomic_tools:
            parts.append("原子工具：" + "、".join(f"`{t}`" for t in self.atomic_tools))
        if self.uploaded_skill:
            parts.append(f"发展技能 load：`{self.uploaded_skill}`")
        elif self.builtin_orchestration:
            parts.append(f"内置编排 `{self.builtin_orchestration}`（勿 load）")
        if self.reasoning and len(parts) < 2:
            parts.append(self.reasoning[:120])
        return "；".join(parts)[:240] or "已规划"

    def blocks_all_retrieval(self) -> bool:
        return RETRIEVAL_ATOMIC_TOOLS.issubset(set(self.skip_tools))


SKILL_MGMT_INTENT = "创建或管理 Agent 发展技能"


def _skill_management_plan_instruction() -> str:
    return "Skill：先调研再 create；数据类须 main.py；失败用 update 修复，勿重复 create。"


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
        parts.append(f"技能：{plan.uploaded_skill}")
        if uploaded_skill_has_script is True:
            parts.append("用 run_skill_script，勿 load")
        elif uploaded_skill_has_script is False:
            parts.append("按 SKILL.md，勿 run_skill_script/load")
    if plan.builtin_orchestration:
        parts.append(f"内置：{plan.builtin_orchestration}（勿 load）")
    if plan.atomic_tools:
        parts.append("工具：" + "、".join(plan.atomic_tools))
    if plan.skip_tools:
        parts.append("勿调：" + "、".join(plan.skip_tools))
    if not parts:
        return ""
    return "【计划】" + "；".join(parts)


def filter_tool_specs_by_plan(
    specs: list[dict[str, Any]],
    plan: AgentExecutionPlan,
) -> list[dict[str, Any]]:
    """按规划裁剪可用 tools；检索类原子工具与发展技能 load 分别控制。"""
    skip = set(plan.skip_tools)
    allow_retrieval = set(plan.atomic_tools) if plan.atomic_tools else None

    filtered: list[dict[str, Any]] = []
    for spec in specs:
        fn = spec.get("function") or {}
        name = str(fn.get("name") or "")
        if not name or name in skip:
            continue
        if name in RETRIEVAL_ATOMIC_TOOLS:
            if allow_retrieval is not None and name not in allow_retrieval:
                continue
            if allow_retrieval is None and plan.blocks_all_retrieval():
                continue
        # load_uploaded_skill 由系统自动注入 SKILL.md，不向 Agent 暴露
        if name == SKILL_LOAD_TOOL:
            continue
        filtered.append(spec)
    return filtered


def _rule_plan_for_skill_management(message: str) -> AgentExecutionPlan | None:
    """创建/更新/删除发展技能必须走 tool loop，禁止 direct_answer。"""
    if not is_skill_management_message(message):
        return None
    msg = (message or "").strip()
    needs_browser = bool(_URL_IN_MESSAGE_RE.search(msg) or _PAGE_INTENT_RE.search(msg))
    if needs_browser:
        steps = (
            "澄清目标字段与验收标准",
            "browser_navigate → browser_snapshot 探查页面（勿截图）",
            "确认能定位到价格/数据后再编写 main.py 与 SKILL.md",
            "create_uploaded_skill（extra_files 含 main.py）",
            "向用户说明用法与局限",
        )
    else:
        steps = (
            "澄清需求、输入输出与验收标准",
            "必要时 web_search 或读文档验证可行性",
            "编写 main.py 与 SKILL.md",
            "create_uploaded_skill（含 extra_files 脚本）",
            "向用户说明用法",
        )
    skip_tools: tuple[str, ...] = ()
    if not user_wants_browser_screenshot(msg):
        skip_tools = ("browser_screenshot",)
    return AgentExecutionPlan(
        reasoning=(
            "发展技能须先调研验证、想清楚再 create_uploaded_skill，避免错误技能浪费用户时间；"
            "探页用 browser_snapshot，勿臆造页面结构"
        ),
        intent=SKILL_MGMT_INTENT,
        direct_answer=False,
        atomic_tools=(),
        skip_tools=skip_tools,
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=steps,
        source="rule",
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
        atomic_tools=plan.atomic_tools,
        skip_tools=fixed.skip_tools or plan.skip_tools,
        uploaded_skill=plan.uploaded_skill,
        builtin_orchestration=plan.builtin_orchestration,
        steps=fixed.steps or plan.steps,
        source=plan.source,
    )


def _rule_plan_from_intent(intent_plan: AgentToolPlan) -> AgentExecutionPlan | None:
    label = intent_plan.intent_label or ""
    if "定时提醒" in label:
        return AgentExecutionPlan(
            reasoning="用户请求定时提醒，必须调用 schedule_notification",
            intent=label,
            direct_answer=False,
            atomic_tools=(),
            skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            builtin_orchestration=None,
            steps=("调用 schedule_notification 设置提醒", "向用户确认已安排"),
            source="rule",
        )
    if "日常" in label or "平台使用" in label:
        return AgentExecutionPlan(
            reasoning=label,
            intent=label,
            direct_answer=True,
            atomic_tools=(),
            skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            builtin_orchestration=None,
            steps=(),
            source="rule",
        )
    if intent_plan.use_attachment:
        return AgentExecutionPlan(
            reasoning="用户已提供临时附件，优先依据附件正文作答",
            intent=intent_plan.intent_label,
            direct_answer=False,
            atomic_tools=(),
            skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            builtin_orchestration=None,
            steps=("阅读附件上下文", "依据附件回答"),
            source="rule",
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
    allowed_builtin: set[str],
) -> AgentExecutionPlan | None:
    if not data:
        return None
    direct = bool(data.get("direct_answer"))
    reasoning = str(data.get("reasoning") or "").strip()
    intent = str(data.get("intent") or reasoning or "执行任务").strip()
    steps_raw = data.get("steps") or []
    steps = tuple(str(s).strip() for s in steps_raw if str(s).strip())[:6]

    atomic = _normalize_tool_names(
        data.get("atomic_tools") or data.get("need_tools"),
        allowed=allowed_atomic,
    )
    skip = _normalize_tool_names(
        data.get("skip_tools") or data.get("skip_atomic_tools"),
        allowed=allowed_atomic,
    )
    if atomic and skip:
        skip_set = set(skip)
        atomic = tuple(t for t in atomic if t not in skip_set)

    uploaded_raw = data.get("uploaded_skill")
    uploaded = str(uploaded_raw).strip() if uploaded_raw else ""
    uploaded_skill = uploaded if uploaded in allowed_uploaded else None
    if uploaded and not uploaded_skill:
        _logger.debug("规划中的 uploaded_skill 不在目录中: %s", uploaded)

    builtin_raw = data.get("builtin_orchestration") or data.get("builtin_skill")
    builtin = str(builtin_raw).strip() if builtin_raw else ""
    builtin_orchestration = builtin if builtin in allowed_builtin else None

    if direct:
        return AgentExecutionPlan(
            reasoning=reasoning or "可直接回答",
            intent=intent,
            direct_answer=True,
            atomic_tools=(),
            skip_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
            uploaded_skill=None,
            builtin_orchestration=None,
            steps=steps,
            source="llm",
        )

    if uploaded_skill and builtin_orchestration:
        builtin_orchestration = None

    return AgentExecutionPlan(
        reasoning=reasoning or intent,
        intent=intent,
        direct_answer=False,
        atomic_tools=atomic,
        skip_tools=skip,
        uploaded_skill=uploaded_skill,
        builtin_orchestration=builtin_orchestration,
        steps=steps,
        source="llm",
    )


def _fallback_plan(intent_label: str = "") -> AgentExecutionPlan:
    return AgentExecutionPlan(
        reasoning=intent_label or "按需调用工具",
        intent=intent_label or "由智能体按需调用工具",
        direct_answer=False,
        atomic_tools=(),
        skip_tools=(),
        uploaded_skill=None,
        builtin_orchestration=None,
        steps=(),
        source="fallback",
    )


def _skill_name_sets(
    db: Session,
    user: User,
) -> tuple[set[str], set[str]]:
    skills = list_all_skill_definitions(db, user=user, admin_view=False, catalog_only=True)
    builtin: set[str] = set()
    uploaded: set[str] = set()
    for skill in skills:
        if skill.readiness in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION):
            continue
        if skill.source == SkillSource.BUILTIN:
            builtin.add(skill.name)
        elif skill.source == SkillSource.UPLOADED:
            uploaded.add(skill.name)
    return builtin, uploaded


_KG_PLANNING_USER_LABEL = "【本体图谱关联（规划参考，非检索结果）】"


def resolve_kg_planning_context(
    db: Session,
    user: User,
    question: str,
) -> str:
    """规划前从问题匹配实体并扩展子图，供消歧与工具选型参考。"""
    from app.core.permissions import user_has_permission

    if not user_has_permission(db, user, "feature.kg_palantir"):
        return ""
    text = (question or "").strip()
    if not text:
        return ""
    try:
        from app.services.kg_service import retrieve_kg_context_for_question

        ctx = retrieve_kg_context_for_question(db, user, text)
        if ctx and ctx.context_text:
            return ctx.context_text.strip()[:1800]
    except Exception as exc:
        _logger.warning("Agent 规划前本体图谱加载失败: %s", exc)
    return ""


def _planning_system_prompt(
    *,
    allowed_atomic: set[str],
    builtin_names: set[str],
    uploaded_names: set[str],
    include_kg_reference: bool = False,
) -> str:
    atomic_list = "、".join(sorted(allowed_atomic)) or "无"
    uploaded_list = "、".join(sorted(uploaded_names)) or "无"
    del builtin_names
    kg_block = ""
    if include_kg_reference:
        kg_block = "若有图谱上下文，先消歧再选工具。\n"
    return (
        "任务规划器。只输出 JSON。\n"
        + kg_block
        + f"原子工具示例：{atomic_list}。发展技能：{uploaded_list}。\n"
        '{"reasoning":"…","intent":"…","direct_answer":true|false,'
        '"atomic_tools":[],"skip_tools":[],"uploaded_skill":null,'
        '"builtin_orchestration":null,"steps":[]}\n'
        "规则：闲聊/够答→direct_answer；仅 steps 覆盖用户明确诉求，勿加额外任务；"
        "定时提醒→schedule_notification；查文档→knowledge_retrieve；"
        "够用即停。"
    )


def _history_snippet(history: list[AiChatMessage] | None, *, limit: int = 4) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for msg in history[-limit:]:
        role = "用户" if msg.role == "user" else "助手"
        text = (msg.content or "").strip()[:160]
        if text:
            lines.append(f"{role}：{text}")
    return "\n".join(lines)


async def resolve_execution_plan(
    db: Session,
    user: User,
    *,
    message: str,
    history: list[AiChatMessage] | None = None,
    intent_plan: AgentToolPlan | None = None,
    available_atomic_tools: set[str] | None = None,
    kg_planning_context: str | None = None,
) -> AgentExecutionPlan:
    """规则 fast path → 可选 LLM 规划 → fallback。"""
    settings = get_settings()
    if intent_plan is None:
        from app.core.permissions import user_has_permission
        from app.services.searxng_service import is_enabled as web_search_enabled

        attach_count = 0
        flags = {
            "kb_enabled": user_has_permission(db, user, "feature.knowledge_search"),
            "kg_enabled": user_has_permission(db, user, "feature.kg_palantir"),
            "web_enabled": web_search_enabled(db),
        }
        intent_plan = plan_agent_tools(
            message,
            attach_count=attach_count,
            history=history,
            **flags,
        )

    rule_plan = _rule_plan_from_intent(intent_plan)
    if rule_plan is not None:
        return rule_plan

    skill_mgmt_plan = _rule_plan_for_skill_management(message)
    if skill_mgmt_plan is not None:
        return skill_mgmt_plan

    if not settings.agent_planning_enabled or not is_configured():
        return _fallback_plan(intent_plan.intent_label)

    allowed_atomic = set(available_atomic_tools or RETRIEVAL_ATOMIC_TOOLS)
    allowed_atomic &= RETRIEVAL_ATOMIC_TOOLS
    builtin_names, uploaded_names = _skill_name_sets(db, user)

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
        builtin_skills=builtin_names,
        uploaded_skills=uploaded_names,
    )
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
                atomic_tools=plan.atomic_tools,
                skip_tools=plan.skip_tools,
                uploaded_skill=plan.uploaded_skill,
                builtin_orchestration=plan.builtin_orchestration,
                steps=plan.steps,
                source="cache",
            )
        return _coerce_skill_management_plan(message, plan)

    kg_text = (kg_planning_context or "").strip()
    if not kg_text:
        kg_text = resolve_kg_planning_context(db, user, message)

    system = _planning_system_prompt(
        allowed_atomic=allowed_atomic,
        builtin_names=builtin_names,
        uploaded_names=uploaded_names,
        include_kg_reference=bool(kg_text),
    )
    user_parts = [f"用户问题：{(message or '').strip()[:800]}"]
    hist = _history_snippet(history)
    if hist:
        user_parts.append(f"近期对话：\n{hist}")
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
        allowed_uploaded=uploaded_names,
        allowed_builtin=builtin_names,
    )
    if parsed:
        parsed = _coerce_skill_management_plan(message, parsed)
        store_cached_payload(
            scope_key,
            message,
            plan_type=PLAN_TYPE_AGENT_EXECUTION,
            intent=parsed.intent,
            payload=execution_plan_to_payload(parsed),
        )
        return parsed
    _logger.debug("Agent 规划 JSON 解析失败，回退按需执行")
    return _fallback_plan(intent_plan.intent_label)
