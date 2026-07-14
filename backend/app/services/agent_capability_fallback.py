"""无匹配 Skill 时的调度兜底 — 需求拆解、能力说明、标准化回执。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.agent.types import FALLBACK_AGENT_ID, AgentRoutePlan
from app.core.llm_parse import parse_llm_json
from app.models.org import User
from app.services.agent_skill_match import (
    SkillMatchAssessment,
    assess_skill_match,
    list_platform_skill_summaries,
    supported_capability_labels,
)

_logger = logging.getLogger(__name__)

MISSING_CAPABILITY_CODE = 8001
CapabilityFallbackMode = Literal["loose", "strict"]


@dataclass(frozen=True, slots=True)
class DemandDecomposition:
    feasible_task: str
    unsupported_part: str
    missing_capability: tuple[str, ...]


def build_missing_capability_receipt(
    user_demand: str,
    *,
    missing_capability: tuple[str, ...],
    supported_capability: tuple[str, ...],
    match_kind: str = "none",
    max_similarity: float = 0.0,
) -> dict[str, Any]:
    return {
        "success": False,
        "code": MISSING_CAPABILITY_CODE,
        "msg": "当前平台无匹配能力完成该需求",
        "detail": {
            "user_demand": (user_demand or "").strip()[:1200],
            "match_kind": match_kind,
            "max_similarity": round(max_similarity, 4),
            "missing_capability": list(missing_capability),
            "supported_capability": list(supported_capability),
        },
    }


def build_capability_explainer_instruction(
    user_demand: str,
    *,
    decomposition: DemandDecomposition | None,
    supported_capability: tuple[str, ...],
    skill_summaries: list[tuple[str, str]],
) -> str:
    caps = "、".join(supported_capability[:16]) or "（暂无已启用 Skill）"
    catalog = "\n".join(f"- {text}" for _, text in skill_summaries[:20])
    parts = [
        "【调度兜底 · 能力说明模式】",
        "当前用户需求无法由现有 Skill 完整覆盖。请仅做文本说明，勿调用任何业务 Tool 或 invoke_skill。",
        f"【用户原始需求】{(user_demand or '').strip()[:800]}",
        f"【平台已支持能力概览】{caps}",
        "【Skill 目录摘要】",
        catalog or "（无）",
    ]
    if decomposition is not None:
        if decomposition.unsupported_part.strip():
            parts.append(f"【无法实现的部分】{decomposition.unsupported_part.strip()[:600]}")
        missing = "、".join(decomposition.missing_capability)
        if missing:
            parts.append(f"【缺失能力】{missing}")
        if decomposition.feasible_task.strip():
            parts.append(
                f"【平台可完成的简化子任务】{decomposition.feasible_task.strip()[:600]}"
            )
    parts.append(
        "请清晰说明：1) 用户诉求要点；2) 平台现有能力范围；3) 当前缺失哪些能力；"
        "4) 用户可如何调整或拆分诉求。语气简洁专业。"
    )
    return "\n".join(parts)


async def decompose_unsupported_demand(
    user_demand: str,
    skill_summaries: list[tuple[str, str]],
    *,
    assessment: SkillMatchAssessment,
) -> DemandDecomposition | None:
    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    if not is_configured():
        return None

    catalog = "\n".join(f"- `{sid}` {text}" for sid, text in skill_summaries[:24])
    system = (
        "你是平台调度层助手。用户诉求无法由现有 Skill 完整满足。"
        "请对比【平台能力清单】拆解需求，输出 JSON："
        '{"feasible_task":"平台现有技能可完成的简化子任务（无则空字符串）",'
        '"unsupported_part":"平台无法实现的需求描述",'
        '"missing_capability":["缺失能力名称",...]}'
        "规则：feasible_task 仅含现有 Skill 可覆盖部分；missing_capability 为简短能力名；"
        "勿编造平台不存在的 Skill；勿建议创建新 Skill。"
    )
    user_prompt = (
        f"【用户原始需求】{(user_demand or '').strip()[:900]}\n"
        f"【匹配情况】kind={assessment.kind} max_similarity={assessment.max_similarity:.3f}\n"
        f"【平台能力清单】\n{catalog}"
    )
    try:
        choice = await chat_completion_message_async(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.1,
        )
        content = (((choice or {}).get("message") or {}).get("content") or "").strip()
        data = parse_llm_json(content)
        if not isinstance(data, dict):
            return None
        missing_raw = data.get("missing_capability")
        missing: list[str] = []
        if isinstance(missing_raw, list):
            missing = [str(x).strip() for x in missing_raw if str(x).strip()]
        elif isinstance(missing_raw, str) and missing_raw.strip():
            missing = [missing_raw.strip()]
        if not missing and assessment.missing_skill_tags:
            missing = list(assessment.missing_skill_tags)
        return DemandDecomposition(
            feasible_task=str(data.get("feasible_task") or "").strip(),
            unsupported_part=str(data.get("unsupported_part") or "").strip(),
            missing_capability=tuple(dict.fromkeys(missing)),
        )
    except Exception:
        _logger.exception("调度需求拆解失败")
        return None


def _unsupported_footer(decomposition: DemandDecomposition | None) -> str:
    if decomposition is None or not decomposition.unsupported_part.strip():
        return ""
    return (
        f"\n\n---\n**暂不支持的部分**：{decomposition.unsupported_part.strip()[:400]}"
    )


async def resolve_capability_gap_route_plan(
    db: Session,
    user: User,
    message: str,
    assessment: SkillMatchAssessment,
    *,
    chat_history: list | None = None,
    pick_routes,
    pick_route,
    route_reasons: dict[str, str],
) -> tuple[AgentRoutePlan, str]:
    """返回 (AgentRoutePlan, effective_user_message)。"""
    settings = get_settings()
    mode: CapabilityFallbackMode = (
        "strict"
        if (settings.agent_capability_fallback_mode or "loose").strip().lower()
        == "strict"
        else "loose"
    )

    summaries = list_platform_skill_summaries(db, user)
    supported = supported_capability_labels(db, user)
    decomposition = await decompose_unsupported_demand(
        message, summaries, assessment=assessment
    )

    missing = (
        decomposition.missing_capability
        if decomposition is not None
        else assessment.missing_skill_tags
    )

    if mode == "loose" and decomposition is not None:
        feasible = decomposition.feasible_task.strip()
        if feasible:
            sub = assess_skill_match(db, user, feasible)
            if sub.kind == "full":
                routes = pick_routes(
                    db, user, feasible, chat_history=chat_history
                )
                if routes and not (
                    len(routes) == 1
                    and routes[0].agent_id == "orchestrator"
                    and routes[0].reason in ("调度默认", "无匹配Skill")
                ):
                    footer = _unsupported_footer(decomposition)
                    return (
                        AgentRoutePlan(
                            mode="single",
                            routes=tuple(routes),
                            source="capability_partial",
                            missing_skill_tags=missing,
                            feasible_goal=feasible,
                            unsupported_part=decomposition.unsupported_part,
                            capability_gap_instruction=(
                                f"执行可行子任务后，须在答复末尾说明以下能力暂不支持："
                                f"{decomposition.unsupported_part.strip()[:400]}"
                                if decomposition.unsupported_part.strip()
                                else ""
                            ),
                        ),
                        feasible,
                    )

    from app.services.agent_profile_service import is_agent_enabled
    from app.services.agent_skill_router import is_skill_management_message

    if is_agent_enabled(db, "skill-dev") and is_skill_management_message(message):
        reason = route_reasons.get("skill-dev", "Skill 创建/更新/执行")
        route = pick_route(db, "skill-dev", reason)
        return (
            AgentRoutePlan(
                mode="single",
                routes=(route,),
                source="capability_gap_skill_dev",
                missing_skill_tags=missing,
                feasible_goal=message,
                unsupported_part="",
                capability_gap_instruction=(
                    "当前平台没有匹配的 Skill 能完成用户需求。"
                    "请自动调用 skill-development 创建一个新 Skill（默认挂载到 skill-dev），"
                    "然后运行脚本验证，最后向用户说明结果。"
                ),
            ),
            message,
        )

    # 用户没有明确要求创建 Skill 时，不走 skill-dev 自动创建流程
    # 直接转向能力说明模式，避免简单问题被误路由到技能创建循环

    fallback_agent = FALLBACK_AGENT_ID

    receipt = build_missing_capability_receipt(
        message,
        missing_capability=missing,
        supported_capability=supported,
        match_kind=assessment.kind,
        max_similarity=assessment.max_similarity,
    )
    instruction = build_capability_explainer_instruction(
        message,
        decomposition=decomposition,
        supported_capability=supported,
        skill_summaries=summaries,
    )
    reason = route_reasons.get(fallback_agent, "平台能力说明")
    route = pick_route(db, fallback_agent, reason)
    return (
        AgentRoutePlan(
            mode="single",
            routes=(route,),
            source="capability_gap",
            missing_skill_tags=missing,
            feasible_goal=decomposition.feasible_task if decomposition else "",
            unsupported_part=decomposition.unsupported_part if decomposition else "",
            capability_gap_instruction=instruction,
            missing_capability_receipt=receipt,
        ),
        message,
    )
