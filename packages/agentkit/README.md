# agentkit — AgentKit 元包

> 一次安装全部多智能体组件

[![GitHub](https://img.shields.io/badge/GitHub-zhibinQiu/Agentkit-181717?logo=github)](https://github.com/zhibinQiu/Agentkit)
[![PyPI](https://img.shields.io/badge/PyPI-agentkit-blue)](https://pypi.org/project/agentkit/)
[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](../../LICENSE)

`agentkit` 是 AgentKit 的元包（meta package），安装它即可一次性安装全部 11 个子包。适合需要完整多智能体能力的项目。

- **GitHub**: [https://github.com/zhibinQiu/Agentkit](https://github.com/zhibinQiu/Agentkit)
- **完整文档**: [packages/README.md](../README.md)

## 安装

```bash
pip install -e packages/agentkit
```

## 包含的子包（11 个）

| 包 | 版本 | 用途 |
|----|------|------|
| agentkit | 4.6.0 | 元包 — 一次安装全部组件 |
| agentkit-aip | 4.6.0 | AIP 消息类型、handoff、会话总线 |
| agentkit-loop | 4.6.0 | Loop Engineering 动态 Prompt 组装 |
| agentkit-mcp | 4.6.0 | MCP JSON-RPC 协议与客户端 |
| agentkit-message | 4.6.0 | LLM 消息解析、内嵌工具调用提取、内容过滤 |
| agentkit-orchestrate | 4.6.0 | 多专精任务编排 |
| agentkit-route | 4.6.0 | 路由类型与纯逻辑 |
| agentkit-skills | 4.6.0 | Skill 插件框架 |
| agentkit-subagent | 4.6.0 | 隔离上下文子 Agent 运行时 |
| agentkit-tools | 4.6.0 | 工具注册、Schema 生成、参数校验、结果压缩 |
| agentkit-interrupt | 4.6.0 | 中断与 Checkpoint、HITL 响应管理 |

## 子包单独安装

```bash
pip install -e packages/agentkit-aip
pip install -e packages/agentkit-loop
pip install -e packages/agentkit-mcp
pip install -e packages/agentkit-message
pip install -e packages/agentkit-orchestrate
pip install -e packages/agentkit-route
pip install -e packages/agentkit-skills
pip install -e packages/agentkit-subagent
pip install -e packages/agentkit-tools
pip install -e packages/agentkit-interrupt
```

## 许可

[AGPL v3](../../LICENSE)
