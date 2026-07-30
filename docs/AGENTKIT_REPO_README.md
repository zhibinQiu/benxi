# 本析智能体运行时（`app.agent`）

> 多智能体核心已内置于本析后端：`backend/app/agent/`。  
> 架构与哲学：[Agent 架构](zh/agent-architecture.md) · [设计哲学](zh/agent-philosophy.md)

---

## 职责边界

可抽离库：路由、编排/DAG、loop 终稿契约、Skill 泛型、子智能体、AIP、工具 Schema/校验。  
**禁止**依赖 `app.services` / `models` / `config` / `database` / `api`；宿主经 Protocol / 回调注入 LLM、存储等。

六相主循环仍在宿主：`backend/app/services/agent_tool_loop.py`。

## 子包

| 子包 | 说明 |
|------|------|
| `aip` | 消息、handoff、会话总线、多 hop 合并 |
| `route` | 路由计划纯逻辑 |
| `orchestrate` | TaskDAG、并行波次、assist、验收 |
| `loop` | 计划类型、exit prompt、`LoopState` |
| `subagent` | 隔离上下文子 Agent（search/use/execute） |
| `skills` | Skill 注册/执行泛型（平台 ORM 见 `app.skills`） |
| `tools` | Schema、校验、结果压缩（全局注册见 `app.tools`） |
| `mcp` | MCP JSON-RPC 客户端 |
| `interrupt` | HITL 与 checkpoint 协议 |
| `message` | 消息解析、过滤、裁剪 |
| `config` | Markdown/YAML 热加载 |

## 业务配置

指令与路由偏好：`backend/agent_md/`（agents / routing / tools / skills）。

## 设计原则

- Protocol 注入，库与平台解耦  
- 调度不直执原子工具；执行下沉子智能体或专精  
- 业务偏好写在 MD，代码不做领域硬编码  
- 终稿基于观测证据，禁止编造  

## 许可

[AGPL v3](../LICENSE)
