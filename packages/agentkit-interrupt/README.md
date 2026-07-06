# agentkit-interrupt

Agent 执行中断、Checkpoint 与恢复 —— 针对 LLM Agent Human-in-the-Loop 场景。

## 设计原则

- **无外部依赖**：核心类型 + Protocol 接口，宿主决定存储后端
- **协议解耦**：`InterruptStore` protocol —— Redis、内存、DB 均可实现
- **宿主自治**：`loop_state` / `working` 透传不解析

## 安装

```bash
pip install agentkit-interrupt
```

## 快速开始

```python
from agentkit_interrupt import (
    InterruptStore,
    save_interrupt_before_wait,
    load_interrupt,
    clear_interrupt,
)

# 宿主实现存储
class MyStore:
    """实现 InterruptStore protocol"""

    def save(self, state, ttl_seconds=86400): ...
    def load(self, checkpoint_id): ...
    def clear(self, checkpoint_id): ...
    def list_for_user(self, user_id): ...

store = MyStore()

# 等待用户前保存状态
cp_id = save_interrupt_before_wait(
    store,
    user_id="user-1",
    phase="awaiting_confirmation",
    loop_state={"tools": [...]},
    working=[{"role": "assistant", "content": "..."}],
    pending_data={"tool_name": "send_email"},
)
```

## License

MIT
