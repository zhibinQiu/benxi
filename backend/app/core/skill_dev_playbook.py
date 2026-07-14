"""技能开发专精 — Skill 命名/脚本规范与默认脚手架。"""

from __future__ import annotations

import re
from typing import Final

from app.core.exceptions import AppError, bad_request
from app.integrations.skill_script_executor import validate_skill_script
from app.core.skill_dev_scaffolds import default_fetch_utils_scaffold, default_main_py_scaffold

_SKILL_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

SKILL_DEV_PLAYBOOK: Final[str] = """【发展 Skill 编写规范 · 创建/修复前必读】

## 1. 命名

- **只允许**小写英文字母、数字、连字符：`carbon-market-price`（✓）
- **禁止**大写、下划线、中文、空格；与已有技能重名时自动重命名
- slug 长度上限 64 字符

## 2. 可执行包结构

```text
my-skill/
├── SKILL.md          # frontmatter.name 必须与目录 slug 一致
└── main.py           # 入口，平台自动注入 skill_runtime
```

## 3. main.py 约束

| # | 必须 | 禁止 |
|---|------|------|
| 1 | 顶部写 `import skill_runtime` | 删除这一行 |
| 2 | SKILL.md description 含冒号时用引号包裹 | 无引号冒号 |
| 3 | 末尾调用 `skill_runtime.finish("结论")` | 未输出 finish |
| 4 | 网页抓取可用 `subprocess.run(["curl",...])`、`requests.get()`（沙箱安全） | `eval`/`exec`/`compile` |
| 5 | 结论为摘要（勿贴整页 HTML） | 原始网页内容 |

## 4. 推荐流程

1. 先用 `invoke_context_subagent` 完成调研
2. 再 `invoke_skill(skill-development, call, {operation: create_skill, ...})`
3. 最后 `invoke_skill(skill-development, call, {operation: run_skill_script, ...})` 验证

## 5. 自动补能力场景

- 以 `【调度自动补能力】` 开头时视为系统要求自动创建 Skill
- 新 Skill 默认挂载到 `skill-dev`，标记 `needs_review`
"""

__all__ = [
    "build_skill_dev_playbook_block",
    "ensure_script_extra_files",
    "format_skill_script_repair_hint",
    "enrich_skill_repair_reason",
    "normalize_skill_slug",
    "slugify_skill_name",
    "SKILL_DEV_PLAYBOOK",
    "validate_uploaded_skill_script",
]


def slugify_skill_name(raw: str) -> str:
    """将用户/模型输入规范化为合法 skill slug。"""
    text = (raw or "").strip().lower()
    text = re.sub(r"[_\s]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if len(text) > 64:
        text = text[:64].rstrip("-")
    return text


def normalize_skill_slug(raw: str) -> str:
    slug = slugify_skill_name(raw)
    if not slug:
        raise bad_request(
            "skill name must be an English slug (lowercase, digits, hyphens), "
            "e.g. carbon-market-price"
        )
    if not _SKILL_NAME_RE.match(slug):
        raise bad_request(
            "skill name only allows lowercase letters, digits, and hyphens, "
            "e.g. carbon-market-price"
        )
    return slug


def validate_uploaded_skill_script(code: str) -> None:
    """校验发展技能脚本。"""
    validate_skill_script((code or "").strip())


def ensure_script_extra_files(
    extra_files: dict[str, str] | None,
    *,
    needs_url: bool,
) -> dict[str, str]:
    """创建脚本型 Skill 时：校验 main.py，不合规则回退为平台脚手架。"""
    files = dict(extra_files or {})
    main = (files.get("main.py") or "").strip()
    if main:
        try:
            validate_uploaded_skill_script(main)
            if needs_url and "fetch_utils.py" not in files:
                files["fetch_utils.py"] = default_fetch_utils_scaffold()
            return files
        except AppError:
            pass
    files["main.py"] = default_main_py_scaffold(needs_url=needs_url)
    if needs_url:
        files["fetch_utils.py"] = default_fetch_utils_scaffold()
    return files


def build_skill_dev_playbook_block() -> str:
    return SKILL_DEV_PLAYBOOK


def format_skill_script_repair_hint(reason: str) -> str:
    """将沙箱/校验报错转为可操作的修复指引。"""
    text = (reason or "").strip()
    if not text:
        return text
    hints: list[str] = []
    if "skill name" in text.lower() or "lowercase" in text.lower():
        hints.append(
            "Rename to an English slug (e.g. carbon-market-price); "
            "keep `create` and SKILL.md frontmatter.name consistent"
        )
    if "NameError" in text and "skill_runtime" in text:
        hints.append(
            "main.py is missing `import skill_runtime` at the top. "
            "Add it so fetch_text / finish are available."
        )
    if "JSON" in text or "skill_runtime.finish" in text:
        hints.append(
            "main.py must end with `skill_runtime.finish('结论')` — "
            "do not rely on print() alone"
        )
    if "timeout" in text.lower() or "timed out" in text.lower():
        hints.append(
            "Script ran over 30s. Simplify the logic or use "
            "skill_runtime.fetch_text with a shorter timeout."
        )
    if "frontmatter" in text.lower() or "mapping values" in text.lower():
        hints.append(
            "SKILL.md description includes a colon — wrap it in YAML quotes."
        )
    if hints:
        return f"{text} → 修复：{'；'.join(hints)}"
    return text


def enrich_skill_repair_reason(reason: str) -> str:
    """包装异常信息为修复上下文。"""
    msg = reason
    if isinstance(reason, str) and reason.startswith("{") and "'message'" in reason:
        m = re.search(r"'message':\s*'([^']*)'", reason)
        if m:
            msg = m.group(1)
    return format_skill_script_repair_hint(msg)
