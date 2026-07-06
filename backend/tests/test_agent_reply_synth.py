"""agent_reply_synth 单元测试。"""

from __future__ import annotations

import asyncio
import json

from app.core.agent_message_parse import looks_like_internal_agent_content
from app.schemas.ai_chat import AiChatMessage
from app.services.agent_reply_synth import (
    _format_skill_conclusion,
    _resolve_tool_loop_reply_fast,
    build_deliverable_evidence_block,
    build_tool_outcome_summary,
    fallback_tool_loop_reply,
    is_internal_tool_outcome_line,
    reply_contradicts_tool_outcomes,
    reply_looks_like_denial,
    reply_looks_like_user_command_instruction,
    skill_creation_user_reply,
    skill_management_goal_satisfied,
    synthesize_tool_loop_user_reply,
)


def test_format_skill_conclusion_from_json():
    payload = {
        "数据名称": "全国碳市场行情",
        "数据来源": "https://www.tanshichang.cn",
        "最新记录": {"日期": "2026-06-23", "收盘": 82.41},
    }
    out = _format_skill_conclusion(json.dumps(payload, ensure_ascii=False))
    assert "82.41" in out
    assert "全国碳市场行情" in out


def test_build_tool_outcome_summary_prefers_skill_conclusion():
    loop_state = {
        "tool_outcome_lines": ["创建 Skill：完成"],
        "last_skill_conclusion": json.dumps(
            {"数据名称": "碳市场", "最新记录": {"收盘": 82.41}},
            ensure_ascii=False,
        ),
    }
    lines = build_tool_outcome_summary(loop_state)
    assert len(lines) == 1
    assert "82.41" in lines[0]


def test_fallback_without_outcomes():
    reply = fallback_tool_loop_reply("帮我查碳价", {})
    assert "没能完成" in reply


def test_fallback_with_tool_outcomes():
    reply = fallback_tool_loop_reply(
        "8s 后提醒我喝水",
        {"tool_outcome_lines": ["设置定时通知：已设置定时通知，将于 15:00:08 提醒：喝水"]},
    )
    assert "喝水" in reply
    assert "没能完成" not in reply


def test_reply_contradicts_tool_outcomes():
    loop_state = {
        "tool_outcome_lines": ["设置定时通知：已设置定时通知，将于 15:00:08 提醒：喝水"]
    }
    assert reply_contradicts_tool_outcomes("抱歉，我无法设置定时提醒", loop_state)
    assert not reply_contradicts_tool_outcomes("好的，已为您设置提醒", loop_state)


def test_synthesize_uses_tool_outcomes_without_llm():
    reply = asyncio.run(
        synthesize_tool_loop_user_reply(
            user_message="8s 后提醒我喝水",
            loop_state={
                "tool_outcome_lines": [
                    "设置定时通知：已设置定时通知，将于 2026-06-26 15:00:08 提醒：喝水"
                ]
            },
        )
    )
    assert "喝水" in reply
    assert reply_looks_like_denial(reply) is False


def test_synthesize_skill_creation_uses_natural_language_reply():
    msg = "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
    loop_state = {
        "created_uploaded_skills": ["carbon-market-price"],
        "invoked_uploaded_skills": ["carbon-market-price"],
        "last_skill_conclusion": (
            '{"数据名称":"全国碳市场","最新记录":{"收盘":83.12}}'
        ),
    }
    reply = asyncio.run(
        synthesize_tool_loop_user_reply(
            user_message=msg,
            loop_state=loop_state,
        )
    )
    assert "83.12" in reply
    assert "「「" not in reply
    assert "自然语言" not in reply
    assert "无需任何" not in reply
    assert "run_skill_script" not in reply


def test_synthesize_returns_plain_skill_conclusion():
    loop_state = {
        "last_skill_conclusion": "北京碳市场最新收盘价 72.50 元/吨（2026-06-26）",
        "tool_outcome_lines": ["执行含脚本的发展 Skill：完成"],
    }
    reply = asyncio.run(
        synthesize_tool_loop_user_reply(
            user_message="北京",
            loop_state=loop_state,
            chat_history=[
                AiChatMessage(
                    role="user",
                    content="生成 skill 爬取碳市场价格",
                ),
                AiChatMessage(
                    role="assistant",
                    content="已为您创建 carbon-market-price 技能。",
                ),
            ],
        )
    )
    assert "72.50" in reply
    assert "北京" in reply


def test_reply_contradicts_user_command_instruction():
    loop_state = {"tool_outcome_lines": ["创建 Skill：完成"]}
    assert reply_contradicts_tool_outcomes(
        "请 run_skill_script('carbon-market-price', args=['广东'])",
        loop_state,
    )
    assert reply_looks_like_user_command_instruction(
        "请使用示例命令 run_skill_script('x')"
    )


