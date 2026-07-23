---
name: browser_replay_workflow
---
立即回放已保存的浏览器 RPA Skill（由 browser_save_workflow 创建）。

## When to use
- 用户要求执行已保存的自动化流程
- 已知 skill_name，需要马上跑一遍

## When NOT to use
- Skill 尚未保存（先操作并 browser_save_workflow）
- 需要在未来某时刻执行（用 schedule_browser_workflow）
- 一次性自然语言探索任务（用 browser_run_task）

## Returns
- 回放执行结果摘要

## Parameters

### skill_name (required)
已保存的 RPA Skill 名称。

### parameters (optional)
键值对，填充 Skill 定义的参数占位。
