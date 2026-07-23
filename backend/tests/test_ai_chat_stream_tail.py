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
        async def _follow_ups():
            return ["配额不足如何购买？", "履约截止日是哪天？"]

        follow_up_task = asyncio.create_task(_follow_ups())
        with (
            patch(
                "app.services.ai_chat_service.run_db_task",
                return_value="conv-new",
            ),
            patch(
                "app.services.ai_chat_service._emit_workflow",
            ) as mock_emit,
        ):
            async def _fake_workflow(*_a, **_k):
                yield json.dumps({"workflow": {"phase": "workflow_finished"}})

            mock_emit.side_effect = lambda *_a, **_k: _fake_workflow()
            from app.services.ai_chat_service import _iter_stream_turn_tail

            return await _collect(
                _iter_stream_turn_tail(
                    user_id=user_id,
                    message="全国碳市场怎么履约？",
                    history=[],
                    conversation_id=None,
                    normalized_reply="履约需按期清缴配额，不足部分可购买。",
                    display_citations=[],
                    kg_context=None,
                    streamed_content=True,
                    tool_loop=True,
                    follow_up_task=follow_up_task,
                )
            )

    payloads = asyncio.run(_run())
    kinds = [next(iter(p.keys())) for p in payloads]
    assert kinds[0] == "workflow"
    assert kinds[1] == "done"
    assert "follow_up_questions" in kinds
    assert kinds.index("done") < kinds.index("follow_up_questions")
    assert payloads[1]["reply"] == "履约需按期清缴配额，不足部分可购买。"
    assert payloads[1]["conversation_id"] is None


def test_stream_turn_tail_no_follow_up_without_task():
    """无 follow_up_task 时不展示劣质兜底推荐。"""
    user_id = uuid4()

    async def _run():
        from app.services.ai_chat_service import _iter_stream_turn_tail

        with (
            patch("app.services.ai_chat_service.run_db_task", return_value="conv-1"),
            patch("app.services.ai_chat_service._emit_workflow") as mock_emit,
        ):
            async def _fake_workflow(*_a, **_k):
                yield json.dumps({"workflow": {"phase": "workflow_finished"}})

            mock_emit.side_effect = lambda *_a, **_k: _fake_workflow()
            return await _collect(
                _iter_stream_turn_tail(
                    user_id=user_id,
                    message="全国碳市场怎么履约？",
                    history=[],
                    conversation_id="conv-1",
                    normalized_reply="完整回复，包含较多细节以便过去兜底逻辑可切句。",
                    display_citations=[],
                    kg_context=None,
                    streamed_content=False,
                    tool_loop=True,
                )
            )

    payloads = asyncio.run(_run())
    assert payloads[0]["workflow"]["phase"] == "workflow_finished"
    assert payloads[1] == {"replace": "完整回复，包含较多细节以便过去兜底逻辑可切句。"}
    assert payloads[2]["done"] is True
    assert all("follow_up_questions" not in p for p in payloads)
