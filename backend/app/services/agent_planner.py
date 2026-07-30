"""AI 智能体执行规划 — 工具 loop 前的轻量规划阶段。

架构原则 — 父编排只委托、不直执（代码强制）
────────────────────────────────────────────────────
父智能体（调度层）只能调用编排入口（invoke_context_subagent 等），
所有实际执行必须委托给子智能体：

  ✅ invoke_context_subagent(kind=search, task=用户查询)
  ✅ invoke_context_subagent(kind=execute, steps=[...])
  ✅ invoke_context_subagent(kind=use, task=技能任务)

已通过 build_agent_tool_specs(for_llm=True) 代码级收口：
  - 父编排 LLM 可见集 = PARENT_ORCHESTRATION_TOOL_NAMES
  - 原子工具仅可被 describe 发现，或由子 Agent 执行
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent_runtime import format_planning_datetime_block
from app.core.llm_parse import parse_llm_json
from app.integrations.deepseek_client import chat_completion_message_async, is_configured
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.agent.loop.plan import AgentExecutionPlan
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
    ATOMIC_TOOL_WEB_SEARCH,
)
from app.skills.catalog import list_all_skill_definitions
from app.skills.types import SkillReadiness

_logger = logging.getLogger(__name__)

RETRIEVAL_ATOMIC_TOOLS = frozenset(
    {
        ATOMIC_TOOL_WEB_SEARCH,
        ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,
        ATOMIC_TOOL_KG_QUERY,
        "fetch_url_content",
        "ontology_query",
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
    intent_label = _execution_plan_intent_label(plan) if plan.intent else ""
    if intent_label:
        parts.append(intent_label)
    if plan.direct_answer:
        parts.append("直接回答")
    else:
        step_summary = _execution_plan_step_summary(plan)
        # 避免「处理用户请求：处理用户请求」这类重复拼接
        if step_summary and step_summary != intent_label:
            parts.append(step_summary)
    if plan.uploaded_skill and plan.intent != "执行发展技能":
        parts.append(f"匹配技能「{plan.uploaded_skill}」")
    if plan.reasoning and len(parts) < 2:
        reason = plan.reasoning[:120]
        if reason not in parts and reason != intent_label:
            parts.append(reason)
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
        "carbon",
    }
)


def _skill_management_plan_instruction() -> str:
    return (
        "Skill 管理：直接调用 create_skill 创建新包，然后 run_skill_script 验证。"
        " 用 invoke_context_subagent(kind=execute, task=...) 执行，"
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


def _rule_plan_for_knowledge_qa_hashtag(message: str) -> AgentExecutionPlan | None:
    """``#知识问答`` / 「请使用 知识问答 技能」硬触发：强制执行 knowledge-qa。"""
    from app.core.tool_skill_taxonomy import SKILL_KNOWLEDGE_QA
    from app.services.agent_skill_router import match_knowledge_qa_hashtag

    question = match_knowledge_qa_hashtag(message)
    if question is None:
        return None
    q = question or (message or "").strip()
    return _make_plan(
        reasoning="按用户指定执行知识问答（#知识问答 / 请使用知识问答技能）",
        intent="知识问答",
        uploaded_skill=SKILL_KNOWLEDGE_QA,
        blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
        steps=(
            f'直接 invoke_skill(knowledge-qa, ask, {{"question": {q!r}}})',
            "基于多源事实底稿综合作答",
        ),
    )


