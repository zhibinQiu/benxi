"""LLM workflow 流式事件测试。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.integrations.deepseek_client import format_llm_stream_error
from app.services.llm_workflow_stream import iter_llm_answer_events


def test_format_llm_stream_error_payment_required():
    req = httpx.Request("POST", "https://api.example/v1/chat/completions")
    resp = httpx.Response(402, request=req)
    err = httpx.HTTPStatusError("402", request=req, response=resp)
    assert "余额" in format_llm_stream_error(err)


def test_iter_llm_answer_events_surfaces_stream_error(monkeypatch):
    async def fake_parts(**kwargs):
        yield {"kind": "error", "text": "语言模型账户余额不足或配额已用尽，请联系管理员"}

    monkeypatch.setattr(
        "app.services.llm_workflow_stream.chat_completion_stream_parts",
        fake_parts,
    )

    async def _run():
        return [
            ev
            async for ev in iter_llm_answer_events(
                messages=[{"role": "user", "content": "test"}],
                skip_initial_thinking=True,
            )
        ]

    events = asyncio.run(_run())
    assert any(ev.get("type") == "error" for ev in events)
    err = next(ev for ev in events if ev.get("type") == "error")
    assert "余额" in err.get("message", "")
