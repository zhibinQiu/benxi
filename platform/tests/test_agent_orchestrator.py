"""父智能体任务编排验收逻辑。"""

from __future__ import annotations

from app.services.agent_orchestrator import (
    OrchestratorTask,
    append_screenshot_markdown_to_reply,
    collect_image_attachments_from_events,
    collect_screenshot_attachments_from_task_results,
    extract_image_attachments_from_markdown,
    tasks_from_routes,
    verify_task_result,
)
from app.services.agent_supervisor import AgentRoute


def test_tasks_from_routes_one_per_route():
    routes = [
        AgentRoute(agent_id="platform", reason="平台"),
        AgentRoute(agent_id="scheduler", reason="定时"),
    ]
    tasks = tasks_from_routes(routes)
    assert len(tasks) == 2
    assert tasks[0].id == "t1"
    assert tasks[0].agent_id == "platform"
    assert tasks[1].agent_id == "scheduler"


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


def test_verify_tool_success_overrides_denial_reply():
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
    assert ok is True
    assert "喝水" in summary
    assert not hint


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
