"""技能开发专精 — 发展 Skill 命名/脚本规范与默认脚手架。"""

from __future__ import annotations

import re

from app.core.exceptions import AppError, bad_request
from app.integrations.skill_script_executor import validate_skill_script

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# 引导模型使用平台注入的 skill_runtime（校验见 skill_script_executor AST）

_FETCH_UTILS_SCAFFOLD = '''"""网页 HTML 内存分析 — 只产出摘要，不持久化原文。"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_MAX_SNIPPET = 280
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header"})


class _HtmlAnalyzer(HTMLParser):
    """轻量 HTML 分析（纯 stdlib，无需 bs4/lxml）。"""
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self._body_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._tag_stack.append(t)
        if t == "title":
            self._in_title = True
        if t in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == t:
            self._tag_stack.pop()
        if t == "title":
            self._in_title = False
        if t in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = _clean(data)
        if not text:
            return
        if self._in_title:
            self.title += text
        elif self._skip_depth == 0:
            tag = self._tag_stack[-1] if self._tag_stack else ""
            if tag in _HEADING_TAGS:
                if text not in self.headings:
                    self.headings.append(text)
            else:
                self._body_parts.append(text)


def _clean(text: str) -> str:
    return unescape(re.sub(r"\\s+", " ", (text or ""))).strip()


def analyze_html(html: str) -> dict[str, object]:
    parser = _HtmlAnalyzer()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    title = _clean(parser.title) or "（无 title）"
    snippet = " ".join(parser._body_parts)[:_MAX_SNIPPET] or "（无摘要）"  # noqa: SLF001
    return {"title": title, "headings": parser.headings[:6], "snippet": snippet}


def build_conclusion(url: str, data: dict[str, object]) -> str:
    headings = data.get("headings") or []
    heading_text = "、".join(headings[:4]) if headings else "（无明显标题）"
    return (
        f"URL：{url}；标题：{data.get('title')}；主要标题：{heading_text}；"
        f"正文摘要：{data.get('snippet')}"
    )
'''

_MAIN_PY_URL_SCAFFOLD = '''"""发展技能入口 — 平台沙箱执行；结论须 skill_runtime.finish 输出。"""
from __future__ import annotations

import sys

import skill_runtime

from fetch_utils import analyze_html, build_conclusion


def main() -> None:
    url = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not url.startswith(("http://", "https://")):
        skill_runtime.finish("用法：run_skill_script 时 args 传入 https:// 开头的 URL")
        return
    try:
        html = skill_runtime.fetch_text(url)
        data = analyze_html(html)
        skill_runtime.finish(build_conclusion(url, data))
    except Exception as exc:
        skill_runtime.finish(f"抓取失败：{exc}")


if __name__ == "__main__":
    main()
'''

_MAIN_PY_GENERIC_SCAFFOLD = '''"""发展技能入口 — 平台沙箱执行；结论须 skill_runtime.finish 输出。"""
from __future__ import annotations

import skill_runtime


def main() -> None:
    # 在此实现业务逻辑；禁止 open/subprocess/requests/写文件
    skill_runtime.finish("脚本已执行；请根据 SKILL.md 与调研材料完善解析逻辑")


if __name__ == "__main__":
    main()
'''

