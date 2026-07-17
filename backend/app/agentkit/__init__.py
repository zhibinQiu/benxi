"""AgentKit — 智能体工具箱。

AgentKit 是本析平台智能体系统的核心工具箱，按职责分层：

- **aip**：智能体互操作协议（Agent Interoperability Protocol），
  定义专精智能体之间的消息交换、会话管理和移交（handoff）机制。
- **config**：通用配置热加载器（MarkdownConfigLoader），
  支持按 mtime 增量刷新的 MD/YAML 配置读取。
- **interrupt**：人机交互（Human-in-the-Loop）支持，
  管理暂停点、用户确认请求和中断生命周期。
- **loop**：工具循环（Tool Loop）核心，
  实现 LLM 多轮工具调用的六相循环引擎。
- **mcp**：MCP（Model Context Protocol）客户端，
  用于连接外部 MCP 服务获取额外工具。
- **message**：消息处理，
  包括消息解析、过滤和对话上下文管理。
- **orchestrate**：编排层，
  管理任务的分发、并行执行和结果验证。
- **route**：路由层，
  基于信号检测和评分决定任务分配到哪个智能体。
- **skills**：技能层，
  管理 Skill 的定义、注册、搜索和执行。
- **subagent**：子智能体，
  提供隔离上下文的多轮研究型子 Agent 运行时。
- **tools**：工具层，
  提供工具参数 Schema 定义、校验、压缩和分层发现（ToolVisibility）。

详细设计理念见 docs/zh/agent-philosophy.md 与 AGENTS.md。
"""

from app import __version__  # noqa: F401 — single source of truth
