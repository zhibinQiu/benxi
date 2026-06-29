---
name: report-construction-plan
description: Use when 用户要写建设方案/实施方案/技术方案报告 | Don't 可研全文、纯流程图 | Output Markdown 建设方案长文（≥5000字）
---

# 建设方案报告

## 适用场景

- 信息化建设方案、工程/项目建设方案、实施方案、技术总体方案
- 用户提到「建设方案」「实施方案」「技术方案」

## 工作流程

1. 确认建设目标、现状基线、约束（工期、预算、合规）。
2. `knowledge_retrieve` + `web_search` 收集政策、标准、同类案例。
3. 遵循 `templates/outline.md`，输出 ≥5000 字 Markdown，引用 `[n]`。
4. **图文并茂**：须含总体架构 Mermaid 图、实施阶段表格或流程图，至少 2 张资源/投资/里程碑类表格。
5. **充实度**：「总体架构与建设内容」「实施路径」须重点扩写，每小节至少 3 段，禁止口号式空话与重复凑字。

## 章节结构

见 `templates/outline.md`。
