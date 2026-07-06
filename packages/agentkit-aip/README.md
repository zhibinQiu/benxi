# agentkit-aip

**AIP（Agent Interoperability Protocol）** 精简实现，基于 GB/Z 185 系列标准子集。

## 适用场景

- 单进程内多专精智能体 **顺序 / 并行 handoff**
- 结构化 **task_request → task_response** 消息
- 与 Loop Engineering 集成的 **complete 事件** 读写

## 安装

```bash
pip install agentkit-aip
```

## 快速开始

```python
from agentkit_aip import (
    AidConfig,
    AipSessionBus,
    HandoffBuilder,
    build_specialist_handoff_result,
)

bus = AipSessionBus(handoff_builder=HandoffBuilder(
    aid_config=AidConfig(country="cn", org_id="my-org"),
))

result = build_specialist_handoff_result(
    ok=True,
    text="检索完成，共 12 条结果",
    agent_id="research",
    session_id="sess-1",
    task_id="task-1",
    loop_state={"tool_outcome_lines": ["web-search: ok"]},
)
bus.publish("sess-1", result.message)

llm_user_msg = bus.format_task_request_for_llm(
    session_id="sess-1",
    task_id="task-2",
    target_agent_id="report",
    user_message="基于检索结果写摘要",
)
```

## 扩展 loop_state 字段

```python
from agentkit_aip import AipDataItem, HandoffBuilder

def extract_citations(state: dict) -> AipDataItem | None:
    cites = state.get("citations")
    if not cites:
        return None
    return AipDataItem(
        dataType="application/json",
        content={"citations": cites[:20]},
        label="citations",
    )

builder = HandoffBuilder(loop_state_extractors=(extract_citations,))
```

## 更多示例

见 [examples/aip_session_bus.py](../examples/aip_session_bus.py)
