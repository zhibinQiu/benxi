"""报告撰写智能体 — 报告类型识别与 Skill 映射。"""

from __future__ import annotations

import re

from app.core.report_skill_catalog import (
    REPORT_SKILL_CONSTRUCTION,
    REPORT_SKILL_FEASIBILITY,
    REPORT_SKILL_NAME_SET,
    REPORT_SKILL_REQUIREMENTS,
    REPORT_SKILL_SURVEY,
    REPORT_SKILL_TEST,
    REPORT_SKILL_WORK_PLAN,
)
from app.services.agent_skill_router import is_diagram_generation_message

_REPORT_INTENT_RE = re.compile(
    r"(?:写|撰写|生成|整理|输出|起草|编制|完成).{0,12}(?:一份|一篇|一个)?"
    r"(?:关于)?.{0,48}(?:可研|可行性研究|可行性分析|需求分析|建设方案|实施方案|"
    r"技术方案|调研|研究|测试|工作(?:计划|方案)|评估|论证)"
    r"(?:报告|方案|计划|说明书|文档)?"
    r"|(?:可研报告|可行性研究报告|需求分析报告|建设方案报告|调研报告|测试报告|"
    r"工作计划|研究报告|行业分析报告|政策分析报告|评估报告|实施方案)",
    re.I,
)

_REPORT_SKILL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"可研|可行性研究|可行性分析|可行性报告", re.I), REPORT_SKILL_FEASIBILITY),
    (re.compile(r"需求分析|需求调研|需求规格|需求说明|\bPRD\b", re.I), REPORT_SKILL_REQUIREMENTS),
    (
        re.compile(r"建设方案|实施方案|技术方案|建设设计|工程方案", re.I),
        REPORT_SKILL_CONSTRUCTION,
    ),
    (re.compile(r"测试报告|测试方案|验收测试|测试用例|测试总结", re.I), REPORT_SKILL_TEST),
    (re.compile(r"工作计划|工作方案|年度计划|行动方案|里程碑计划", re.I), REPORT_SKILL_WORK_PLAN),
    (
        re.compile(r"调研|市场分析|行业分析|研究报告|研究", re.I),
        REPORT_SKILL_SURVEY,
    ),
)


def is_report_generation_message(message: str) -> bool:
    """用户是否要撰写结构化长报告（非纯图表）。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if is_diagram_generation_message(msg) and not re.search(
        r"报告|方案|计划|可研|调研|需求分析|建设|测试|工作", msg, re.I
    ):
        return False
    return bool(_REPORT_INTENT_RE.search(msg))


def classify_report_skill(message: str) -> str:
    """按用户表述选择报告类型 Skill；默认调研/研究报告。"""
    msg = (message or "").strip()
    for pattern, skill_name in _REPORT_SKILL_PATTERNS:
        if pattern.search(msg):
            return skill_name
    return REPORT_SKILL_SURVEY


def pick_available_report_skill(message: str, available: set[str]) -> str | None:
    if not available:
        return None
    preferred = classify_report_skill(message)
    if preferred in available:
        return preferred
    if REPORT_SKILL_SURVEY in available:
        return REPORT_SKILL_SURVEY
    return sorted(available)[0]


def report_skill_label(skill_name: str) -> str:
    from app.core.report_skill_catalog import REPORT_SKILL_LABELS

    key = (skill_name or "").strip()
    return REPORT_SKILL_LABELS.get(key, key or "报告")


def resolve_report_skill_for_turn(
    message: str,
    history: list | None,
    available: set[str],
) -> str:
    """当前轮或首轮用户输入所对应的报告类型 Skill。"""
    msg = (message or "").strip()
    for pattern, skill_name in _REPORT_SKILL_PATTERNS:
        if pattern.search(msg) and skill_name in available:
            return skill_name
    if history:
        for item in history:
            role = getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else None)
            content = getattr(item, "content", None) if role else None
            if content is None and isinstance(item, dict):
                content = item.get("content")
            text = (content or "").strip()
            if role == "user" and text:
                for pattern, skill_name in _REPORT_SKILL_PATTERNS:
                    if pattern.search(text) and skill_name in available:
                        return skill_name
                break
    picked = pick_available_report_skill(message, available)
    return picked or REPORT_SKILL_SURVEY


def is_report_page_message_acceptable(message: str, *, has_history: bool) -> bool:
    """报告功能页：多轮修订允许短句；首轮须为撰写报告类需求。"""
    if has_history:
        return bool((message or "").strip())
    msg = (message or "").strip()
    if not msg:
        return False
    if is_report_generation_message(msg):
        return True
    for pattern, _ in _REPORT_SKILL_PATTERNS:
        if pattern.search(msg):
            return True
    if re.search(r"撰写.{0,24}报告|写.{0,12}报告|生成.{0,12}报告", msg, re.I):
        return True
    return False


def build_report_workflow_intent_title(
    *,
    skill_name: str,
    revision_intent: str,
    has_history: bool,
) -> str:
    """工作流展示：首轮仅报告类型；多轮附加修订意图。"""
    label = report_skill_label(skill_name)
    if not has_history or revision_intent == "initial":
        return label
    revision_labels = {
        "follow_up": "补充与修订",
        "format_adjust": "调整报告格式",
    }
    revision = revision_labels.get(revision_intent, revision_intent)
    return f"{label} · {revision}"


__all__ = [
    "REPORT_SKILL_NAME_SET",
    "build_report_workflow_intent_title",
    "classify_report_skill",
    "is_report_generation_message",
    "is_report_page_message_acceptable",
    "pick_available_report_skill",
    "report_skill_label",
    "resolve_report_skill_for_turn",
]
