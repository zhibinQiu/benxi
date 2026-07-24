"""对话工作时记忆（Harness）— 与 MEMORY.md 系统记忆分离。

标准化接口：
  - ``record``：通用一步
  - ``observe_route`` / ``observe_stream_event``：路由与执行监控
  - ``add_failure_receipt``：失败事实回执
  - ``format_prompt_block``：注入调度上下文

业务偏好不写在本模块；只记录过程事实。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

WORKING_MEMORY_MARKER = "【工作时记忆】"
_HINT = (
    "以上为本轮 harness 轨迹（非 MEMORY.md）；"
    "回交调度须据此重规划；勿编造轨迹中未出现的工具结果。"
)

_WATCH_PHASES = frozenset(
    {"agent_thought", "agent_thinking", "tool_start", "tool_done", "tool_error", "tool_result"}
)


@dataclass
class WorkingMemory:
    steps: list[str] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)

    def record(self, title: str, detail: str = "", *, agent_id: str = "") -> None:
        title = (title or "").strip()
        detail = " ".join((detail or "").split()).strip()
        agent = (agent_id or "").strip()
        if not title and not detail:
            return
        head = f"[{agent}] {title}" if agent else title
        line = f"- {head}：{detail}" if detail else f"- {head}"
        if line not in self.steps:
            self.steps.append(line)

    # 兼容旧调用名
    add = record

    def observe_route(self, *, source: str, agent_id: str, reason: str = "") -> None:
        detail = f"source={(source or 'unknown').strip()}"
        if reason:
            detail = f"{detail}；{reason.strip()[:160]}"
        self.record("路由", detail, agent_id=agent_id)

    def observe_stream_event(self, event: dict[str, Any] | None) -> None:
        if not isinstance(event, dict):
            return
        et = str(event.get("type") or "").strip()
        if et == "workflow":
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            self._observe_workflow(data)
            return
        if et != "tool_result":
            return
        name = str(event.get("tool") or event.get("name") or "tool").strip()
        ok = event.get("ok")
        summary = str(event.get("summary") or event.get("detail") or "").strip()[:160]
        status = "ok" if ok is not False else "failed"
        key = f"tr:{name}:{status}:{summary[:40]}"
        if not self._mark(key):
            return
        self.record(
            f"工具/{status}",
            f"{name}" + (f" → {summary}" if summary else ""),
            agent_id=str(event.get("agent_id") or ""),
        )

    def _observe_workflow(self, data: dict[str, Any]) -> None:
        phase = str(data.get("phase") or "").strip()
        if phase and phase not in _WATCH_PHASES:
            return
        title = str(data.get("title") or phase or "步骤").strip()
        detail = str(data.get("detail") or "").strip()[:200]
        tool = str(data.get("tool") or "").strip()
        status = str(data.get("status") or "").strip()
        agent_id = str(data.get("agent_id") or "").strip()
        key = f"wf:{agent_id}:{title}:{tool}:{status}:{detail[:48]}"
        if not self._mark(key):
            return
        bits = [b for b in (tool, status, detail) if b]
        self.record(title, "；".join(bits), agent_id=agent_id)

    def _mark(self, key: str) -> bool:
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def add_failure_receipt(
        self,
        *,
        agent_id: str,
        agent_title: str,
        loop_state: dict | None = None,
        reply: str = "",
    ) -> str:
        state = dict(loop_state or {})
        facts: list[str] = []
        outcomes = [
            str(x).strip()
            for x in (state.get("tool_outcome_lines") or [])
            if str(x).strip()
        ]
        if outcomes:
            facts.append("工具摘要：" + "；".join(outcomes[:6]))
        executed = list(state.get("executed_tool_calls") or [])
        if executed:
            names = [
                (
                    f"{str(rec.get('tool_name') or 'tool').strip()}"
                    + (
                        f"→{str(rec.get('summary') or '').strip()}"
                        if str(rec.get("summary") or "").strip()
                        else ""
                    )
                )
                for rec in executed[-8:]
            ]
            facts.append("已调用：" + "；".join(names))
        elif not outcomes:
            facts.append("无有效工具证据")
        reply_s = " ".join((reply or "").split()).strip()
        if reply_s:
            facts.append(f"专精自述（勿当事实）：{reply_s[:240]}")
        receipt = f"{agent_title or agent_id} 未交付。" + (
            " " + " ".join(facts) if facts else ""
        )
        self.record("失败回执", receipt, agent_id=agent_id)
        return receipt

    def format_prompt_block(self, *, max_chars: int = 3200) -> str:
        if not self.steps:
            return ""
        body = "\n".join(self.steps)
        text = f"{WORKING_MEMORY_MARKER}\n本轮轨迹：\n{body}\n\n{_HINT}"
        return text if len(text) <= max_chars else text[: max_chars - 1] + "…"
