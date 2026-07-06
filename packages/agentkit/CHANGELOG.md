# Changelog

## 4.6.0 (2026-07-06)

- 统一全包子包版本至 4.6.0（与 doc-platform 对齐）
- 新增 agentkit-message、agentkit-tools、agentkit-interrupt 三个子包
- 各子包新增 README（含快速开始、API 概览）、CHANGELOG、py.typed 类型标记
- 各子包 `__init__.py` 统一暴露 `__version__`

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls` 元数据
- 添加 LICENSE、py.typed 标记文件
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- 聚合 agentkit-aip、agentkit-loop、agentkit-mcp、agentkit-orchestrate、agentkit-route、agentkit-skills、agentkit-subagent 七个子包
