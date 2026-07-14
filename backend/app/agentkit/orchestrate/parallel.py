"""并行子任务 worker 池 — 合并事件流。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal, TypeVar

from app.agentkit.orchestrate.events import workflow_task_event
from app.agentkit.orchestrate.ids import new_task_step_id
from app.agentkit.orchestrate.types import ORCH_TASK_RESULT, OrchestratorTask, TaskExecutionResult

_logger = logging.getLogger(__name__)
TSession = TypeVar("TSession")
StreamKind = Literal["event", "result", "done"]

TaskRunner = Callable[..., AsyncIterator[dict[str, Any]]]


async def iter_task_event_parts(
    stream: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[tuple[StreamKind, Any]]:
    """单路子任务流：按 kind 分流客户端事件与终态 result。"""
    async for event in stream:
        match event.get("type"):
            case t if t == ORCH_TASK_RESULT:
                yield "result", event["result"]
            case _:
                yield "event", event


async def iter_parallel_task_events(
    tasks: list[OrchestratorTask],
    routes: list[Any],
    *,
    session_factory: Callable[[], TSession],
    run_one_task: TaskRunner,
    all_tasks: list[OrchestratorTask] | None = None,
    agent_title_fn: Callable[[str], str] | None = None,
    close_session: Callable[[TSession], None] | None = None,
    **run_kwargs: Any,
) -> AsyncIterator[tuple[StreamKind, Any]]:
    """并行执行子任务，产出 (kind, payload)：event | result | done。"""
    task_snapshot = all_tasks or tasks
    queue: asyncio.Queue[tuple[StreamKind, Any]] = asyncio.Queue()

    async def worker(task: OrchestratorTask, route: Any) -> None:
        sess = session_factory()
        try:
            result: TaskExecutionResult | None = None
            async for kind, payload in iter_task_event_parts(
                run_one_task(sess, task=task, route=route, **run_kwargs)
            ):
                match kind:
                    case "result":
                        result = payload
                    case "event":
                        await queue.put(("event", payload))
            if result is not None:
                await queue.put(("result", result))
        except Exception:
            _logger.exception("并行子任务失败 task=%s", task.id)
            task.status = "failed"
            task.last_error = "子任务执行异常"
            await queue.put(
                (
                    "event",
                    workflow_task_event(
                        "task_failed",
                        task,
                        step_id=new_task_step_id(task.id),
                        detail=task.last_error,
                        all_tasks=task_snapshot,
                        agent_title_fn=agent_title_fn,
                    ),
                )
            )
        finally:
            if close_session is not None:
                close_session(sess)
            await queue.put(("done", None))

    async with asyncio.TaskGroup() as tg:
        workers = [tg.create_task(worker(task, route)) for task, route in zip(tasks, routes)]
        active = len(workers)
        while active > 0:
            kind, payload = await queue.get()
            match kind:
                case "done":
                    active -= 1
                case _:
                    yield kind, payload
