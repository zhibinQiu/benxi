"""AI 对话流式收尾：先 workflow_finished，再 replace/done，后 conversation_id / follow_up。"""

import asyncio
import json
from unittest.mock import patch
from uuid import uuid4


async def _collect(gen):
    return [json.loads(chunk) async for chunk in gen]


def test_stream_turn_tail_done_before_follow_up():
    user_id = uuid4()

    async def _run():
        with (
            patch(
                "app.services.ai_chat_service.run_db_task",
                return_value="conv-new",
            ),
            patch(
                "app.services.ai_chat_service._resolve_follow_up_questions",
                return_value=["继续展开？"],
            ),
            patch(
                "app.services.ai_chat_service._emit_workflow",
            ) as mock_emit,
        ):
            async def _fake_workflow(*_a, **_k):
                yield json.dumps({"workflow": {"phase": "workflow_finished"}})

            mock_emit.side_effect = lambda *_a, **_k: _fake_workflow()
            return await _collect(
                _iter_stream_turn_tail(
                    user_id=user_id,
                    message="你好",
                    history=[],
                    conversation_id=None,
                    normalized_reply="你好，我是小析。",
                    display_citations=[],
                    kg_context=None,
                    streamed_content=True,
                    tool_loop=True,
                )
            )

    from app.services.ai_chat_service import _iter_stream_turn_tail

    payloads = asyncio.run(_run())
    kinds = [next(iter(p.keys())) for p in payloads]
    assert kinds[0] == "workflow"
    assert kinds[1] == "done"
    assert "follow_up_questions" in kinds
    assert kinds.index("done") < kinds.index("follow_up_questions")
    assert payloads[1]["reply"] == "你好，我是小析。"
    assert payloads[1]["conversation_id"] is None


def test_stream_turn_tail_replace_when_not_streamed():
    user_id = uuid4()

    async def _run():
        from app.services.ai_chat_service import _iter_stream_turn_tail

        with (
            patch("app.services.ai_chat_service.run_db_task", return_value="conv-1"),
            patch(
                "app.services.ai_chat_service._resolve_follow_up_questions",
                return_value=[],
            ),
            patch("app.services.ai_chat_service._emit_workflow") as mock_emit,
        ):
            async def _fake_workflow(*_a, **_k):
                yield json.dumps({"workflow": {"phase": "workflow_finished"}})

            mock_emit.side_effect = lambda *_a, **_k: _fake_workflow()
            return await _collect(
                _iter_stream_turn_tail(
                    user_id=user_id,
                    message="你好",
                    history=[],
                    conversation_id="conv-1",
                    normalized_reply="完整回复",
                    display_citations=[],
                    kg_context=None,
                    streamed_content=False,
                    tool_loop=True,
                )
            )

    payloads = asyncio.run(_run())
    assert payloads[0]["workflow"]["phase"] == "workflow_finished"
    assert payloads[1] == {"replace": "完整回复"}
    assert payloads[2]["done"] is True
