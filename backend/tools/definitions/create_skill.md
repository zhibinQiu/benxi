---
name: create_skill
---
创建上传型 Skill：name 为英文 slug（如 carbon-market-price）。数据/抓取类 extra_files 须含 main.py（`import skill_runtime` + `skill_runtime.finish` + 允许的 fetch API；禁 requests/open/subprocess）。

## When to use
- skill-dev：用户要求新建可复用的发展 Skill
- 已准备好 SKILL.md 正文与可选脚本文件

## When NOT to use
- 仅调用已有 Skill（用 invoke_skill / kind=use）
- 更新已有文件（用 update_uploaded_skill_file）
- 父编排层直接创建

## Returns
- 创建结果（Skill 名称与状态）

## Parameters

### name (required)
英文 slug。

### description (required)
简短能力说明。

### skill_md_body (required)
SKILL.md 正文。

### extra_files (optional)
相对路径 → 文件内容映射；数据类 Skill 通常含 main.py。

### replace_existing (optional)
同名是否覆盖，默认 false。
