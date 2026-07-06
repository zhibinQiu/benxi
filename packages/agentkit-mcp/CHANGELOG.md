# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 新增 `__init__.py` 中 `__version__` 暴露
- 完善 README：快速开始、协议层独立使用、token 压缩示例
- 新增 `platform_server.py` 平台 MCP 服务端支持
- 新增 `external_registry.py` 外部 MCP Skill 注册支持
- 新增 `skill_builder.py` MCP Skill 构建器

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls`、LICENSE、py.typed
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- MCP JSON-RPC 2.0 协议常量与响应解析（build_jsonrpc_request、parse_jsonrpc_response）
- HTTP/SSE 异步客户端（McpClient、McpClientConfig）
- 工具结果摘要压缩（summarize_mcp_tool_result）
