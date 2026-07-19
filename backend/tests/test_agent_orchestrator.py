"""父智能体任务编排验收逻辑。"""

from __future__ import annotations

from app.services.agent_orchestrator import (
    OrchestratorAnswerAssessment,
    OrchestratorTask,
    TaskExecutionResult,
    append_screenshot_markdown_to_reply,
    assess_orchestrator_answer_coverage_rule,
    build_deliverable_brief_for_assessment,
    build_global_round_reflection,
    collect_image_attachments_from_events,
    collect_screenshot_attachments_from_task_results,
    extract_image_attachments_from_markdown,
    should_escalate_to_skill_dev,
    tasks_from_routes,
    verify_task_result,
)
from app.services.agent_reply_synth import is_substantive_deliverable
from app.services.agent_supervisor import AgentRoute


def test_tasks_from_routes_one_per_route():
    routes = [
        AgentRoute(agent_id="platform", reason="平台"),
    ]
    tasks = tasks_from_routes(routes)
    assert len(tasks) == 1
    assert tasks[0].id == "t1"
    assert tasks[0].agent_id == "platform"


def test_verify_rejects_tool_failure():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    events = [
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "status": "failed",
                "detail": "权限不足",
            },
        }
    ]
    ok, summary, hint = verify_task_result(task, events, {"reply": "失败了"})
    assert ok is False
    assert not summary
    assert "重试" in hint or "权限" in hint


def test_verify_accepts_tool_success_reply():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    events = [
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "status": "done",
                "detail": "文件夹已创建",
            },
        }
    ]
    ok, summary, hint = verify_task_result(
        task, events, {"reply": "已在文档库创建文件夹「喝水」"}
    )
    assert ok is True
    assert "喝水" in summary
    assert not hint


def test_verify_rejects_excuse_without_tools():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    ok, _, hint = verify_task_result(
        task,
        [],
        {"reply": "小析无直接创建本地文件夹的工具，建议您手动新建"},
    )
    assert ok is False
    assert hint


def test_verify_rejects_denial_even_without_legacy_markers():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    ok, _, hint = verify_task_result(
        task,
        [],
        {"reply": "抱歉，我无法设置定时提醒，建议您使用手机自带的计时器"},
    )
    assert ok is False
    assert hint


def test_verify_rejects_platform_reply_without_tool_evidence():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    ok, _, hint = verify_task_result(
        task,
        [],
        {"reply": "已在文档库创建文件夹「喝水」"},
    )
    assert ok is False
    assert "工具" in hint


def test_verify_rejects_tool_evidence_without_deliverable_reply():
    task = OrchestratorTask(
        id="t1", title="文档查阅", agent_id="platform", reason="总结文档"
    )
    events = [
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "detail": "已读取「测试」正文 18191 字",
                "status": "done",
            },
        }
    ]
    ok, _, hint = verify_task_result(task, events, {"reply": ""})
    assert ok is False
    assert hint


def test_is_substantive_deliverable():
    assert not is_substantive_deliverable("已读取正文 18191 字")
    assert is_substantive_deliverable(
        "本文介绍了 Claude Code 的架构设计、工具链治理与工程实践要点。"
    )


def test_verify_tool_success_requires_substantive_reply():
    task = OrchestratorTask(
        id="t1", title="平台操作", agent_id="platform", reason="x"
    )
    events = [
        {
            "type": "workflow",
            "data": {
                "phase": "tool_result",
                "status": "done",
                "tool_name": "schedule_notification",
                "detail": "喝水 · 2026-06-26 15:00:08",
            },
        }
    ]
    ok, summary, hint = verify_task_result(
        task,
        events,
        {"reply": "抱歉，我无法设置定时提醒或闹钟，建议您使用手机自带的计时器"},
    )
    assert ok is False
    assert hint

    ok2, summary2, _ = verify_task_result(
        task,
        events,
        {
            "reply": "已为您设置喝水提醒，将于 2026-06-26 15:00:08 通过系统通知提醒您"
        },
    )
    assert ok2 is True
    assert "喝水" in summary2


def test_should_escalate_to_skill_dev_on_platform_failure():
    task = OrchestratorTask(
        id="t1",
        title="平台操作",
        agent_id="platform",
        reason="x",
        last_error="请调用平台工具完成该步骤，勿仅口头说明无法操作",
    )
    assert should_escalate_to_skill_dev(task, satisfied=False, events=[]) is True


def test_should_not_escalate_on_permission_error():
    task = OrchestratorTask(
        id="t1",
        title="平台操作",
        agent_id="platform",
        reason="x",
        last_error="请修正后重试：权限不足",
    )
    assert should_escalate_to_skill_dev(task, satisfied=False, events=[]) is False


def test_collect_image_attachments_dedupes_by_url():
    events = [
        {
            "type": "attachment",
            "data": {
                "type": "image",
                "url": "/api/v1/browser-rpa/screenshot?key=a",
                "title": "截图1",
            },
        },
        {
            "type": "attachment",
            "data": {
                "type": "image",
                "url": "/api/v1/browser-rpa/screenshot?key=a",
                "title": "重复",
            },
        },
        {
            "type": "workflow",
            "data": {"phase": "tool_result"},
        },
    ]
    out = collect_image_attachments_from_events(events)
    assert len(out) == 1
    assert out[0]["url"].endswith("key=a")


