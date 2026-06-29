---
name: report-requirements
description: Use when 用户要写需求分析报告/PRD/需求规格 | Don't 可研、测试报告、短答 | Output Markdown 需求分析长文档（≥5000字）
---

# 需求分析报告

## 适用场景

- 业务/产品需求分析、需求调研报告、需求规格说明（SRS）、PRD 级文档
- 用户提到「需求分析」「需求调研」「需求说明」

## 工作流程

1. **澄清对象**：系统/产品名称、用户角色、业务边界。
2. **收集材料**：`knowledge_retrieve`（制度、现状文档）；`web_search`（行业实践、标准）。
3. **按 `templates/outline.md` 输出**，正文 ≥5000 字，引用句末 `[n]`。
4. **需求条目**：功能需求用编号列表或表格；优先级（P0/P1/P2）须有据或标注假设。

## 章节结构

见 `templates/outline.md`。

## 类型区分

可研 → `report-feasibility`；建设方案 → `report-construction-plan`；调研 → `report-survey`。
