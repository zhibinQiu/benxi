---
name: schedule_browser_workflow
---
在指定未来时间自动回放已保存的浏览器 RPA Skill。

## When to use
- 「明天 X 点自动跑这个流程」「定时执行浏览器自动化」
- 已有 browser_save_workflow 保存的 Skill

## When NOT to use
- 需要立即回放（用 browser_replay_workflow）
- 普通文字提醒（用 schedule_notification）
- Skill 不存在

## Returns
- 定时任务 ID 与计划执行时间

## Parameters

### skill_name (required)
已保存的 RPA Skill 名称。

### scheduled_at (required)
ISO 8601 绝对时间（含时区），如 2026-07-06T12:00:00+08:00。

### parameters (optional)
回放时传入的参数键值对。
