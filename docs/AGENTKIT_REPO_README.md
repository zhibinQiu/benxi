# AgentKit

> 多智能体架构的 Python 工具包 — 路由 · 编排 · 通信 · 执行

[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)]()

**AgentKit** 是一个多智能体架构的 Python 工具包，提供从路由、编排、通信到执行的全链路组件。

- **GitHub**: [https://github.com/zhibinQiu/Agentkit](https://github.com/zhibinQiu/Agentkit)
- **本析平台**: [https://github.com/zhibinQiu/benxi](https://github.com/zhibinQiu/benxi)

---

## 子包一览

| 包 | 版本 | 说明 |
|----|------|------|
| agentkit-aip | 4.6.0 | AIP 消息类型、handoff、会话总线 |
| agentkit-loop | 4.6.0 | Loop Engineering 动态 Prompt 组装 |
| agentkit-mcp | 4.6.0 | MCP JSON-RPC 协议与客户端 |
| agentkit-message | 4.6.0 | LLM 消息解析、内嵌工具调用提取 |
| agentkit-orchestrate | 4.6.0 | 多专精任务编排 |
| agentkit-route | 4.6.0 | 路由类型与纯逻辑 |
| agentkit-skills | 4.6.0 | Skill 插件框架 |
| agentkit-subagent | 4.6.0 | 子 Agent 运行时 |
| agentkit-tools | 4.6.0 | 工具注册、Schema 生成、校验 |
| agentkit-interrupt | 4.6.0 | 中断与 Checkpoint、HITL |

## 设计原则

- **Protocol 注入**：宿主通过 Protocol 接口注入 LLM、Tool 等依赖，无平台耦合
- **渐进式采用**：子包可独立安装，按需引入
- **零 ORM/DB**：业务上下文通过 `extras` 字典传递
- **面向测试**：纯函数核心，I/O 边界清晰

## 安装

```bash
pip install agentkit           # 全部组件
pip install agentkit-aip       # 仅 AIP 协议
pip install agentkit-mcp       # 仅 MCP 客户端
```

## 许可

[AGPL v3](LICENSE)
