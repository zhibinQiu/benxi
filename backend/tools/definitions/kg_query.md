---
name: kg_query
---
查询本体知识图谱，返回结构化实体关系。
当用户问实体关系、分类归属、属性信息时使用。

## When to use
- 用户问实体关系、分类归属、属性信息
- 需要从知识图谱中查询结构化数据

## When NOT to use
- 需文档全文检索（用 knowledge_retrieve）
- 需搜索网络公开信息（用 web_search）

## Returns
- 匹配的实体、关系及属性
- 仅查询图谱数据，不检索文档全文

## Parameters

### question (required)
查询问题。
