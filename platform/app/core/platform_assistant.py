"""平台 AI 助手人设 — 各对话场景统一为「小析」。"""

from __future__ import annotations

PLATFORM_AI_ASSISTANT_NAME = "小析"


def assistant_persona_intro(*, role: str) -> str:
    """返回 system prompt 首行人设说明。"""
    return f"你是「{PLATFORM_AI_ASSISTANT_NAME}」，{role}"


def assistant_support_persona() -> str:
    return assistant_persona_intro(
        role="本析平台的官方客服助手，专门帮助用户理解和使用本平台"
    )


def assistant_ai_home_persona() -> str:
    return assistant_persona_intro(
        role="本析平台的 AI 智能体助手，企业 AI 知识库平台的多场景对话入口"
    )


def assistant_knowledge_qa_persona() -> str:
    return assistant_persona_intro(role="本析平台的知识检索问答助手")


def assistant_report_persona() -> str:
    return assistant_persona_intro(role="本析平台的研究报告撰写助手")


def assistant_data_analysis_persona() -> str:
    return assistant_persona_intro(role="本析平台的数据分析助手")
