"""DAG 波次调度 — 按拓扑层并行执行 ready 节点。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.agent.orchestrate.dag import TaskDAG
from app.agent.orchestrate.events import workflow_task_event
from app.agent.orchestrate.ids import new_task_step_id
from app.agent.orchestrate.parallel import iter_parallel_task_events
from app.agent.orchestrate.types import ORCH_TASK_RESULT, TaskExecutionResult
from app.agent.route.types import AgentRoute

_logger = logging.getLogger(__name__)

NodeRunner = Callable[..., AsyncIterator[dict[str, Any]]]


async def iter_dag_wave_events(
    dag: TaskDAG,
    *,
    run_one_node: NodeRunner,
    max_parallel: int = 3,
    agent_title_fn: Callable[[str], str] | None = None,
    **run_kwargs: Any,
) -> AsyncIterator[tuple[str, Any]]:
    """按波次调度 DAG。

    产出 (kind, payload)：
    - ``event``: 客户端 workflow / 其他事件
    - ``result``: TaskExecutionResult（单节点完成）
    - ``wave_done``: 本波次结束（payload=node ids）
    - ``dag_done``: 整图结束（payload=dag）
    """
    max_par = max(1, int(max_parallel or 1))
    safety = 0
    max_waves = max(1, len(dag.nodes) + 2)

    while not dag.all_terminal() and safety < max_waves:
        safety += 1
        ready = dag.ready_nodes(limit=max_par)
        if not ready:
            # 上游失败导致下游无法启动 → 标记 blocked 为 failed
            blocked = dag.blocked_by_failure()
            if blocked:
                for node in blocked:
                    dag.mark_failed(node.id, error="blocked by upstream failure")
                    task = node.to_orchestrator_task()
                    yield (
                        "event",
                        workflow_task_event(
                            "task_failed",
                            task,
                            step_id=new_task_step_id(node.id),
                            detail=node.last_error,
                            all_tasks=dag.orchestrator_tasks(),
                            agent_title_fn=agent_title_fn,
                            mode="dag",
                        ),
                    )
                continue
            # 无 ready 且无 blocked：图卡住（不应发生）
            _logger.warning("DAG scheduler stuck with no ready nodes")
            for node in dag.nodes:
                if node.status == "pending":
                    dag.mark_failed(node.id, error="scheduler stuck")
            break

        for node in ready:
            dag.mark_running(node.id)
            yield (
                "event",
                workflow_task_event(
                    "task_started",
                    node.to_orchestrator_task(),
                    step_id=new_task_step_id(node.id),
                    detail=node.goal or node.reason,
                    all_tasks=dag.orchestrator_tasks(),
                    agent_title_fn=agent_title_fn,
                    mode="dag",
                ),
            )

        tasks = [n.to_orchestrator_task() for n in ready]
        routes = [
            AgentRoute(agent_id=n.agent_id, reason=n.reason or n.goal or n.title)
            for n in ready
        ]
        wave_ids = [n.id for n in ready]
        results_by_id: dict[str, TaskExecutionResult] = {}

        async def run_one_task(_sess, *, task, route, **_kw):
            node = dag.get(task.id)
            if node is None:
                yield {
                    "type": ORCH_TASK_RESULT,
                    "result": TaskExecutionResult(
                        task=task,
                        route=route,
                        satisfied=False,
                    ),
                }
                return
            async for event in run_one_node(node=node, task=task, route=route, **run_kwargs):
                if event.get("type") == ORCH_TASK_RESULT:
                    yield event
                else:
                    yield event

        async for kind, payload in iter_parallel_task_events(
            tasks,
            routes,
            session_factory=lambda: None,
            run_one_task=run_one_task,
            all_tasks=dag.orchestrator_tasks(),
            agent_title_fn=agent_title_fn,
            close_session=None,
        ):
            if kind == "event":
                yield "event", payload
            elif kind == "result" and isinstance(payload, TaskExecutionResult):
                results_by_id[payload.task.id] = payload
                yield "result", payload

        for node in ready:
            result = results_by_id.get(node.id)
            reply = ""
            if result and result.complete:
                reply = str(result.complete.get("reply") or "").strip()
            satisfied = bool(result and result.satisfied and reply)
            if satisfied:
                dag.mark_done(node.id, reply=reply)
                yield (
                    "event",
                    workflow_task_event(
                        "task_done",
                        node.to_orchestrator_task(),
                        step_id=new_task_step_id(node.id),
                        detail=reply[:240],
                        all_tasks=dag.orchestrator_tasks(),
                        agent_title_fn=agent_title_fn,
                        mode="dag",
                    ),
                )
            else:
                err = ""
                if result and result.complete:
                    err = str(result.complete.get("reply") or "").strip()[:200]
                if not err:
                    err = "task produced no reply"
                dag.mark_failed(node.id, error=err)
                yield (
                    "event",
                    workflow_task_event(
                        "task_failed",
                        node.to_orchestrator_task(),
                        step_id=new_task_step_id(node.id),
                        detail=err,
                        all_tasks=dag.orchestrator_tasks(),
                        agent_title_fn=agent_title_fn,
                        mode="dag",
                    ),
                )

        yield "wave_done", wave_ids

    # 仍 pending 的标记失败
    for node in dag.nodes:
        if node.status in ("pending", "running"):
            dag.mark_failed(node.id, error="incomplete at scheduler exit")
            yield (
                "event",
                workflow_task_event(
                    "task_failed",
                    node.to_orchestrator_task(),
                    step_id=new_task_step_id(node.id),
                    detail=node.last_error,
                    all_tasks=dag.orchestrator_tasks(),
                    agent_title_fn=agent_title_fn,
                    mode="dag",
                ),
            )

    yield "dag_done", dag
