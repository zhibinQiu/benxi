---
name: list_mounted_folders
---
列出当前 Agent 已挂载的知识库文件夹列表。每个文件夹包含知识库名称、文件夹名称和文档数量。

## When to use
- 想了解当前 Agent 可以检索哪些知识库文件夹
- 用户问"你能看到哪些知识库文件夹"
- 在执行 knowledge_folder_search 前了解检索范围

## When NOT to use
- 查询具体文档内容（用 knowledge_retrieve 或 knowledge_folder_search）
- 需要搜索所有可访问文档（用 knowledge_retrieve）

## Returns
- 挂载的文件夹列表（含知识库名称、文件夹名、文档数量）

## Parameters

无参数。