def test_skill_creation_user_reply():
    reply = skill_creation_user_reply({"created_uploaded_skills": ["carbon-market-price"]})
    assert reply
    assert "carbon-market-price" in reply
    assert "「「" not in reply
    assert "自然语言" not in reply
    assert "run_skill_script" not in reply


def test_synthesize_never_returns_internal_assistant_text():
    loop_state = {
        "last_skill_conclusion": json.dumps(
            {"数据名称": "碳市场", "最新记录": {"收盘": 82.41}},
            ensure_ascii=False,
        ),
    }

    reply = asyncio.run(
        synthesize_tool_loop_user_reply(
            user_message="查碳价",
            loop_state=loop_state,
        )
    )
    assert "DSML" not in reply
    assert "L246" not in reply
    assert "82.41" in reply
    assert not looks_like_internal_agent_content(reply)


def test_synthesize_expects_skill_data_without_result():
    reply = asyncio.run(
        synthesize_tool_loop_user_reply(
            user_message="北京",
            loop_state={"expects_skill_data": True},
        )
    )
    assert "run_skill_script" not in reply
    assert "未能自动获取" in reply


_SKILL_CREATE_MSG = (
    "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格。"
)


def test_internal_tool_outcome_line():
    assert is_internal_tool_outcome_line("Skills 目录：共 4 个技能")
    assert not is_internal_tool_outcome_line("创建 Skill: foo：已创建")


def test_skill_management_not_satisfied_after_list_only():
    loop_state = {"tool_outcome_lines": ["Skills 目录：共 4 个技能"]}
    assert skill_management_goal_satisfied(loop_state, _SKILL_CREATE_MSG) is False


def test_synthesize_skill_create_does_not_leak_catalog_line():
    reply = asyncio.run(
        synthesize_tool_loop_user_reply(
            user_message=_SKILL_CREATE_MSG,
            loop_state={"tool_outcome_lines": ["Skills 目录：共 4 个技能"]},
        )
    )
    assert "Skills 目录" not in reply
    assert "共 4 个技能" not in reply
    assert "抱歉" in reply


def test_build_tool_outcome_summary_filters_catalog():
    lines = build_tool_outcome_summary(
        {"tool_outcome_lines": ["Skills 目录：共 4 个技能"]}
    )
    assert lines == []


def test_orchestrator_assist_outcome_is_internal():
    assert is_internal_tool_outcome_line("请求调度协助 → research：已提交")


def test_build_deliverable_evidence_prioritizes_subagent():
    block = build_deliverable_evidence_block(
        {
            "subagent_summaries": [
                {"kind": "explore", "task": "调研", "summary": "应忽略的旧摘要"},
                {"kind": "browser_digest", "task": "页面", "summary": "最新子智能体：收盘 82.41"},
            ],
            "retrieval_context_parts": ["早期检索：不应出现在终稿证据"],
            "tool_outcome_lines": ["Skills 目录：共 4 个技能"],
        }
    )
    assert "最新子智能体：收盘 82.41" in block
    assert "早期检索" not in block
    assert "Skills 目录" not in block
    assert "应忽略的旧摘要" not in block


def test_skill_creation_user_reply_prefers_last_subagent():
    reply = skill_creation_user_reply(
        {
            "created_uploaded_skills": ["carbon-price-2"],
            "subagent_summaries": [
                {"kind": "explore", "summary": "旧调研"},
                {"kind": "browser_digest", "summary": "页面字段：日期、收盘价"},
            ],
            "last_skill_conclusion": json.dumps(
                {"数据名称": "碳市场", "最新记录": {"收盘": 99.0}},
                ensure_ascii=False,
            ),
        }
    )
    assert reply is not None
    assert "carbon-price-2" in reply
    assert "页面字段：日期、收盘价" in reply
    assert "旧调研" not in reply
    assert "99.0" in reply


def test_resolve_fast_skill_management_success():
    reply = _resolve_tool_loop_reply_fast(
        _SKILL_CREATE_MSG,
        {
            "created_uploaded_skills": ["carbon-scraper"],
            "invoked_uploaded_skills": ["carbon-scraper"],
            "last_skill_conclusion": json.dumps(
                {"数据名称": "碳市场", "最新记录": {"收盘": 82.41}},
                ensure_ascii=False,
            ),
            "subagent_summaries": [
                {"kind": "browser_digest", "summary": "已确认页面含收盘价字段"},
            ],
        },
    )
    assert reply is not None
    assert "抱歉" not in reply
    assert "carbon-scraper" in reply
    assert "收盘价字段" in reply
