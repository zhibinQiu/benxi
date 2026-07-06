# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 初始独立发布
- 声明式工具注册（ToolRegistry、ToolDef）
- Pydantic Model → JSON Schema → OpenAI function calling 格式（build_function_tool_spec）
- 运行时参数校验（validate_tool_arguments、format_validation_error）
- Tool JSON 结果压缩（compress_tool_result）
