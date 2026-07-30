"""Task DAG 模型、规划解析与波次调度测试。"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.agent.orchestrate.dag import TaskNode, build_task_dag
from app.agent.orchestrate.types import ORCH_TASK_RESULT, TaskExecutionResult
from app.core.agent.types import AgentRoute
from app.services.agent_task_dag_planner import (
    agent_plan_detail_lines,
    build_node_user_message,
    dag_from_flat_routes,
    fallback_join_replies,
    parse_task_dag_payload,
    should_attempt_task_dag,
)


def test_dag_rejects_cycle():
    with pytest.raises(ValueError, match="cycle"):
        build_task_dag(
            [
                TaskNode(id="a", title="A", agent_id="platform", depends_on=("b",)),
                TaskNode(id="b", title="B", agent_id="report", depends_on=("a",)),
            ]
        )


def test_dag_rejects_unknown_dependency():
    with pytest.raises(ValueError, match="unknown dependency"):
        build_task_dag(
            [
                TaskNode(id="a", title="A", agent_id="platform", depends_on=("missing",)),
            ]
        )


def test_ready_nodes_wave_order():
    dag = build_task_dag(
        [
            TaskNode(id="t1", title="A", agent_id="platform"),
            TaskNode(id="t2", title="B", agent_id="carbon"),
            TaskNode(id="t3", title="C", agent_id="report", depends_on=("t1", "t2")),
        ]
    )
    ready = dag.ready_nodes()
    assert [n.id for n in ready] == ["t1", "t2"]
    dag.mark_done("t1", reply="ok1")
    dag.mark_done("t2", reply="ok2")
    ready2 = dag.ready_nodes()
    assert [n.id for n in ready2] == ["t3"]
    assert dag.summary_chain() == "A∥B → C"


def test_parse_task_dag_payload_strips_bad_deps_and_agents():
    dag = parse_task_dag_payload(
        {
            "tasks": [
                {
                    "id": "t1",
                    "title": "平台",
                    "agent_id": "platform",
                    "goal": "list todos",
                    "depends_on": ["ghost"],
                },
                {
                    "id": "t2",
                    "title": "碳",
                    "agent_id": "carbon",
                    "goal": "price",
                    "depends_on": ["t1"],
                },
                {
                    "id": "t3",
                    "title": "坏",
                    "agent_id": "not-an-agent",
                    "goal": "x",
                },
            ]
        },
        allowed_agents={"platform", "carbon", "orchestrator"},
        max_nodes=4,
    )
    assert dag is not None
    assert [n.id for n in dag.nodes] == ["t1", "t2"]
    assert dag.get("t1").depends_on == ()
    assert dag.get("t2").depends_on == ("t1",)


def test_parse_cycle_degrades_to_no_edges():
    dag = parse_task_dag_payload(
        {
            "tasks": [
                {"id": "t1", "agent_id": "platform", "depends_on": ["t2"], "title": "A"},
                {"id": "t2", "agent_id": "carbon", "depends_on": ["t1"], "title": "B"},
            ]
        },
        allowed_agents={"platform", "carbon"},
    )
    assert dag is not None
    assert all(n.depends_on == () for n in dag.nodes)


def test_dag_from_flat_routes_sequential_and_parallel():
    routes = [
        AgentRoute(agent_id="platform", reason="todos"),
        AgentRoute(agent_id="carbon", reason="price"),
    ]
    seq = dag_from_flat_routes(routes, message="先查待办然后查碳价", mode="sequential")
    assert seq is not None
    assert seq.get("t2").depends_on == ("t1",)

    par = dag_from_flat_routes(routes, message="同时查待办以及碳价", mode="parallel")
    assert par is not None
    assert all(n.depends_on == () for n in par.nodes)


def test_should_attempt_task_dag_signals():
    assert should_attempt_task_dag("先查报告然后创建待办", route_count=1) is True
    assert should_attempt_task_dag("你好", route_count=1) is False
    assert should_attempt_task_dag("查一下碳价", route_count=2) is True


def test_build_node_user_message_injects_parents():
    node = TaskNode(id="t2", title="报告", agent_id="report", goal="写摘要")
    msg = build_node_user_message(
        "帮我写报告",
        node,
        [("平台", "待办有 3 条")],
    )
    assert "本步目标" in msg
    assert "上游 平台 结论" in msg
    assert "待办有 3 条" in msg


def test_agent_plan_detail_lines():
    dag = build_task_dag(
        [
            TaskNode(id="t1", title="A", agent_id="platform", goal="g1"),
            TaskNode(id="t2", title="B", agent_id="report", depends_on=("t1",), goal="g2"),
        ]
    )
    text = agent_plan_detail_lines(dag)
    assert "1. A" in text
    assert "依赖 t1" in text


def test_fallback_join_replies():
    text = fallback_join_replies(
        [
            {"title": "平台", "reply": "ok1"},
            {"title": "碳", "reply": "ok2"},
        ]
    )
    assert "【平台】" in text
    assert "ok2" in text


def test_iter_dag_wave_events_serial_then_parallel():
    from app.agent.orchestrate.scheduler import iter_dag_wave_events

    dag = build_task_dag(
        [
            TaskNode(id="t1", title="A", agent_id="platform"),
            TaskNode(id="t2", title="B", agent_id="carbon"),
            TaskNode(id="t3", title="C", agent_id="report", depends_on=("t1", "t2")),
        ]
    )
    order: list[str] = []

    async def run_one_node(*, node, task, route, **_kw):
        order.append(node.id)
        complete = {"type": "complete", "reply": f"done-{node.id}", "citations": []}
        yield {
            "type": ORCH_TASK_RESULT,
            "result": TaskExecutionResult(
                task=task,
                route=route,
                complete=complete,
                satisfied=True,
            ),
        }

    async def _run():
        waves: list[list[str]] = []
        async for kind, payload in iter_dag_wave_events(
            dag,
            run_one_node=run_one_node,
            max_parallel=3,
        ):
            if kind == "wave_done":
                waves.append(list(payload))
        return waves

    waves = asyncio.run(_run())
    assert set(waves[0]) == {"t1", "t2"}
    assert waves[1] == ["t3"]
    assert set(order) == {"t1", "t2", "t3"}
    assert dag.is_complete_success()


def test_synthesize_dag_final_reply_fallback_without_llm(monkeypatch):
    from app.services import agent_task_dag_planner as planner

    monkeypatch.setattr(
        "app.integrations.deepseek_client.is_configured",
        lambda: False,
    )

    async def _run():
        return await planner.synthesize_dag_final_reply(
            "汇总",
            [
                {"title": "A", "reply": "结果一"},
                {"title": "B", "reply": "结果二"},
            ],
        )

    reply = asyncio.run(_run())
    assert "结果一" in reply
    assert "结果二" in reply


def test_execute_task_dag_calls_synthesizer(monkeypatch):
    """Supervisor DAG 路径使用 synthesizer，而非纯拼接。"""
    from app.core.agent_loop_session import AgentLoopSession
    from app.services import agent_supervisor as supervisor

    dag = build_task_dag(
        [
            TaskNode(id="t1", title="A", agent_id="platform", goal="g1"),
            TaskNode(id="t2", title="B", agent_id="carbon", goal="g2"),
        ]
    )
    synth_calls: list[list] = []

    async def fake_synth(user_message, results):
        synth_calls.append(results)
        return "SYNTHESIZED"

    async def fake_hop(sess, user_id, *, route, user_message, **kwargs):
        yield {
            "type": "complete",
            "reply": f"hop-{route.agent_id}",
            "messages": [],
            "citations": [],
            "kg_context": None,
        }

    monkeypatch.setattr(supervisor, "_run_specialist_hop", fake_hop)
    monkeypatch.setattr(
        "app.services.agent_task_dag_planner.synthesize_dag_final_reply",
        fake_synth,
    )

    async def _run():
        events = []
        async for ev in supervisor._execute_task_dag(
            AgentLoopSession(uuid.uuid4()),
            uuid.uuid4(),
            dag=dag,
            user_message="同时查待办以及碳价",
            chat_history=None,
            retrieval_context="",
            context_instruction="",
            conversation_id=None,
            attachment_session_id=None,
            intent_plan=None,
            max_rounds=1,
            messages=[],
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    assert synth_calls, "synthesizer must be called"
    complete = [e for e in events if e.get("type") == "complete"]
    assert complete
    assert complete[-1]["reply"] == "SYNTHESIZED"
    phases = [
        e.get("data", {}).get("phase")
        for e in events
        if e.get("type") == "workflow"
    ]
    assert "plan_tasks" in phases
    assert "agent_plan" in phases
