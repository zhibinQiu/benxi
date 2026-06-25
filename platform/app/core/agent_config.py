"""系统智能体 AGENT.md 默认内容与解析。"""

from __future__ import annotations

from typing import Any

import yaml

from app.core.agent_profiles import AgentProfileDef
from app.core.exceptions import bad_request

AGENT_MD_FILENAME = "AGENT.md"

AGENT_INSTRUCTION_BLOCKS: dict[str, str] = {
    "orchestrator": "- 复杂操作由专精智能体处理；你只做理解与简短应答",
    "platform": (
        "文档库=平台知识中心（非本地路径）。"
        "文件夹：list_document_folders / create_kb_folder；"
        "文档：list_library_documents / create_library_document；"
        "待办：list_todos / create_todo；"
        "提醒：send_notification / schedule_notification（确认用具体日期时间）。"
        "无权限勿分享/移动/删除。"
    ),
    "research": (
        "检索：knowledge_retrieve（文档）、kg_query（图谱）、web_search（联网）；按需选用，勿全调。"
    ),
    "rpa": (
        "browser_navigate → browser_snapshot → click/type；"
        "仅用户要求时 browser_screenshot；保存流程 browser_save_workflow。"
    ),
    "scheduler": (
        "schedule_notification / list_scheduled_notifications / cancel_scheduled_notification；"
        "定时 RPA：schedule_browser_workflow。"
    ),
    "skill-dev": (
        "create_uploaded_skill / update_uploaded_skill_file / delete_uploaded_skill；"
        "数据类须 main.py；先 snapshot 调研；失败修 skill 勿重复创建。"
    ),
}


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
    body = AGENT_INSTRUCTION_BLOCKS.get(defn.id, f"# {defn.title}\n")
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
