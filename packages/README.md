# AgentKit

AgentKit 是一个多智能体架构的 Python 工具包，提供从路由、编排、通信到执行的全链路组件。

## 包架构

```mermaid
flowchart LR
    agentkit["agentkit (元包)"] --> aip["agentkit-aip<br/>AIP 协议"]
    agentkit --> loop["agentkit-loop<br/>Loop Engineering"]
    agentkit --> mcp["agentkit-mcp<br/>MCP 客户端"]
    agentkit --> msg["agentkit-message<br/>消息解析/过滤"]
    agentkit --> route["agentkit-route<br/>路由类型"]
    agentkit --> skills["agentkit-skills<br/>Skill 框架"]
    agentkit --> subagent["agentkit-subagent<br/>子 Agent 运行时"]
    agentkit --> tools["agentkit-tools<br/>工具注册/Schema/校验"]
    agentkit --> orchestrate["agentkit-orchestrate<br/>任务编排"]

    orchestrate --> aip
    orchestrate --> route
```

## 设计原则

- **Protocol 注入**：宿主通过 Protocol 接口注入 LLM、Tool 等依赖，库本身无平台耦合
- **渐进式采用**：子包可独立安装，按需引入
- **零 ORM/DB**：业务上下文通过 `extras` 字典传递，不依赖任何 ORM
- **面向测试**：纯函数核心，I/O 边界清晰

## 快速开始

```bash
# 安装全部组件
pip install -e packages/agentkit

# 或按需安装
pip install -e packages/agentkit-aip
pip install -e packages/agentkit-mcp
pip install -e packages/agentkit-tools
pip install -e packages/agentkit-message
```

## 子包导航

| 包 | 版本 | 依赖 | 职责 |
|----|------|------|------|
| [agentkit-aip](agentkit-aip) | 0.2.0 | pydantic | AIP 消息类型、handoff、会话总线 |
| [agentkit-loop](agentkit-loop) | 0.2.0 | 无 | Loop Engineering 动态 Prompt 组装 |
| [agentkit-mcp](agentkit-mcp) | 0.2.0 | httpx | MCP JSON-RPC 协议与客户端 |
| [agentkit-message](agentkit-message) | 0.1.0 | 无 | LLM 消息解析、内嵌工具调用提取、内容过滤 |
| [agentkit-orchestrate](agentkit-orchestrate) | 0.2.0 | agentkit-aip, agentkit-route | 多专精任务编排 |
| [agentkit-route](agentkit-route) | 0.2.0 | 无 | 路由类型与纯逻辑 |
| [agentkit-skills](agentkit-skills) | 0.2.0 | 无 | Skill 插件框架 |
| [agentkit-subagent](agentkit-subagent) | 0.2.0 | 无 | 隔离上下文子 Agent 运行时 |
| [agentkit-tools](agentkit-tools) | 0.1.0 | pydantic | 工具注册、Schema 生成、参数校验、结果压缩 |

## 示例

见 [examples/](examples/) 目录，每个子包都有独立的可运行示例。
