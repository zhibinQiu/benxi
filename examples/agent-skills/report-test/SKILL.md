---
name: report-test
description: Use when 用户要写测试报告/验收测试/测试总结 | Don't 需求分析、可研 | Output Markdown 测试报告（≥3000字，用例多时可更长）
---

# 测试报告

## 适用场景

- 系统/软件测试报告、验收测试报告、测试总结、回归测试报告
- 用户提到「测试报告」「测试方案」「验收测试」

## 工作流程

1. 确认被测对象、测试类型（功能/性能/安全等）、测试周期。
2. 有测试记录或需求文档时 `knowledge_retrieve`；标准/最佳实践可 `web_search`。
3. 按 `templates/outline.md` 输出；无真实用例数据时基于用户描述构造**示例级**用例并标注「待实测补充」，勿伪造通过率。

## 章节结构

见 `templates/outline.md`。
