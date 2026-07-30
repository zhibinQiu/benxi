---
name: knowledge_folder_search
---
检索当前 Agent 已挂载知识库文件夹中的文档，返回与 query 相关的文档片段。
当 Agent 已经挂载了知识库文件夹，且用户问题涉及这些文件夹内的知识时使用。

## When to use
- Agent 已配置知识库文件夹挂载，用户问挂载文件夹内的文档内容
- 需要在已挂载的知识范围内检索信息

## When NOT to use
- 用户未配置任何文件夹挂载（用 knowledge_retrieve）
- 需要搜索公开网络信息（用 web_search）
- 需查询实体关系图（用 kg_query）
- 用户已指定具体文档（用 read_document_content）

## Returns
- 匹配文档的标题、片段及来源
- 仅检索已挂载文件夹内已索引的文档内容

## Parameters

### query (required)
搜索关键词。

### limit (optional)
最大返回片段数。默认 8，最大 30。
