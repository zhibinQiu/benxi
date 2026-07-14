"""系统智能体 AGENT.md 默认内容与解析。"""

from __future__ import annotations

from typing import Any

import yaml

from app.agentkit.config import MarkdownConfigLoader
from app.core.agent_profiles import AgentProfileDef
from app.core.exceptions import bad_request

AGENT_MD_FILENAME = "AGENT.md"
STYLE_MD_FILENAME = "STYLE.md"


class _InstructionLoader(MarkdownConfigLoader):
    """智能体指令加载器：从 agents/instructions/*.md 读取。

    每个 MD 文件使用 YAML frontmatter 定义 id/title/description，
    正文部分为智能体的指令内容。
    修改 MD 文件后立即生效（mtime 检测）。
    """

    _CONFIG_DIR = "agents/instructions"
    _SCAN_INTERVAL = 2.0
    _SKIP_FRONTMATTER = True  # 只保留正文


_instruction_loader = _InstructionLoader()


def get_default_instruction_body(agent_id: str) -> str | None:
    """返回智能体默认指令正文（从 MD 文件加载）。
    不存在时返回 None（调用方回退）。
    """
    return _instruction_loader.get(agent_id)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    raw = (text or "").lstrip("\ufeff")
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise bad_request(f"AGENT.md frontmatter 解析失败: {exc}") from exc
    if not isinstance(meta, dict):
        raise bad_request("AGENT.md frontmatter 必须是 YAML 对象")
    return meta, parts[2].lstrip("\n")


def build_default_agent_md(defn: AgentProfileDef) -> str:
    body = get_default_instruction_body(defn.id) or f"# {defn.title}\n"
    return (
        f"---\n"
        f"id: {defn.id}\n"
        f"title: {defn.title}\n"
        f"description: {defn.description}\n"
        f"---\n"
        f"{body.rstrip()}\n"
    )


def get_effective_agent_md(defn: AgentProfileDef, config_md: str | None) -> str:
    stored = (config_md or "").strip()
    if stored:
        return stored
    return build_default_agent_md(defn)


def get_effective_description(defn: AgentProfileDef, config_md: str | None) -> str:
    md = get_effective_agent_md(defn, config_md)
    frontmatter, _ = parse_frontmatter(md)
    desc = str(frontmatter.get("description") or "").strip()
    return desc or defn.description


def get_config_instruction_body(defn: AgentProfileDef, config_md: str | None) -> str | None:
    """运行时专精正文；有自定义 AGENT.md 时用其 body，否则 None 表示内置块。"""
    stored = (config_md or "").strip()
    if not stored:
        return None
    _, body = parse_frontmatter(stored)
    text = (body or "").strip()
    return text or None


def validate_agent_md(agent_id: str, content: str) -> str:
    text = (content or "").strip()
    if not text:
        raise bad_request("AGENT.md 不能为空")
    frontmatter, body = parse_frontmatter(text)
    fm_id = str(frontmatter.get("id") or "").strip()
    if fm_id != agent_id:
        raise bad_request(f"AGENT.md frontmatter.id 必须为 `{agent_id}`")
    desc = str(frontmatter.get("description") or "").strip()
    if not desc:
        raise bad_request("AGENT.md frontmatter.description 不能为空（描述何时路由到该智能体）")
    if not (body or "").strip():
        raise bad_request("AGENT.md 正文不能为空")
    return text


# ── STYLE.md ──────────────────────────────────────────────────────────────────

DEFAULT_STYLE_MD_TEMPLATE = """# 回复风格设定

你可以在此文件中设定该智能体的回复风格偏好，例如语气、措辞、详细程度等。

## 语气与风格

- 语气：专业 / 友好 / 简洁 / 正式（请选择或自定义）
- 使用表情符号：否
- 使用 Markdown 格式：是
- 引用来源：是

## 详细程度

- 默认回复长度：适中
- 列举信息时：使用列表
- 复杂概念：需分层解释

## 特殊要求

- 对非技术用户：避免过多术语
- 确认步骤：关键操作前需用户确认
- 错误处理：给出具体原因和可行建议

---

*以上为默认模板，你可以按需修改，无需保留 frontmatter。*
"""


def build_default_style_md(defn: AgentProfileDef) -> str:
    """返回对应智能体的默认 STYLE.md 内容。"""
    return (
        f"# {defn.title} — 回复风格设定\n\n"
        f"{DEFAULT_STYLE_MD_TEMPLATE}"
    )


def get_effective_style_md(defn: AgentProfileDef, style_md: str | None) -> str:
    """有自定义 style_md 时返回自定义值，否则返回默认模板。"""
    stored = (style_md or "").strip()
    if stored:
        return stored
    return build_default_style_md(defn)
