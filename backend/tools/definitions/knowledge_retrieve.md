---
name: knowledge_retrieve
---
检索企业文档库，返回与 query 相关的文档片段。
当用户问企业知识、文档内容时使用。

## When to use
- 用户问企业知识库、文档内容、平台资料
- 需要从已索引文档中检索相关信息

## When NOT to use
- 需搜索公开网络信息（用 web_search）
- 需查询实体关系图（用 kg_query）
- 用户已指定具体文档（用 read_document_content）

## Returns
- 匹配文档的标题、片段及来源
- 仅检索已索引到知识库的文档内容，不检索外部网络

## Parameters

### query (required)
搜索关键词。

### doc_ids (optional)
限定检索的文档 ID 列表。默认不限定。

### limit (optional)
最大返回片段数。默认 8，最大 30。
