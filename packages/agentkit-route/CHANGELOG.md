# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 新增 `__init__.py` 中 `__version__` 暴露
- 完善 README：职责边界表、快速开始与路由模式推断
- 新增 `scoring.py` 路由分数过滤
- 新增 `signals.py` 信号检测协议（SignalDetector、CompoundDetector）

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls`、LICENSE、py.typed
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- 路由类型（AgentRoute、AgentRoutePlan、RouteMode）
- 模式推断（infer_route_mode）
- Handoff 上限截断（cap_routes）
- 路由计划构建（build_route_plan）
- 分数过滤（filter_routes_by_agent_scores）
- 信号检测协议（SignalDetector、CompoundDetector）