def _rule_plan_for_skill_management(message: str) -> AgentExecutionPlan | None:
    """创建/更新/删除发展技能必须走 tool loop，禁止 direct_answer。"""
    if not is_skill_management_message(message):
        return None
    msg = (message or "").strip()
    needs_browser = bool(message_has_url(msg) or message_has_page_intent(msg))
    if needs_browser:
        steps = (
            "invoke_context_subagent(kind=search, task=用户需求) 调研页面结构",
            "澄清目标字段与验收标准",
            "create_skill 直接创建技能包",
            "run_skill_script 验证新包",
            "向用户说明结果与用法",
        )
    else:
        steps = (
            "澄清需求、输入输出与验收标准",
            "必要时 invoke_context_subagent(kind=search, queries=[...])",
            "create_skill 直接创建技能包",
            "run_skill_script 验证新包",
            "向用户说明结果与用法",
        )
    blocked_extra: tuple[str, ...] = ()
    if not user_wants_browser_screenshot(msg):
        blocked_extra = ("browser_screenshot",)
    return _make_plan(
        reasoning=(
            "发展技能：直接调用 create_skill 等原子工具创建与验证，"
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
    # 父层只编排：把技能交给 use 子智能体执行（子层有完整工具集）
    if has_script:
        steps = (
            f"invoke_context_subagent(kind=use, task=使用技能 {skill} 完成用户请求；"
            f"需要时 run_skill_script({skill}))",
            "根据子智能体结论整理最终回答",
        )
        reasoning = f"已有发展技能 `{skill}`（脚本型），委托 use 子智能体执行"
    else:
        steps = (
            f"invoke_context_subagent(kind=use, task=按技能 {skill} 的 SKILL.md 完成用户请求)",
            "根据子智能体结论整理最终回答",
        )
        reasoning = f"已有发展技能 `{skill}`（指令型），委托 use 子智能体按 SKILL.md 执行"
    return _make_plan(
        reasoning=reasoning,
        intent="执行发展技能",
        # 父层禁止自行做检索原子工具；技能执行委托 use 子智能体
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

    # 显式点名技能（「请使用 xxx 技能」/消息中含 slug）优先，不受检索信号压制
    explicit = _match_explicit_uploaded_skill_name(msg, uploaded_names)
    if explicit:
        return explicit

    skill = _infer_uploaded_skill_followup(msg, history, uploaded_names)
    if skill:
        return skill

    if exclude_research_context and matches_research_signal(msg):
        return None

    return None


def _match_explicit_uploaded_skill_name(message: str, uploaded_names: set[str]) -> str | None:
    """用户消息中明确写出技能名时返回该技能。"""
    from app.services.agent_skill_router import MERMAID_DIAGRAM_SKILL
    from app.services.user_capability_directive import parse_user_capability_directive

    msg = (message or "").strip()
    if not msg or not uploaded_names:
        return None

    def _ok(name: str) -> str | None:
        if not name or name == MERMAID_DIAGRAM_SKILL:
            return None
        return name

    # 前端固定格式「请使用 X 技能：…」
    directive = parse_user_capability_directive(msg)
    if directive is not None and directive.kind == "skill":
        label = directive.raw_label.casefold()
        for name in uploaded_names:
            if name.casefold() == label:
                return _ok(name)
        for name in sorted(uploaded_names, key=len, reverse=True):
            n = name.casefold()
            if n and (n in label or label in n):
                hit = _ok(name)
                if hit:
                    return hit

    msg_fold = msg.casefold()
    # 「使用/调用 xxx 技能」优先（含中文名）
    m = re.search(
        r"(?:请使用|使用|调用|按|执行)\s*[「\"'`]?([^\s「」\"'`：:]{1,80})[」\"'`]?\s*技能",
        msg,
        re.I,
    )
    if m:
        named = m.group(1).casefold()
        for name in uploaded_names:
            if name.casefold() == named:
                return _ok(name)
    for name in sorted(uploaded_names, key=len, reverse=True):
        if name == MERMAID_DIAGRAM_SKILL:
            continue
        if name.casefold() in msg_fold:
            return name
    return None


def _rule_plan_for_platform_system_data(
    db: Session,
    user: User,
    message: str,
) -> AgentExecutionPlan | None:
    """平台用户/部门等组织数据：统一经知识图谱（必要时先 sync_platform_org）。"""
    from app.services.agent_skill_router import (
        is_org_member_list_question,
        is_person_org_affiliation_question,
    )

    # 人员归属 / 部门成员优先图谱（即使不算「平台系统数据」意图）
    if is_person_org_affiliation_question(message):
        return _make_plan(
            reasoning="人员组织归属须来自知识图谱 employs/member_of，禁止臆造或仅凭常识回答",
            intent="查询人员所属组织",
            allowed_tools=(ATOMIC_TOOL_KG_QUERY,),
            blocked_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE, ATOMIC_TOOL_WEB_SEARCH),
            steps=(
                "kg_query 查询该人员与组织的 employs/member_of 关系",
                "仅根据工具返回的所属组织作答，禁止编造公司名",
            ),
        )
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
    if not is_platform_system_data_message(message):
        return None
    return _make_plan(
        reasoning="平台用户/部门列表须经知识图谱（平台组织同步后的 ABox），禁止臆造",
        intent="查询平台用户/组织数据",
        allowed_tools=(ATOMIC_TOOL_KG_QUERY,),
        blocked_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE,),
        steps=(
            "kg_query 查询平台组织/用户相关实体与关系（图谱无数据时可先同步平台组织）",
            "仅根据图谱返回数据作答，禁止编造姓名或邮箱",
        ),
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
    """浏览器操作意图（站点搜索/截图/页面访问）→ 委托 execute 子智能体。"""
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
        reasoning="用户需要进行浏览器操作，委托 execute 子智能体调用浏览器工具",
        intent="浏览器操作",
        blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
        steps=(
            "invoke_context_subagent(kind=execute, task=用户浏览器需求；"
            "优先 browser_run_task 一次完成，或分步 browser_navigate/type/screenshot)",
            "根据子智能体返回结果与截图整理回答",
        ),
    )


def _rule_plan_for_diagram(
    db: Session,
    user: User,
    message: str,
) -> AgentExecutionPlan | None:
    """Mermaid 图表：直接作答输出围栏，不走工具/技能。"""
    _ = db
    _ = user
    msg = (message or "").strip()
    if not msg or not is_diagram_generation_message(msg):
        return None
    return _make_plan(
        reasoning="用户要求生成图表：在回复中直接输出 ```mermaid 围栏（无需工具）",
        intent="生成图表",
        direct_answer=True,
        uploaded_skill=None,
        allowed_tools=(),
        blocked_tools=tuple(RETRIEVAL_ATOMIC_TOOLS),
        steps=(
            "直接在回复中输出一个合法的 ```mermaid 代码块",
            "可附简短图意说明；禁止只描述不画",
        ),
        source="rule",
    )


def _rule_plan_for_report(
    db: Session,
    user: User,
    message: str,
) -> AgentExecutionPlan | None:
    """结构化长报告撰写 → 匹配报告类型 Skill。"""
    _ = db
    _ = user
    from app.services.report_agent_skills import (
        classify_report_skill,
        is_report_generation_message,
    )

    msg = (message or "").strip()
    if not msg or not is_report_generation_message(msg):
        return None
    skill = classify_report_skill(msg)
    return _make_plan(
        reasoning=f"用户要求撰写报告，使用报告类型 Skill「{skill}」",
        intent="撰写报告",
        direct_answer=False,
        uploaded_skill=skill,
        allowed_tools=(ATOMIC_TOOL_KNOWLEDGE_RETRIEVE, "web_search"),
        steps=(
            "检索知识库与联网材料",
            f"按 {skill} 技能结构撰写报告",
        ),
        source="rule",
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
    all_names = _plannable_skill_names(db, user, agent_id=aid)

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
                "调研（invoke_context_subagent(kind=execute, task=...)；"
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

    # carbon：政策/碳价走官方源原子工具；新闻才回交浏览器子智能体
    if aid == "carbon":
        from app.skills.builtin.handlers import _classify_carbon_question

        kind = _classify_carbon_question(message)
        if kind == "news":
            return _make_plan(
                reasoning="双碳新闻资讯：交浏览器子智能体查最新",
                intent="双碳新闻",
                steps=(
                    "invoke_context_subagent(kind=execute, task=查询最新双碳新闻资讯)",
                ),
                source="specialist",
            )
        if kind == "forecast":
            return _make_plan(
                reasoning="双碳时序预测：优先 time_series_forecast 模型推理",
                intent="双碳预测",
                steps=("time_series_forecast(method=按用户指定或rule, series=cea或ccer)",),
                source="specialist",
            )
        if kind == "price":
            return _make_plan(
                reasoning="双碳碳价：优先 carbon_price 官方源",
                intent="双碳碳价",
                steps=("carbon_price(keyword=用户问题)",),
                source="specialist",
            )
        if kind in ("emission", "ccer", "international", "local"):
            return _make_plan(
                reasoning=f"双碳结构化数据：carbon_data(topic={kind})",
                intent="双碳数据",
                steps=(f"carbon_data(topic={kind}, keyword=用户问题)",),
                source="specialist",
            )
        # policy / general → 政策官方源
        return _make_plan(
            reasoning="双碳政策/综合：优先 carbon_policy 官方源",
            intent="双碳政策",
            steps=("carbon_policy(keyword=用户问题)",),
            source="specialist",
        )

    pass  # 其他领域专精：使用默认 Skill，不 load 任何 SKILL.md

    return None


# 对外别名（历史 import 名）
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

    # 本轮已锁定 kg_query（图谱优先路径）：禁止被 Skill 语义匹配覆盖
    if (
        "kg_query" in (plan.allowed_tools or ())
        and "web_search" in (plan.blocked_tools or ())
        and not plan.uploaded_skill
    ):
        return plan

    uploaded = plan.uploaded_skill
    if not uploaded and uploaded_names:
        uploaded = match_uploaded_skill_for_message(
            msg,
            history,
            uploaded_names=uploaded_names,
            exclude_research_context=True,
        )

    # 旧版 mermaid-diagram 技能不再作为画图路径；画图由直接作答输出围栏完成
    if uploaded == MERMAID_DIAGRAM_SKILL:
        uploaded = None

    if uploaded and uploaded.lower() not in msg.lower():
        keep = False
        if uploaded_names and uploaded in uploaded_names:
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
    """无规则匹配时的安全兜底：让 LLM 自主使用 CORE_TOOL 完成任务。

    编排器默认只能看到 CORE_TOOL_NAMES（web_search / knowledge_retrieve /
    kg_query / invoke_context_subagent 等安全工具），浏览器工具默认不可见，
    因此不存在「画流程图 → 调用浏览器」类误判风险。direct_answer=True
    反而让 LLM 在需要实时数据时只能凭空回答，造成「只说不做」。
    """
    return _make_plan(
        reasoning=intent_label or "无规则匹配，由智能体自主选择工具或直接回答",
        intent=intent_label or "查询或执行",
        direct_answer=False,
        source="fallback",
    )


def _plannable_skill_names(
    db: Session,
    user: User,
    *,
    agent_id: str | None = None,
) -> set[str]:
    """规划可用 Skill 名称。

    = 该 Agent 已挂载 Skill
    ∪ 当前用户上传型 Skill（显式例外：便于「请使用 xxx-skill」编排 kind=use）

    不含未挂载的平台 builtin/MCP 全库（与 find_skills 可见范围对齐，上传例外除外）。
    """
    from app.skills.types import SkillSource

    names: set[str] = set()
    aid = (agent_id or "").strip() or "orchestrator"
    try:
        from app.services.agent_profile_service import resolve_agent_skill_names

        names.update(resolve_agent_skill_names(db, aid))
    except Exception:
        pass
    for skill in list_all_skill_definitions(db, user=user, admin_view=False, catalog_only=True):
        if skill.readiness in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION):
            continue
        if skill.source == SkillSource.UPLOADED:
            names.add(skill.name)
    return names


# 对外别名：可规划 Skill 名集合（非平台全库）
_all_available_skill_names = _plannable_skill_names  # type: ignore[assignment]
_skill_name_sets = _plannable_skill_names  # type: ignore[assignment]


_KG_PLANNING_USER_LABEL = "【语义层决策上下文（规划参考）】"
_KG_PROBE_TIMEOUT_SEC = 2.5
_KG_DECISION_CACHE_TTL = 45.0
# key → (monotonic_ts, planning_text, can_direct, direct_reply)
_KG_DECISION_CACHE: dict[str, tuple[float, str, bool, str]] = {}


def _kg_decision_cache_key(user_id: str, question: str) -> str:
    return f"{user_id}::{hash((question or '').strip())}"


def peek_cached_kg_planning_text(user_id: str, question: str) -> str:
    """读取本轮短时缓存的图谱规划文本（无 IO）。"""
    key = _kg_decision_cache_key(str(user_id), question)
    entry = _KG_DECISION_CACHE.get(key)
    if entry is None:
        return ""
    ts, text, _can, _reply = entry
    if time.monotonic() - ts > _KG_DECISION_CACHE_TTL:
        _KG_DECISION_CACHE.pop(key, None)
        return ""
    return text or ""


def peek_cached_kg_direct_reply(user_id: str, question: str) -> str:
    """读取本轮短时缓存的图谱直答正文（无 IO）。"""
    key = _kg_decision_cache_key(str(user_id), question)
    entry = _KG_DECISION_CACHE.get(key)
    if entry is None:
        return ""
    ts, _text, _can, reply = entry
    if time.monotonic() - ts > _KG_DECISION_CACHE_TTL:
        _KG_DECISION_CACHE.pop(key, None)
        return ""
    return (reply or "").strip()


def _store_kg_decision_cache(
    user_id: str,
    question: str,
    *,
    planning_text: str,
    can_direct: bool,
    direct_reply: str,
) -> None:
    if len(_KG_DECISION_CACHE) >= 256:
        _KG_DECISION_CACHE.clear()
    key = _kg_decision_cache_key(str(user_id), question)
    _KG_DECISION_CACHE[key] = (
        time.monotonic(),
        planning_text or "",
        bool(can_direct),
        (direct_reply or "").strip(),
    )


async def resolve_kg_decision_context(
    db: Session,
    user: User,
    question: str,
    history: list[AiChatMessage] | None = None,
    *,
    mode: str = "probe",
    timeout_sec: float | None = None,
):
    """规划前构建语义层决策上下文；无权限或失败时返回 None。

    调度默认路径：先快速关键词匹配 → 无命中则立刻结束 → 有命中再浅层推理。
    mode=probe：depth=1、无传递推理、短超时。
    mode=full：完整推理。
    """
    import asyncio

    from app.semantic import (
        OntologyHubService,
        can_answer_from_decision,
        try_direct_answer_from_decision,
    )
    from app.services.semantic_runtime import (
        get_kg_query_service,
        get_ontology_hub_service,
    )
    from app.semantic.models import AgentDecisionContext
    from app.core.conversation_turn_context import effective_question_for_retrieval
    from app.core.permissions import user_has_semantic_layer_permission
    from app.services.user_capability_directive import analysis_text_for_semantic

    if not user_has_semantic_layer_permission(db, user):
        return None
    # 固定前缀（请让/请使用…技能）只分析冒号后；无正文则跳过
    seed = analysis_text_for_semantic(question)
    if not seed:
        return None
    text = effective_question_for_retrieval(seed, history).strip()
    if not text:
        return None

    uid = str(user.id)
    # 同轮已探测过（含超时空结果哨兵）：不再打 Neo4j
    cache_key = _kg_decision_cache_key(uid, text)
    cached_entry = _KG_DECISION_CACHE.get(cache_key)
    if cached_entry is not None:
        if time.monotonic() - cached_entry[0] <= _KG_DECISION_CACHE_TTL:
            return None
        _KG_DECISION_CACHE.pop(cache_key, None)

    probe = (mode or "probe").strip().lower() != "full"
    # 通用真多跳：probe/full 均深度 3 并开启推理；超时由 _KG_PROBE_TIMEOUT_SEC 控制
    depth = 3
    include_inferred = True
    wait = (
        float(timeout_sec)
        if timeout_sec is not None
        else (_KG_PROBE_TIMEOUT_SEC if probe else 5.0)
    )

    async def _probe() -> AgentDecisionContext | None:
        kg = await get_kg_query_service()
        hub: OntologyHubService = await get_ontology_hub_service(kg=kg)
        decision = await hub.build_decision_context(
            text,
            uid,
            max_depth=depth,
            include_inferred=include_inferred,
            db=db,
        )
        if not isinstance(decision, AgentDecisionContext):
            return None
        # 无图谱/SQL 材料时不进入直答缓存
        if not decision.has_material and not decision.matched_entities:
            return None
        return decision

    try:
        from app.core.stream_cancel import await_unless_cancelled, raise_if_stream_cancelled

        raise_if_stream_cancelled()
        decision = await await_unless_cancelled(
            asyncio.wait_for(_probe(), timeout=max(0.3, wait)),
            poll_sec=0.15,
        )
        if decision is None:
            _store_kg_decision_cache(
                uid, text, planning_text="", can_direct=False, direct_reply=""
            )
            return None
        planning = decision.planning_text(max_chars=1800)
        direct = try_direct_answer_from_decision(decision, text) or ""
        _store_kg_decision_cache(
            uid,
            text,
            planning_text=planning,
            can_direct=can_answer_from_decision(decision),
            direct_reply=direct,
        )
        return decision
    except asyncio.TimeoutError:
        _logger.warning("Agent 规划前语义层探测超时 mode=%s wait=%.1fs", mode, wait)
        _store_kg_decision_cache(
            uid, text, planning_text="", can_direct=False, direct_reply=""
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _logger.warning("Agent 规划前语义层加载失败: %s", exc)
    return None


async def resolve_kg_planning_context(
    db: Session,
    user: User,
    question: str,
    history: list[AiChatMessage] | None = None,
    *,
    mode: str = "probe",
) -> str:
    """规划前构建语义层决策上下文文本，供消歧与工具选型参考。"""
    from app.core.conversation_turn_context import effective_question_for_retrieval

    text = effective_question_for_retrieval(question, history).strip()
    cached = peek_cached_kg_planning_text(str(user.id), text)
    if cached:
        return cached
    # 空缓存哨兵：已探测无结果
    key = _kg_decision_cache_key(str(user.id), text)
    if key in _KG_DECISION_CACHE:
        return ""
    decision = await resolve_kg_decision_context(
        db, user, question, history=history, mode=mode
    )
    if decision is None:
        return peek_cached_kg_planning_text(str(user.id), text)
    return decision.planning_text(max_chars=1800)


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
        "规则：仅闲聊/无需任何工具的常识问答→direct_answer=true；"
        "凡需检索、提醒/通知/待办、浏览器、写平台数据、执行 Skill→direct_answer=false 并选工具；"
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

    # 人员归属 / 部门成员：无论是否已有图谱上下文，一律 kg_query（禁止 list_users）
    if not force_replan:
        from app.semantic.ontology.intents import (
            INTENT_ORG_MEMBERS,
            INTENT_PERSON_AFFILIATION,
            detect_intent_tags,
        )

        tags = set(detect_intent_tags(message))
        kg_prefers = (
            "优先工具: kg_query" in (kg_planning_context or "")
            or "kg_query" in (kg_planning_context or "")
        )
        if kg_prefers or tags & {INTENT_PERSON_AFFILIATION, INTENT_ORG_MEMBERS}:
            platform_data_plan = _rule_plan_for_platform_system_data(db, user, message)
            if platform_data_plan is not None:
                return platform_data_plan

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

    # #知识问答 硬触发优先于闲聊/其它规则
    knowledge_qa_plan = _rule_plan_for_knowledge_qa_hashtag(message)
    if knowledge_qa_plan is not None and not force_replan:
        return knowledge_qa_plan

    chitchat_plan = _rule_plan_for_chitchat(message, history)
    if chitchat_plan is not None and not force_replan:
        return chitchat_plan

    skill_mgmt_plan = _rule_plan_for_skill_management(message)
    if skill_mgmt_plan is not None and not force_replan:
        return skill_mgmt_plan

    all_skill_names = _plannable_skill_names(db, user, agent_id=specialist_id or "orchestrator")
    followup_plan = _rule_plan_for_uploaded_skill_followup(
        db, user, message, history, all_skill_names
    )
    if followup_plan is not None and not force_replan:
        return followup_plan

    browser_plan = _rule_plan_for_browser_operation(message)
    if browser_plan is not None and not force_replan:
        return browser_plan

    diagram_plan = _rule_plan_for_diagram(db, user, message)
    if diagram_plan is not None and not force_replan:
        return diagram_plan

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
        kg_text = await resolve_kg_planning_context(db, user, message, history=history)

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
