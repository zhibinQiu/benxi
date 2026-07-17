---
name: invoke_context_subagent
---
联网检索/深度调研的统一入口——委托子 Agent 执行联网检索。
所有需要上网查信息/调研/研究的需求统一使用此工具。
browser_digest→浏览器自动化页面取证；explore→多源并行检索；deep_research→联网检索与深度调研。

## When to use
- 所有需要联网获取信息的情况（这是唯一的联网检索入口）
- deep_research：联网检索 + 深度调研——子 Agent 自主分析意图、多关键词搜索、FireCrawl 读全文、交叉验证
- explore：内部知识多源并行检索（web-search + knowledge-search + kg），省 Token
- browser_digest：浏览器页面取证，打开指定 URL 获取页面内容与结构
- skill-dev 创建 Skill 时的纯主题检索（无浏览器操作）

## When NOT to use
- 已知 Skill 名（直接用 invoke_skill）

## Returns
- 结构化调研/检索/取证结果

## Parameters

### kind (required)
子 Agent 类型：deep_research（联网检索/深度调研）、explore（并行检索）、browser_digest（页面取证）。

### task (optional)
单子任务描述。最长 1200 字符。deep_research 传入用户的查询或调研问题。

### queries (optional)
explore 专用：2-4 个 query 并行检索。deep_research 不需要此字段，子 Agent 会自主分析意图并生成搜索关键词。
