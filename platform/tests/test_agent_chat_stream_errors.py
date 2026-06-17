"""Dify 流式对话：正文已生成后的非致命错误处理。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.agent_chat_client import iter_agent_chat_stream


def _sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}"


async def _collect_stream(lines: list[str]) -> list[dict]:
    async def fake_aiter_lines():
        for line in lines:
            yield line

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = fake_aiter_lines
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.stream = lambda *a, **k: mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    out: list[dict] = []
    with patch("app.integrations.agent_chat_client.httpx.AsyncClient", return_value=mock_client):
        async for chunk in iter_agent_chat_stream(
            base_url="http://dify.test",
            api_key="key",
            query="测试",
            user_id="u1",
            feature_label="双碳问答",
        ):
            out.append(json.loads(chunk))
    return out


@pytest.mark.asyncio
async def test_stream_ignores_error_after_answer():
    lines = [
        _sse_line({"event": "message", "answer": "结论如下。"}),
        _sse_line({"event": "error", "message": "retriever failed"}),
    ]
    payloads = await _collect_stream(lines)
    assert not any("error" in p for p in payloads)
    assert payloads[-1]["done"] is True
    assert payloads[-1]["reply"] == "结论如下。"


@pytest.mark.asyncio
async def test_stream_emits_citations_before_done():
    lines = [
        _sse_line({"event": "message", "answer": "见 [1]。"}),
        _sse_line(
            {
                "event": "message_end",
                "metadata": {
                    "retriever_resources": [
                        {
                            "document_name": "政策汇编",
                            "content": "引用片段",
                        }
                    ]
                },
            }
        ),
    ]
    payloads = await _collect_stream(lines)
    cite_events = [p for p in payloads if p.get("citations")]
    assert len(cite_events) == 1
    assert cite_events[0]["citations"][0]["title"] == "政策汇编"
    assert payloads[-1]["done"] is True
    assert payloads[-1]["citations"][0]["title"] == "政策汇编"
