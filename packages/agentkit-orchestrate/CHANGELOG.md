# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 新增 `__init__.py` 中 `__version__` 暴露
- 完善 README：职责边界表、快速开始与宿主职责说明
- 新增 `events.py` / `event_parse.py` workflow 事件支持
- 新增 `document.py` 文档上下文提取
- 新增 `messages.py` 编排消息模板（重试、协助、升级）
- 新增 `assessment.py` 用户诉求规则验收与全局轮反思

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls`、LICENSE、py.typed
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- 编排领域模型（OrchestratorTask、TaskExecutionResult）
- 路由 → 任务清单（tasks_from_routes）
- 子任务规则验收（verify_task_result、VerifyRules、VerifyHooks）
- 调度协助与 skill-dev 升级（AssistRules）
- 用户诉求规则验收（assess_answer_coverage_rule）
- Workflow 事件构造（workflow_plan_tasks、workflow_task_event）
- 并行 worker 事件合并（iter_parallel_task_events）
- 编排消息模板（重试、协助、升级）
