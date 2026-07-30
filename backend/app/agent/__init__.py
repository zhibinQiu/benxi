"""可抽离库：智能体运行时（``app.agent``）。

职责：路由、编排/DAG、工具循环、Skill 泛型、子智能体、AIP、工具 Schema/校验。
禁止依赖：``app.services`` / ``app.models`` / ``app.config`` / ``app.database`` / ``app.api``。
宿主经 Protocol / 回调注入存储、LLM、取消钩子等。

子包：
- aip：智能体互操作（消息、会话、handoff）
- config：Markdown/YAML 配置热加载
- interrupt：人机确认与中断生命周期
- loop：LLM 多轮工具调用循环
- mcp：外部 MCP 工具客户端
- message：消息解析与对话上下文
- orchestrate：任务 DAG / 并行编排
- route：信号检测与智能体路由
- skills：Skill 定义、注册与执行（平台 ORM Skill 见 ``app.skills``）
- subagent：隔离上下文的研究型子智能体
- tools：参数 Schema、校验与结果压缩（全局 Tool 注册见 ``app.tools``）
"""

from app import __version__  # noqa: F401 — single source of truth
