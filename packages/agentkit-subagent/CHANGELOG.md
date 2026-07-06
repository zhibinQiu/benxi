# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 新增 `__init__.py` 中 `__version__` 暴露
- 完善 README：快速开始、API 概览表、宿主注入接口说明
- 新增 `explore.py` 并行 explore 支持
- 新增 `loop.py` 隔离 tool 循环支持
- 新增 `context.py` loop_state 上下文工具

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls`、LICENSE、py.typed
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- 子 Agent 运行时类型（SubagentRuntime、SubagentKindConfig）
- 配置 Builder（SubagentConfig）
- 统一入口（execute_subagent）
- 并行 explore（parallel_explore_queries）
- 隔离 tool 循环（run_subagent_tool_loop）
- loop_state 上下文工具（child_state_from_parent、merge_child_into_parent）
