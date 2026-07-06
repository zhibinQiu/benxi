# agentkit-skills

**Agent Skill** 插件框架：类型、注册表、统一 dispatch。

## 设计原则

- **Tool vs Skill**：原子 Tool 不直接暴露给 LLM；专精通过 `invoke_skill(skill, action, params)` 调用
- **零 ORM**：`SkillInvocationContext.extras` 承载宿主字段（db、user 等）
- **短路由行**：`format_skill_route_line()` 生成紧凑目录条目

## 安装

```bash
pip install agentkit-skills
```

## 注册与调用

```python
from agentkit_skills import (
    SkillDefinition,
    SkillInvocationContext,
    SkillInvocationResult,
    SkillReadiness,
    SkillSource,
    SkillToolSpec,
    invoke_skill_tool,
    register_skill,
)

async def search_handler(ctx: SkillInvocationContext, params: dict) -> SkillInvocationResult:
    query = params.get("query", "")
    # ... 宿主实现 ...
    return SkillInvocationResult(True, f"检索完成: {query}", data={"hits": []})

register_skill(SkillDefinition(
    name="web-search",
    title="网页搜索",
    description="检索公开网页",
    source=SkillSource.BUILTIN,
    readiness=SkillReadiness.READY,
    tools=(SkillToolSpec("search", "执行搜索", {"type": "object"}, search_handler),),
))

result = await invoke_skill_tool(
    SkillInvocationContext(conversation_id="c1"),
    skill_name="web-search",
    tool_name="search",
    params={"query": "hello"},
)
```

## 与 MCP 集成

外部 MCP Skill 可在宿主层将 `agentkit-mcp.McpClient.call_tool` 包装为 `SkillHandler`，
再 `register_skill` 即可纳入同一 invoke 面。

## 更多示例

见 [examples/skill_registry.py](../examples/skill_registry.py)
