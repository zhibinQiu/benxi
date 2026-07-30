---
name: update_uploaded_skill_file
---
更新上传型 Skill 包内的文本文件。更新 .py 时内容顶部必须 `import skill_runtime`，结论用 `skill_runtime.finish`。

## When to use
- skill-dev：修改 SKILL.md 或脚本内容
- 修复脚本 NameError / 逻辑错误后回写

## When NOT to use
- 新建整个 Skill（用 create_skill）
- 删除 Skill（用 delete_uploaded_skill）

## Returns
- 更新结果

## Parameters

### skill_name (required)
Skill slug。

### file_path (required)
包内相对路径（如 SKILL.md、main.py）。

### content (required)
完整新文件内容。
