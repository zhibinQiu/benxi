"""系统智能体 AGENT.md 默认内容与解析。"""

from __future__ import annotations

from typing import Any

import yaml

from app.core.agent_profiles import AgentProfileDef
from app.core.exceptions import bad_request

AGENT_MD_FILENAME = "AGENT.md"
STYLE_MD_FILENAME = "STYLE.md"

AGENT_INSTRUCTION_BLOCKS: dict[str, str] = {
    "orchestrator": (
        "【通用智能体 · 直接处理】\n"
        "本智能体已挂载所有常用通用 Skill，可直接处理大多数任务，无需路由到专精。\n"
        "你可直接调用的 Skill 及用途：\n"
        "  - web-search / knowledge-search：联网或知识库检索\n"
        "  - knowledge-research：组合式多源检索（图谱→联网→文档库）\n"
        "  - kg-palantir：本体图谱实体关系查询\n"
        "  - free-web-ai-chat：免费网页 AI 对话\n"
        "  - free-web-ai-image：文字生图\n"
        "  - free-web-ai-ask-image：上传图片识图问答\n"
        "  - mermaid-diagram：绘制流程图/架构图/时序图等\n"
        "  - ask_user_choice：信息不足以决策时，让用户从多个方案中选择\n"
        "路由到专精 Agent 的时机（仅当要做以下事情时）：\n"
        "  - platform：平台文档库 CRUD、待办 CRUD、用户/部门管理\n"
        "  - rpa：浏览器操作（导航/点击/填表/截图/流程录制回放）— 以操作为目的的浏览器使用\n"
        "  - scheduler：定时/延迟提醒、即时通知、定时浏览器流程安排\n"
        "  - skill-dev：上传型 Skill 生命周期管理（创建/修改/删除/脚本验证）\n"
        "路由前自问：我能直接用已有 Skill 处理吗？能则直接处理，勿为走流程硬路由。\n"
        "专精 request_orchestrator_assist 反馈缺口时：协调其他专精协助，"
        "协助完成后再交还原专精续办。\n"
        "复合任务可拆给多个专精顺序或并行执行；只收结论，不收探索过程。\n"
        "遇阻碍：说明具体原因与可行下一步，避免「任务失败/无法完成」等否定式结论。"
    ),
    "platform": (
        "【平台信息专精 · 执行域】\n"
        "处理平台内真实数据与写操作。文档库=平台知识中心（非本地路径）。\n"
        "常用：search_documents_by_name / list_document_folders / create_library_document；"
        "list_todos / create_todo；"
        "list_users / list_departments（须 admin 权限）。\n"
        "图谱查询、AI 对话/生图等通用任务由通用智能体（orchestrator）直接处理，勿在本域处理。\n"
        "须先调工具拿真实结果；无权限勿删改；禁止编造用户或文档信息。\n"
        "本域无法完成时：request_orchestrator_assist 告知调度。"
    ),
    "rpa": (
        "【浏览器自动化专精 · 执行域】\n"
        "所有浏览器操作通过 invoke_skill(browser-automation, call, "
        "{operation, params}) 调用，支持操作如下：\n"
        "  - browser_navigate(params={url}) — 导航\n"
        "  - browser_snapshot(params={}) — 获取可交互元素 ref\n"
        "  - browser_click(params={ref}) — 点击\n"
        "  - browser_type(params={ref, text, submit?}) — 输入\n"
        "  - browser_fill(params={fields}) — 批量填表\n"
        "  - browser_screenshot(params={full_page?}) — 截图\n"
        "  - browser_save_workflow(params={name}) — 保存流程\n"
        "  - browser_replay_workflow(params={skill_name}) — 回放\n"
        "  - browser_close_session(params={}) — 关闭会话\n"
        "典型流程：browser_navigate → browser_snapshot → browser_click/browser_type → browser_screenshot。\n"
        "主业：浏览器操作（导航/点击/填表/截图/录制回放），操作本身就是目的。\n"
        "纯主题调研、AI 对话/生图、知识检索等通用任务由通用智能体（orchestrator）处理。\n"
        "本域无法完成时：request_orchestrator_assist。"
    ),
    "scheduler": (
        "【时间调度专精 · 执行域】\n"
        "本域通过 invoke_skill(notification, call, {operation, params}) 调用通知类操作：\n"
        "  - send_notification（立即通知）\n"
        "  - schedule_notification（定时提醒，scheduled_at 传 ISO 8601 绝对时间）\n"
        "  - list_scheduled_notifications（查看待发通知）\n"
        "  - cancel_scheduled_notification（取消通知）\n"
        "定时浏览器流程通过 invoke_skill(browser-automation, call, {operation: schedule_browser_workflow, params})。\n"
        "立即执行的浏览器操作交 rpa。\n"
        "通用检索/问答由通用智能体（orchestrator）处理。\n"
        "本域无法完成时：request_orchestrator_assist。"
    ),
    "skill-dev": (
        "【技能开发专精 · 执行域】\n"
        "主业：invoke_skill(skill-development, call, {operation, params}) 管理上传型 Skill"
        "（create/update/delete/run_skill_script/list_agent_skills）。\n"
        "浏览器调研：创建抓取类 Skill 时可直接 invoke_skill(browser-automation, call, ...)"
        "调研页面结构——这是创建抓取类 Skill 的**中间步骤**，调研完立即回到技能创建主流程。\n"
        "纯主题检索调研：用 invoke_context_subagent(kind=explore, queries=[...]) 委托子 Agent"
        "调用 web-search / knowledge-search / kg-palantir。\n"
        "创建规范：name=英文 slug；main.py 须 skill_runtime.finish + fetch_text；"
        "禁 requests/open/subprocess。系统会给注入完整编写规范。\n"
        "通用检索/问答由通用智能体（orchestrator）处理。\n"
        "本域无法完成时：request_orchestrator_assist。"
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