SKILL_DEV_PLAYBOOK = """【发展 Skill 编写规范 · 创建/修复前必读】

## 1. 命名（invoke_skill skill-development call operation=create_skill 的 name 字段）

- **仅**小写英文字母、数字、连字符：`carbon-market-price`（✓）
- **禁止**：大写、下划线、中文、空格：`carbon_price_scraper`、`Carbon-Price`（✗）
- 与已有发展技能**重名**时系统会自动重命名（如 `carbon-price-scraper-2`），勿 load/覆盖旧包

## 2. 可执行包结构（数据/抓取类 **必须**含 main.py）

```text
my-skill/
├── SKILL.md          # frontmatter.name 与目录 slug 一致
│                      # description 含冒号时须引号包裹
│                      # 示例:
│                      #   ---
│                      #   name: my-skill
│                      #   description: "Use when: 查询价格；不要: 非价格相关"
│                      #   ---
└── main.py           # 入口，平台注入 skill_runtime.py
```

可参考平台示例 `web-page-insight`（`skill_runtime.fetch_text` + 内存解析，禁止落盘）。

## 3. main.py 硬性约束

| # | 必须 | 禁止 |
|---|------|------|
| ① | **文件顶部写 `import skill_runtime`**（平台注入的运行时模块，不写则执行报 `NameError`） | 删掉这一行 |
| ② | SKILL.md 的 YAML frontmatter 中 `description` 含冒号（如 `Use when: 查询价格`）时**必须**用引号包裹：`description: "Use when: 查询价格"`（否则 YAML 解析失败） | 在 description 中用无引号的冒号 |
| ③ | 末尾 `skill_runtime.finish("中文结论")` | `open()`、写文件、Path.write_* |
| ④ | 公开网页用 `skill_runtime.fetch_text(url)` | `requests`、`urllib`、`subprocess` |
| ⑤ | 结论为**摘要**（勿贴整页 HTML） | `eval`/`exec`、数据库、socket |

`finish` 会输出 `{"conclusion":"..."}` 单行 JSON；**不要**只 `print` 普通文本。

## 4. 推荐流程（生成/创建请求）

**勿** list_agent_skills 或 load/run 已有包——用户要求生成时**直接 create**。

1. `invoke_context_subagent` 完成调研（网页 browser_digest→browser-automation；公开信息 explore→web-search 等）
2. `invoke_skill(skill-development, call, {operation: create_skill, name, description, skill_md_body, extra_files})`
3. `invoke_skill(skill-development, call, {operation: run_skill_script, skill_name, entry: main.py})` 验证**新创建**的包；失败则 `{operation: update_uploaded_skill_file, ...}` 修 main.py，**勿**重复 create

## 5. 自动补能力场景（调度器已判定无匹配 Skill）

当收到以 `【调度自动补能力】` 开头的任务时：

- 视为系统要求你自动创建新 Skill 来填补能力缺口。
- 先按第 4 步完成调研，再直接 `create_skill`（无需用户明确说"创建"）。
- 创建出的 Skill 默认挂载到 `skill-dev`，并标记为 `needs_review`（不会进入通用 Skill 目录）。
- 必须 `run_skill_script` 验证新包，并将验证结论作为最终回复依据。
- 最终回答需说明：已创建 Skill 名称、验证结果、当前 Skill 仅挂载在 skill-dev 下待审。
"""


def slugify_skill_name(raw: str) -> str:
    """将用户/模型输入规范为合法 skill slug。"""
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
            "skill name 须为英文 slug（小写字母、数字、连字符），"
            "例如 carbon-market-price；勿使用纯中文名"
        )
    if not _SKILL_NAME_RE.match(slug):
        raise bad_request(
            "skill name 仅允许小写字母、数字与连字符（如 carbon-market-price）"
        )
    return slug


def validate_uploaded_skill_script(code: str) -> None:
    """校验发展技能脚本。"""
    validate_skill_script((code or "").strip())


def default_fetch_utils_scaffold() -> str:
    return _FETCH_UTILS_SCAFFOLD


def default_main_py_scaffold(*, needs_url: bool = False) -> str:
    return _MAIN_PY_URL_SCAFFOLD if needs_url else _MAIN_PY_GENERIC_SCAFFOLD


def ensure_script_extra_files(
    extra_files: dict[str, str] | None,
    *,
    needs_url: bool,
) -> dict[str, str]:
    """创建脚本型 Skill 时：校验 main.py；不合规则回退为平台脚手架。"""
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
    if "skill name" in text or "仅允许小写字母" in text:
        hints.append(
            "name 改为英文 slug（如 carbon-market-price），"
            "create 与 SKILL.md frontmatter.name 保持一致"
        )
    if "NameError" in text and "skill_runtime" in text:
        hints.append(
            "main.py 文件顶部缺少 `import skill_runtime`（平台注入的运行模块）。"
            "请确保第一行附近有 `import skill_runtime`，"
            "否则 skill_runtime.fetch_text / skill_runtime.finish 会 NameError。"
        )
    if "JSON" in text or "skill_runtime.finish" in text or "skill_runtime is not defined" in text:
        hints.append(
            "main.py 末尾须 skill_runtime.finish('中文结论')，"
            "勿只 print 或 print(dict)"
        )
    if "不允许" in text or "requests" in text or "urllib" in text or "subprocess" in text:
        hints.append(
            "删除 open/requests/urllib/subprocess；"
            "网页用 skill_runtime.fetch_text(url)，内存解析后 finish 摘要"
        )
    if "超时" in text or "timeout" in text.lower():
        hints.append(
            "脚本执行超过 30 秒，请精简逻辑或用 skill_runtime.fetch_text 限时抓取"
        )
    if "frontmatter" in text or "mapping values" in text:
        hints.append(
            "SKILL.md 的 description 字段含冒号时须 YAML 引号包裹，"
            "如 `description: \"Use when: ...\"`；创建时系统会自动修复，但建议直接传正确格式"
        )
    if hints:
        return f"{text} → 修复：{'；'.join(hints)}"
    return text


def enrich_skill_repair_reason(reason: str) -> str:
    """包装异常信息为修复上下文（兼容 AppError dict 字符串）。"""
    msg = reason
    if isinstance(reason, str) and reason.startswith("{") and "'message'" in reason:
        m = re.search(r"'message':\s*'([^']*)'", reason)
        if m:
            msg = m.group(1)
    return format_skill_script_repair_hint(msg)
