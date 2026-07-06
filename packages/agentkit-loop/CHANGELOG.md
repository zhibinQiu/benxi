# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 新增 `__init__.py` 中 `__version__` 暴露
- 完善 README：六相循环映射说明、Loop 与 Prompt Engineering 对比表
- 补充 `plan.py` 模块（AgentExecutionPlan / AgentToolPlan）
- 新增 `build_turn_tools_context` 工具上下文构建

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls`、LICENSE、py.typed
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- Loop Engineering 核心类型（LoopEvidence、LoopExitRequest）
- 证据提供者协议（LoopEvidenceProvider）
- 动态 Prompt 组装（build_loop_exit_prompt_messages）
- 默认证据提供者工厂（dict_evidence_provider）
- 规划与工具上下文构建（build_agent_instruction_from_plan、build_turn_tools_context）
- Agent 执行规划类型（AgentExecutionPlan、AgentToolPlan）
