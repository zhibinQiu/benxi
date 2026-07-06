"""agentkit-loop 终稿 Prompt 组装测试。"""

from agentkit_loop import LoopExitRequest, build_loop_exit_prompt_messages, dict_evidence_provider


def test_build_loop_exit_prompt_messages():
    loop_state = {
        "_execution_plan": type("P", (), {"reasoning": "plan"})(),
        "tool_outcome_lines": ["tool-a: ok"],
    }
    provider = dict_evidence_provider(format_plan=lambda _p: "【步骤】do work")
    messages = build_loop_exit_prompt_messages(
        LoopExitRequest(user_message="hello", loop_state=loop_state),
        provider=provider,
    )
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "hello" in user
    assert "plan" in user
    assert "tool-a" in user
