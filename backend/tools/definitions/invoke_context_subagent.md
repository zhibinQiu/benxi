---
name: invoke_context_subagent
---
委托子 Agent 调用系统 Skill 或原子工具。
browser_digest→浏览器自动化页面取证；explore→多源并行检索；deep_research→深度联网调研。

## When to use
- explore：多源并行检索（web-search + knowledge-search + kg-palantir），省 Token
- deep_research：深度联网研究——子 Agent 自主分析意图、多关键词搜索、FireCrawl 读全文、交叉验证
- browser_digest：浏览器页面取证，打开指定 URL 获取页面内容与结构
- skill-dev 创建 Skill 时的纯主题检索（无浏览器操作）

## When NOT to use
- 单次简单搜索（直接用 web_search）
- 已知 Skill 名（直接用 invoke_skill）

## Returns
- 结构化调研/检索/取证结果

## Parameters

### kind (required)
子 Agent 类型：explore（并行检索）、browser_digest（页面取证）、deep_research（深度研究）。

### task (optional)
单子任务描述。最长 1200 字符。

### queries (optional)
explore 专用：2-4 个 query 并行检索。deep_research 不需要此字段。
