"""agentkit-tools 使用示例：工具注册、Schema 生成、参数校验、结果压缩。"""

from pydantic import BaseModel, Field

from agentkit_tools import (
    ToolRegistry,
    compress_tool_result,
    validate_tool_arguments,
)


# 1. 定义参数模型
class WebSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500, description="搜索关键词")
    max_items: int = Field(default=8, ge=1, le=20, description="最大结果数")


class KnowledgeRetrieveArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    doc_ids: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=8, ge=1, le=30)


# 2. 注册工具
registry = ToolRegistry()
registry.register("web_search", "联网检索公开信息", WebSearchArgs)
registry.register(
    "knowledge_retrieve",
    "检索企业知识库",
    KnowledgeRetrieveArgs,
    categories={"knowledge"},
)

# 3. 生成 LLM function calling spec
specs = registry.build_specs()
print("Tool specs:")
for spec in specs:
    func = spec["function"]
    print(f"  - {func['name']}: {func['description']}")
    print(f"    参数: {func['parameters']}")
print()

# 4. 按分类查询
print(f"知识类工具: {registry.names_by_category('knowledge')}")
print(f"全部工具: {registry.names}")
print(f"工具数量: {len(registry)}")
print()

# 5. 校验参数（成功）
cleaned, error = validate_tool_arguments(
    registry,
    "web_search",
    {"query": "2024年AI趋势", "max_items": 5},
)
print(f"校验成功: cleaned={cleaned}, error={error}")

# 6. 校验参数（失败 - 缺少必填字段）
cleaned, error = validate_tool_arguments(
    registry,
    "web_search",
    {"max_items": 999},  # query 必填 + max_items 超出范围
)
print(f"校验失败: cleaned={cleaned}, error={error}")
print()

# 7. 压缩工具结果
raw_result = (
    '{"ok": true, "summary": "找到 5 条相关结果", '
    '"data": {"hits": [{"snippet": "AI在2024年快速发展..."}, {"snippet": "多模态成为趋势..."}], '
    '"total": 5, "page_content": "' + "x" * 5000 + '"}}'
)
compressed = compress_tool_result(raw_result, max_chars=500)
import json

parsed = json.loads(compressed)
print(f"压缩后 ok={parsed['ok']}, summary={parsed['summary']}")
print(f"压缩后 data={json.dumps(parsed.get('data'), ensure_ascii=False)}")
print(f"原始长度={len(raw_result)}, 压缩后长度={len(compressed)}")