def test_append_screenshot_markdown_appends_unique_images():
    attachments = [
        {
            "type": "image",
            "url": "/api/v1/browser-rpa/screenshot?key=shot1",
            "title": "百度搜索",
        }
    ]
    merged = append_screenshot_markdown_to_reply("已完成搜索。", attachments)
    assert "已完成搜索。" in merged
    assert "### 页面截图" in merged
    assert "![百度搜索](/api/v1/browser-rpa/screenshot?key=shot1)" in merged


def test_append_screenshot_markdown_skips_existing_url():
    url = "/api/v1/browser-rpa/screenshot?key=shot1"
    reply = f"见截图 ![x]({url})"
    merged = append_screenshot_markdown_to_reply(
        reply,
        [{"type": "image", "url": url, "title": "x"}],
    )
    assert merged.count(url) == 1


def test_extract_image_attachments_from_markdown():
    url = "/api/v1/browser-rpa/screenshot?key=baidu1"
    reply = f"已完成搜索。\n\n![百度搜索]({url})"
    out = extract_image_attachments_from_markdown(reply)
    assert len(out) == 1
    assert out[0]["url"] == url
    assert out[0]["title"] == "百度搜索"


def test_extract_image_attachments_from_plain_url():
    url = "/api/v1/browser-rpa/screenshot?key=baidu-plain"
    reply = f"已完成搜索。截图：{url}"
    out = extract_image_attachments_from_markdown(reply)
    assert len(out) == 1
    assert out[0]["url"] == url


def test_collect_screenshot_attachments_from_task_results_merges_events_and_reply():
    url = "/api/v1/browser-rpa/screenshot?key=merged"
    events = [
        {
            "type": "attachment",
            "data": {"type": "image", "url": url, "title": "流式截图"},
        }
    ]
    result = type(
        "R",
        (),
        {
            "events": events,
            "complete": {
                "reply": f"结果如下 ![dup]({url})",
            },
        },
    )()
    out = collect_screenshot_attachments_from_task_results([result])
    assert len(out) == 1
    assert out[0]["url"] == url


def _task_result(
    *,
    agent_id: str = "platform",
    summary: str = "",
    satisfied: bool = True,
    last_error: str = "",
) -> TaskExecutionResult:
    task = OrchestratorTask(
        id="t1",
        title="检索研究",
        agent_id=agent_id,
        reason="x",
        summary=summary,
        last_error=last_error,
    )
    return TaskExecutionResult(
        task=task,
        route=AgentRoute(agent_id=agent_id, reason="x"),
        satisfied=satisfied,
    )


def test_assess_rule_rejects_empty_results():
    out = assess_orchestrator_answer_coverage_rule("总结这篇文章", [])
    assert out.addresses_user is False
    assert "无子任务" in out.reason


def test_assess_rule_rejects_all_unsatisfied():
    results = [
        _task_result(satisfied=False, last_error="工具失败"),
    ]
    out = assess_orchestrator_answer_coverage_rule("总结这篇文章", results)
    assert out.addresses_user is False
    assert "均未" in out.reason


def test_assess_rule_rejects_tool_status_as_deliverable():
    results = [
        _task_result(summary="已读取「测试.pdf」正文 18191 字"),
    ]
    out = assess_orchestrator_answer_coverage_rule("请总结这篇文章内容", results)
    assert out.addresses_user is False
    assert out.gap


def test_assess_rule_accepts_substantive_summary():
    results = [
        _task_result(
            summary="本文介绍了碳市场配额机制、交易流程与近期政策调整要点。"
        ),
    ]
    out = assess_orchestrator_answer_coverage_rule("请总结这篇文章", results)
    assert out.addresses_user is True


def test_build_deliverable_brief_lists_task_status():
    results = [
        _task_result(summary="要点一、二、三", satisfied=True),
        _task_result(summary="", satisfied=False, last_error="权限不足"),
    ]
    brief = build_deliverable_brief_for_assessment(results)
    assert "完成" in brief
    assert "未完成" in brief
    assert "权限不足" in brief


def test_build_global_round_reflection_includes_gap_and_brief():
    assessment = OrchestratorAnswerAssessment(
        False,
        reason="缺少实质交付物",
        gap="尚未形成对用户问题的回答",
    )
    results = [
        _task_result(summary="已读取正文 12000 字", satisfied=True),
    ]
    text = build_global_round_reflection(
        global_round=0,
        assessment=assessment,
        results=results,
    )
    assert "第 1 轮全局验收未通过" in text
    assert "尚未形成对用户问题的回答" in text
    assert "已读取正文" in text


def test_fallback_specialist_correction_includes_failures():
    from app.services.agent_orchestrator import _fallback_specialist_correction

    task = OrchestratorTask(
        id="t1",
        title="技能开发",
        agent_id="skill-dev",
        reason="x",
    )
    text = _fallback_specialist_correction(
        task=task,
        rule_hint="请修正后重试：参数无效",
        failures=["create_skill: 参数无效：params"],
        specialist_reply="",
    )
    assert "参数无效" in text
    assert "skill-development" in text


def test_build_global_round_reflection_includes_correction_instruction():
    assessment = OrchestratorAnswerAssessment(
        False,
        reason="子任务均未验收通过",
        gap="技能创建失败",
    )
    task = OrchestratorTask(
        id="t1",
        title="技能开发",
        agent_id="skill-dev",
        reason="x",
        correction_instruction="改用 create_skill 直接创建技能包",
    )
    results = [
        TaskExecutionResult(
            task=task,
            route=None,
            events=[],
            complete=None,
            satisfied=False,
        )
    ]
    text = build_global_round_reflection(
        global_round=0,
        assessment=assessment,
        results=results,
    )
    assert "调度改正指引" in text
    assert "invoke_skill" in text
