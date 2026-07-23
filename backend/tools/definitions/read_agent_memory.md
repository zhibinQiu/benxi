---
name: read_agent_memory
---
读取当前用户的 MEMORY.md 长期记忆全文。

## When to use
- 需要了解用户偏好、角色设定、长期约定
- 用户问「你还记得我说过什么」

## When NOT to use
- 查询平台业务数据（用对应业务工具）
- 写入记忆（用 append_agent_memory）

## Returns
- MEMORY.md 文本内容
