"""子智能体循环：禁止把「我会搜索」当结论；多 query 全量下发。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from app.agentkit.subagent.loop import (
    _is_promise_only_summary,
    run_subagent_tool_loop,
)
from app.agentkit.subagent.runtime import execute_subagent
from app.agentkit.subagent.types import SubagentKindConfig, SubagentRuntime
from app.agentkit.subagent.config import SubagentConfig
from app.services.agent_skill_router import (
    matches_research_intent,
    should_skip_kg_probe,
)


def test_promise_only_summary_detected():
    assert _is_promise_only_summary("我会先并行搜索两人的近期评价")
    assert not _is_promise_only_summary(
        "万斯优势在于…；德桑蒂斯短板在于…。来源：https://example.com"
    )


def test_research_intent_covers_lookup_phrases():
    assert matches_research_intent("帮我查一下最新报价")
    # 对比/调研类问题不跳过图谱探测（调度默认先快查关键词）
    assert not should_skip_kg_probe("万斯相比德桑蒂斯有哪些优劣势？")
    assert not should_skip_kg_probe("邱智斌是哪个部门的")
    assert should_skip_kg_probe("你好")


def test_subagent_loop_runs_tools_then_answers():
    async def _run():
        kind = SubagentKindConfig(
            kind="search",
            allowed_tools=frozenset({"web_search"}),
            max_rounds=4,
            system_contract="test",
        )
        child: dict = {}
        calls = {"n": 0}

        async def llm_complete(messages, tools):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "message": {
                        "content": "我会先并行搜索…",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "web_search",
                                    "arguments": '{"query":"vance"}',
                                },
                            }
                        ],
                    }
                }
            return {
                "message": {
                    "content": "万斯优势：年轻。德桑蒂斯短板：争议。来源 example.com",
                    "tool_calls": [],
                }
            }

        async def execute_tool(name, args):
            child.setdefault("retrieval_context_parts", []).append(
                "检索摘要：万斯年轻；德桑蒂斯争议"
            )
            child.setdefault("citations", []).append(
                {"index": 1, "title": "ex", "url": "https://example.com"}
            )
            return '{"ok": true, "summary": "联网检索返回 2 条"}'

        def record_tool(state, tool_name, raw_args, result_text, summary, step_id):
            state.setdefault("tool_outcome_lines", []).append(f"{tool_name}: {summary}")
            state.setdefault("executed_tool_calls", []).append(
                {"tool_name": tool_name, "summary": summary, "step_id": step_id}
            )

        summary = await run_subagent_tool_loop(
            kind_config=kind,
            task="对比万斯与德桑蒂斯",
            child_state=child,
            tool_specs=[{"type": "function", "function": {"name": "web_search"}}],
            llm_complete=llm_complete,
            execute_tool=execute_tool,
            record_tool=record_tool,
        )
        assert "我会先" not in summary
        assert "万斯" in summary
        assert child.get("citations")

    asyncio.run(_run())


def test_execute_subagent_embeds_all_queries():
    async def _run():
        captured: dict = {}

        async def llm_complete(messages, tools):
            captured["user"] = messages[1]["content"]
            return {"message": {"content": "结论：两边各有优劣。", "tool_calls": []}}

        runtime = SubagentRuntime(
            kinds={
                "search": SubagentKindConfig(
                    kind="search",
                    allowed_tools=frozenset({"web_search"}),
                    max_rounds=2,
                    system_contract="test",
                )
            }
        )
        cfg = SubagentConfig.full(
            runtime=runtime,
            llm_complete=llm_complete,
            execute_tool=AsyncMock(return_value='{"ok":true,"summary":"ok"}'),
            record_tool=lambda *a, **k: None,
            build_tool_specs=lambda allowed: [],
            invoke_skill=AsyncMock(return_value='{"ok":true,"summary":"ok"}'),
        )
        raw = await execute_subagent(
            config=cfg,
            kind="search",
            task="对比两人",
            queries=["万斯 优劣势", "德桑蒂斯 优劣势"],
            llm_configured=True,
        )
        assert "万斯 优劣势" in captured["user"]
        assert "德桑蒂斯 优劣势" in captured["user"]
        assert "run_tool_batch" in captured["user"]
        assert '"ok": true' in raw.lower() or '"ok":true' in raw.replace(" ", "").lower()

    asyncio.run(_run())


def test_execute_subagent_merges_citations_via_shared_holder():
    """execute_tool 写入 holder 中的 child_state，merge 后父层应有引用。"""

    async def _run():
        parent: dict = {}
        holder: dict = {"state": None}
        calls = {"n": 0}

        async def llm_complete(messages, tools):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "web_search",
                                    "arguments": '{"query":"x"}',
                                },
                            }
                        ],
                    }
                }
            return {"message": {"content": "结论已出。", "tool_calls": []}}

        async def execute_tool(name, args):
            state = holder["state"]
            assert state is not None
            state.setdefault("citations", []).append(
                {"index": 1, "title": "ex", "url": "https://example.com/a"}
            )
            return '{"ok":true,"summary":"ok"}'

        runtime = SubagentRuntime(
            kinds={
                "search": SubagentKindConfig(
                    kind="search",
                    allowed_tools=frozenset({"web_search"}),
                    max_rounds=4,
                    system_contract="test",
                )
            }
        )
        cfg = SubagentConfig.full(
            runtime=runtime,
            llm_complete=llm_complete,
            execute_tool=execute_tool,
            record_tool=lambda *a, **k: None,
            build_tool_specs=lambda allowed: [
                {"type": "function", "function": {"name": "web_search"}}
            ],
            invoke_skill=AsyncMock(return_value='{"ok":true,"summary":"ok"}'),
            child_state_holder=holder,
        )
        raw = await execute_subagent(
            config=cfg,
            kind="search",
            task="查一下",
            loop_state=parent,
            llm_configured=True,
        )
        assert '"ok": true' in raw.lower() or '"ok":true' in raw.replace(" ", "").lower()
        assert parent.get("citations")
        assert parent["citations"][0]["url"] == "https://example.com/a"
        assert holder["state"] is not None
        assert holder["state"].get("citations")

    asyncio.run(_run())


def test_merge_child_citations_reindexes_into_parent():
    from app.agentkit.subagent.context import merge_child_into_parent

    parent = {"citations": [{"index": 1, "title": "p", "url": "https://p.example"}]}
    child = {
        "citations": [
            {"index": 1, "title": "c1", "url": "https://c1.example"},
            {"index": 2, "title": "c2", "url": "https://c2.example"},
        ]
    }
    merge_child_into_parent(
        parent, child, kind="search", task="t", summary="s"
    )
    assert len(parent["citations"]) == 3
    assert parent["citations"][1]["index"] == 2
    assert parent["citations"][2]["index"] == 3
    assert parent["citations"][1]["url"] == "https://c1.example"
