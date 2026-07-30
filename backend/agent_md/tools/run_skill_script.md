---
name: run_skill_script
---
执行含 main.py 的发展 Skill 脚本。entry 填 .py 相对路径或留空自动选择；勿填 shell 命令。入口须 `import skill_runtime`，结论用 `skill_runtime.finish`。

## When to use
- use 子层或 skill-dev：运行上传 Skill 的可执行入口
- 已确认 Skill 含合规 main.py

## When NOT to use
- 只查看 SKILL.md（用 load_uploaded_skill）
- 父编排层直调
- 调用平台已绑定 Skill 的 action（用 invoke_skill）

## Returns
- 脚本执行结论（经由 skill_runtime.finish）

## Parameters

### skill_name (required)
Skill slug。

### entry (optional)
Python 入口相对路径（如 main.py）；留空自动选择。勿填 cat/bash 等 shell。

### args (optional)
传给脚本的字符串参数列表。
