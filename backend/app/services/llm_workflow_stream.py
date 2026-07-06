"""LLM 流式输出 + workflow 事件（思考过程 / 正文 delta）共用逻辑。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.core.agent_message_parse import DsmlStreamFilter, sanitize_agent_user_reply
from app.integrations.deepseek_client import chat_completion_stream_parts


async def iter_llm_answer_events(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    think_title: str = "正在组织回答",
    think_detail: str = "分析材料并生成回答…",
    timeout: float = 300.0,
    step_id: str | None = None,
    skip_initial_thinking: bool = False,
    unlimited_output: bool = False,
    max_total_chars: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """产出 workflow / delta 结构化事件，供各流式 API 包装为 SSE。"""
    answer_think_id = step_id or f"answer-{uuid.uuid4().hex[:8]}"
    if not skip_initial_thinking:
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thinking",
                "title": think_title,
                "detail": think_detail,
                "tool": "llm",
                "step_id": answer_think_id,
            },
        }

    answer_thought_done = False
    content_emitted = False
    dsml_filter = DsmlStreamFilter()
    async for part in chat_completion_stream_parts(
        messages=messages,
        temperature=temperature,
        timeout=timeout,
        unlimited_output=unlimited_output,
        max_total_chars=max_total_chars,
    ):
        kind = part.get("kind")
        text = part.get("text") or ""
        if kind == "error":
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "模型调用失败",
                    "detail": text,
                    "tool": "llm",
                    "step_id": answer_think_id,
                    "status": "failed",
                },
            }
            yield {"type": "error", "message": text}
            return
        if kind == "reasoning" and text:
            yield {
                "type": "workflow",
                "data": {
                    "phase": "thinking_delta",
                    "step_id": answer_think_id,
                    "delta": text,
                    "title": think_title,
                    "tool": "llm",
                },
            }
            continue
        if kind != "content" or not text:
            continue
        if not answer_thought_done:
            thought_detail = ""
            yield {
                "type": "workflow",
                "data": {
                    "phase": "agent_thought",
                    "title": "思考完成",
                    "detail": thought_detail,
                    "tool": "llm",
                    "step_id": answer_think_id,
                    "status": "done",
                },
            }
            answer_thought_done = True
        clean = dsml_filter.feed(text)
        if clean:
            content_emitted = True
            yield {"type": "delta", "text": clean}

    raw_before_flush = dsml_filter.raw_text
    tail = dsml_filter.flush()
    if tail:
        content_emitted = True
        yield {"type": "delta", "text": tail}

    if not content_emitted and raw_before_flush.strip():
        recovered = sanitize_agent_user_reply(raw_before_flush)
        if recovered:
            if not answer_thought_done:
                yield {
                    "type": "workflow",
                    "data": {
                        "phase": "agent_thought",
                        "title": "思考完成",
                        "detail": "",
                        "tool": "llm",
                        "step_id": answer_think_id,
                        "status": "done",
                    },
                }
                answer_thought_done = True
            content_emitted = True
            yield {"type": "delta", "text": recovered}

    if not answer_thought_done:
        yield {
            "type": "workflow",
            "data": {
                "phase": "agent_thought",
                "title": "思考完成",
                "detail": "模型未返回正文",
                "tool": "llm",
                "step_id": answer_think_id,
                "status": "done",
            },
        }
