---
name: request_orchestrator_assist
---
本域无法完成时向调度智能体反馈，由调度层协调其他专精协助后再交还你续办。

## When to use
- 专精 Agent 遇到本域无法完成的任务
- 需要其他专精 Agent 提供数据或操作结果
- 当前任务超出本域能力范围

## When NOT to use
- 可直接用已有工具完成
- 需要直接向用户提问（用 ask_user_choice）

## Returns
- 调度协助结果

## Parameters

### reason (required)
为何需要调度协助，简要说明缺乏什么能力或数据。

### needed_from (optional)
需要哪个 Agent/能力提供协助。

### suggested_agent_id (optional)
建议的协助专精 ID。
