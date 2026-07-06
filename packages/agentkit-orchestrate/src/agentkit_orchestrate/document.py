"""Handoff 文档上下文提取。"""

from __future__ import annotations

from typing import Any

from agentkit_orchestrate.types import TaskExecutionResult


def _handoff_from_complete(complete: dict[str, Any] | None) -> Any:
    """从 complete 事件提取 handoff（惰性导入 AIP）。"""
    if not complete:
        return None
    from agentkit_aip.messaging import handoff_from_complete as _hfc

    return _hfc(complete)


def extract_document_contexts_from_results(
    results: list[TaskExecutionResult],
) -> list[dict]:
    contexts: list[dict] = []
    for item in results:
        message = item.aip_handoff or _handoff_from_complete(item.complete)
        if message is None:
            continue
        for data_item in message.dataItems:
            if data_item.label == "document_context" and isinstance(data_item.content, dict):
                contexts.append(data_item.content)
    return contexts
