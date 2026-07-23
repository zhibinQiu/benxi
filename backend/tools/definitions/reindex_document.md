---
name: reindex_document
---
重建指定文档的解析/向量索引；可选重新同步到知识库。

## When to use
- 文档内容已变但检索结果仍旧
- 索引异常、分片错误需要重建

## When NOT to use
- 首次简单同步（可先试 sync_document_knowledge）
- 未指定具体文档

## Returns
- 重建索引结果

## Parameters

### document_id (required)
文档 ID。

### parser_id (optional)
指定解析器；通常留空用默认。

### resync (optional)
重建后是否再同步知识库。默认 false。
