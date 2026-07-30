---
name: kg_query
---
按本体规划的路径查询知识图谱（Neo4j ABox）事实，返回结构化实体关系。
当用户问实体关系、分类归属、属性信息时使用。

## When to use
- 用户问实体关系、分类归属、属性信息
- 需要从知识图谱中查询结构化实例数据

## When NOT to use
- 需文档全文检索（用 knowledge_retrieve）
- 需搜索网络公开信息（用 web_search）
- 仅需了解类型/关系定义或查询路径说明（用 ontology_query）

## Returns
- 匹配的实体、关系及属性
- 仅查询图谱事实，不检索文档全文；SQL 计划由本体产出但不在本工具执行

## Parameters

### question (required)
查询问题。
