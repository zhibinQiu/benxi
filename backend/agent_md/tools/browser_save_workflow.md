---
name: browser_save_workflow
---
将当前会话中已录制的浏览器操作保存为可回放的 RPA Skill，供日后 browser_replay_workflow / schedule_browser_workflow 使用。

## When to use
- 已完成一组可复用的浏览器步骤，需要固化为 Skill
- 用户要求「保存这段操作为自动化流程」

## When NOT to use
- 尚未执行任何可录制步骤
- 只需立刻回放已有 Skill（用 browser_replay_workflow）
- 创建通用上传型 Skill（用 create_skill，属 skill-dev）

## Returns
- 保存后的 Skill 名称与状态

## Parameters

### name (required)
RPA Skill 名称（英文 slug 或可读名）。

### description (optional)
Skill 说明。

### parameters (optional)
可参数化的变量名列表，回放时由调用方传入。

### replace_existing (optional)
同名已存在时是否覆盖。默认 true。
