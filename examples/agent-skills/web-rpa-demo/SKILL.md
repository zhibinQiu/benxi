---
name: web-rpa-demo
description: 浏览器 RPA 录制产物示例（workflow.json 格式对照）；实际流程由本析智能体内置 browser_* 工具对话探索后 browser_save_workflow 生成。
---

# 浏览器 RPA 流程示例（录制产物对照）

本包**不是**可执行脚本 Skill，而是展示 `browser_save_workflow` 生成的 `workflow.json` 结构，供管理员与开发者对照。

## 系统能力 vs 本示例

| 层级 | 说明 |
|------|------|
| **内置 `browser_*` 工具** | 平台 RPA 能力：对话中打开页面、snapshot、点击、填表、截图 |
| **`browser_save_workflow`** | 将探索过程固化为 upload Skill |
| **本示例包** | 静态 workflow.json 样例，用于文档与测试对照 |

## workflow.json 结构

```json
{
  "version": 1,
  "recorded_at": "2026-06-22T12:00:00+00:00",
  "parameters": ["url", "custname"],
  "steps": [
    {"action": "navigate", "url": "https://httpbin.org/forms/post"},
    {"action": "type", "ref": "e2", "text": "{{custname}}"},
    {"action": "click", "ref": "e8"},
    {"action": "screenshot", "full_page": false}
  ]
}
```

## 典型对话（启用 AGENT_BROWSER_ENABLED 后）

1. 「打开 https://httpbin.org/forms/post 并填写客户名 Test，提交后截图」  
2. 小析依次调用 `browser_navigate` → `browser_snapshot` → `browser_type` → `browser_click` → `browser_screenshot`  
3. 「把这个流程保存为 httpbin-form-demo」→ `browser_save_workflow`

## 与 web-page-insight 的分工

- **web-page-insight**：只读公开页、HTTP 拉取、无 JS 交互  
- **browser_* **：SPA、表单、登录、截图、流程录制

详见 [浏览器 RPA 实现说明](../../docs/zh/implementation/browser-rpa-implementation.md)。
