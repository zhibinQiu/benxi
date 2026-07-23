---
name: browser_run_task
---
用自然语言描述驱动浏览器自主完成多步任务（内部会导航/snapshot/交互）。适合端到端探索，精细控制时改用原子 navigate/snapshot/click。

## When to use
- 「打开某某网站并完成某操作」类自然语言任务
- 步骤较多、不必逐步手工编排时

## When NOT to use
- 只需读公开 URL 正文（用 fetch_url_content）
- 需要逐步可控的精确点击（用 navigate + snapshot + click）
- 已有保存好的 RPA（用 browser_replay_workflow）

## Returns
- 任务执行结论与关键步骤摘要

## Parameters

### task (required)
自然语言任务描述。

### start_url (optional)
起始 URL；不传则在当前会话页上继续，或由任务自行决定。

### max_steps (optional)
最大自动步数，1–40；过大可能耗时更长。
