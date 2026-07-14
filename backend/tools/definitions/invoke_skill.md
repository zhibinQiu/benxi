---
name: invoke_skill
---
调用已绑定的系统 Skill。文档库/技能开发/浏览器自动化等均经此入口。

## When to use
- 调用已绑定的系统 Skill（文档库 CRUD、技能开发等）
- 文档库操作：invoke_skill(document-library, call, {operation, params})
- 技能开发：invoke_skill(skill-development, call, {operation: create_skill, ...})

## When NOT to use
- 可直接用原子工具一步完成的任务（优先走原子工具）
- 运行上传型 Skill 脚本（用 run_skill_script）

## Returns
- Skill 执行结果

## Parameters

### skill_name (required)
要调用的 Skill 名称。

### action (required)
操作类型。固定为 "call"。

### params (required)
操作参数，根据目标 Skill 的要求传入。
