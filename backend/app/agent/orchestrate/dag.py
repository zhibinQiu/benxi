"""Task DAG — 带依赖的子任务图（纯函数，零平台依赖）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent.orchestrate.types import OrchestratorTask

NodeStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class TaskNode:
    """DAG 节点：专精 Agent 上的一个可调度子任务。"""

    id: str
    title: str
    agent_id: str
    goal: str = ""
    depends_on: tuple[str, ...] = ()
    status: NodeStatus = "pending"
    reply: str = ""
    reason: str = ""
    last_error: str = ""

    def to_orchestrator_task(self) -> OrchestratorTask:
        return OrchestratorTask(
            id=self.id,
            title=self.title,
            agent_id=self.agent_id,
            reason=self.reason or self.goal,
            status=self.status,
            summary=(self.reply or self.last_error)[:200],
            last_error=self.last_error,
        )


@dataclass
class TaskDAG:
    """有向无环任务图；节点 id 唯一。"""

    nodes: list[TaskNode] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._index = {n.id: n for n in self.nodes}
        self.validate()

    def validate(self) -> None:
        """校验 id 唯一、依赖存在、无环；失败抛 ValueError。"""
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task node id")
        id_set = set(ids)
        for n in self.nodes:
            for dep in n.depends_on:
                if dep not in id_set:
                    raise ValueError(f"unknown dependency {dep!r} on node {n.id!r}")
                if dep == n.id:
                    raise ValueError(f"self-dependency on node {n.id!r}")
        if self._has_cycle():
            raise ValueError("task DAG contains a cycle")

    def _has_cycle(self) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(nid: str) -> bool:
            if nid in visited:
                return False
            if nid in visiting:
                return True
            visiting.add(nid)
            node = self._index[nid]
            for dep in node.depends_on:
                if dfs(dep):
                    return True
            visiting.remove(nid)
            visited.add(nid)
            return False

        return any(dfs(n.id) for n in self.nodes)

    def get(self, node_id: str) -> TaskNode | None:
        return self._index.get(node_id)

    def ready_nodes(self, *, limit: int | None = None) -> list[TaskNode]:
        """依赖均已 done 且自身 pending 的节点（稳定按 nodes 顺序）。"""
        ready: list[TaskNode] = []
        for n in self.nodes:
            if n.status != "pending":
                continue
            if not all(self._index[d].status == "done" for d in n.depends_on):
                continue
            ready.append(n)
            if limit is not None and len(ready) >= limit:
                break
        return ready

    def blocked_by_failure(self) -> list[TaskNode]:
        """因上游 failed 而无法推进的 pending 节点。"""
        out: list[TaskNode] = []
        for n in self.nodes:
            if n.status != "pending":
                continue
            if any(self._index[d].status == "failed" for d in n.depends_on):
                out.append(n)
        return out

    def mark_running(self, node_id: str) -> None:
        n = self._index[node_id]
        n.status = "running"

    def mark_done(self, node_id: str, *, reply: str = "") -> None:
        n = self._index[node_id]
        n.status = "done"
        n.reply = (reply or "").strip()
        n.last_error = ""

    def mark_failed(self, node_id: str, *, error: str = "") -> None:
        n = self._index[node_id]
        n.status = "failed"
        n.last_error = (error or "").strip()

    def all_terminal(self) -> bool:
        return all(n.status in ("done", "failed") for n in self.nodes)

    def is_complete_success(self) -> bool:
        return bool(self.nodes) and all(n.status == "done" for n in self.nodes)

    def orchestrator_tasks(self) -> list[OrchestratorTask]:
        return [n.to_orchestrator_task() for n in self.nodes]

    def edges(self) -> list[dict[str, str]]:
        return [
            {"from": dep, "to": n.id}
            for n in self.nodes
            for dep in n.depends_on
        ]

    def summary_chain(self) -> str:
        """可读摘要：同波次用 ∥，波次之间用 →。"""
        if not self.nodes:
            return ""
        remaining = {n.id for n in self.nodes}
        waves: list[list[str]] = []
        done: set[str] = set()
        while remaining:
            wave = [
                n.id
                for n in self.nodes
                if n.id in remaining and all(d in done for d in n.depends_on)
            ]
            if not wave:
                # 环或坏依赖：退回扁平标题
                return " → ".join(n.title for n in self.nodes)
            waves.append([self._index[i].title for i in wave])
            for i in wave:
                remaining.discard(i)
                done.add(i)
        return " → ".join("∥".join(titles) if len(titles) > 1 else titles[0] for titles in waves)

    def parent_replies(self, node_id: str) -> list[tuple[str, str]]:
        """返回 (parent_title, reply) 列表，供下游上下文注入。"""
        n = self._index[node_id]
        out: list[tuple[str, str]] = []
        for dep in n.depends_on:
            p = self._index[dep]
            reply = (p.reply or "").strip()
            if reply:
                out.append((p.title, reply))
        return out

    def done_results(self) -> list[dict[str, Any]]:
        return [
            {
                "id": n.id,
                "title": n.title,
                "agent_id": n.agent_id,
                "goal": n.goal,
                "reply": n.reply,
                "status": n.status,
            }
            for n in self.nodes
            if n.status == "done" and (n.reply or "").strip()
        ]


def build_task_dag(nodes: list[TaskNode]) -> TaskDAG:
    """工厂：校验并返回 TaskDAG。"""
    return TaskDAG(nodes=list(nodes))
