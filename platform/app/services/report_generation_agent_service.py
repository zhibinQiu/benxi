"""报告生成功能页 — 输入校验等辅助（主流式编排见 report_generation_service）。"""

from __future__ import annotations

import json

from app.core.report_skill_catalog import report_writing_quality_instruction
from app.services.report_agent_skills import report_skill_label
from app.services.report_generation_service import (
    _INTENT_LABELS,
    iter_report_generation_stream,
)

REPORT_INPUT_HINT = "请输入您想要生成的报告…"


def build_report_context_instruction(
    *,
    message: str,
    intent: str,
    topic: str,
    doc_count: int,
    web_available: bool,
    skill_name: str,
) -> str:
    """保留供测试与文档引用；运行时材料收集不经过 Agent tool loop。"""
    parts = [
        "【报告功能页】撰写结构化长报告。",
        f"报告类型：{report_skill_label(skill_name)}（Skill `{skill_name}`）。",
        f"用户意图：{_INTENT_LABELS.get(intent, intent)}。",
    ]
    if topic:
        parts.append(f"报告主题：{topic}")
    if doc_count:
        parts.append(f"用户已选择 {doc_count} 份本地文档。")
    if web_available:
        parts.append("允许联网检索。")
    parts.append(report_writing_quality_instruction(skill_name))
    if intent == "format_adjust":
        parts.append(f"格式调整需求：{message[:400]}")
    return "\n".join(parts)


def _iter_report_input_hint_payloads() -> list[str]:
    return [
        json.dumps({"delta": REPORT_INPUT_HINT}, ensure_ascii=False),
        json.dumps({"done": True, "reply": REPORT_INPUT_HINT}, ensure_ascii=False),
    ]


__all__ = [
    "REPORT_INPUT_HINT",
    "build_report_context_instruction",
    "iter_report_generation_stream",
]
