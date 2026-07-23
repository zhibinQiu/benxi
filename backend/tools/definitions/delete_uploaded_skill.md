---
name: delete_uploaded_skill
---
删除上传型 Skill 包。

## When to use
- skill-dev：用户明确要求删除某发展 Skill

## When NOT to use
- 仅禁用或修改文件（用 update_uploaded_skill_file）
- 删除内置/非上传 Skill（不适用）

## Returns
- 删除结果

## Parameters

### skill_name (required)
Skill slug。
