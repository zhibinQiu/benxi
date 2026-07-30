---
name: load_uploaded_skill
---
加载上传型（发展）Skill 的 SKILL.md 全文，用于阅读指令与约定后再执行脚本或编排。

## When to use
- use 子层或 skill-dev：需要先读懂 Skill 再行动
- 确认 Skill 说明、参数与步骤

## When NOT to use
- 父编排层默认路径（父层用 invoke_context_subagent kind=use）
- 直接执行 main.py（用 run_skill_script）
- 调用已绑定内置/编排 Skill 的 action（用 invoke_skill）

## Returns
- SKILL.md 全文

## Parameters

### skill_name (required)
上传型 Skill 的 slug 名称。
