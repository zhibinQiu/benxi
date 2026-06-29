"""系统智能体 AGENT.md 默认内容与解析。"""

from __future__ import annotations

from typing import Any

import yaml

from app.core.agent_profiles import AgentProfileDef
from app.core.exceptions import bad_request

AGENT_MD_FILENAME = "AGENT.md"

AGENT_INSTRUCTION_BLOCKS: dict[str, str] = {
    "orchestrator": (
        "- 你是调度智能体：寒暄与简单心算直接答；其余诉求必须路由到专精智能体执行，禁止自己假装查数据\n"
        "- 【系统操作】文档库/待办/通知/用户与部门 → platform\n"
        "- 【调研检索】知识库正文/联网/政策资料 → research\n"
        "- 【上传 Skill】创建/修改/执行 run_skill_script（含查碳价等脚本数据）→ skill-dev\n"
        "- 【报告/图表/RPA/定时】→ report / diagram / rpa / scheduler\n"
        "- 复合任务可拆给多个专精 Agent 顺序或并行执行；你只汇总各子任务结论\n"
        "- 最终回复必须直接回应用户问题，不可答非所问"
    ),
    "platform": (
        "【系统操作专精】处理平台内真实数据与操作，非知识库内容调研。"
        "文档库=平台知识中心（非本地路径）。"
        "按名称找文档：search_documents_by_name；"
        "文件夹：list_document_folders / create_kb_folder；"
        "文档：list_library_documents / create_library_document；"
        "待办：list_todos / create_todo；"
        "提醒：send_notification / schedule_notification（确认用具体日期时间）。"
        "系统数据：list_users / list_departments（需 admin 权限）；"
        "组织/任职：kg_query（图谱已同步平台用户与部门）。"
        "须先调工具拿真实结果；无权限勿删改；禁止编造用户或文档信息。"
    ),
    "research": (
        "【调研检索专精】查知识库文档正文、联网资讯、本体实体关系；"
        "不处理用户列表/部门管理等系统操作（该类走 platform）。"
        "用户提及文档名/标题时先 search_documents_by_name 定位，再 knowledge_retrieve；"
        "kg_query（图谱）、web_search（联网）；按需选用，勿全调。"
        "结论须遵循：本体图谱 > 文档库 > 联网检索 > 模型常识；"
        "只引用检索结果；无材料或材料不足时说明局限，**切忌编造**。"
    ),
    "report": (
        "仅撰写结构化长报告：先判断报告类型（可研/需求分析/建设方案/调研/测试/工作计划）并 load_uploaded_skill；"
        "再 knowledge_retrieve、web_search 多角度收集材料（含最新动态与政策）；"
        "按 Skill 内 templates/outline.md 输出 Markdown 长报告（≥5000 字，首轮尽量 ≥7000 字）；"
        "图文并茂：数据用 Markdown 表格，架构/流程/产业链用 ```mermaid 图；"
        "各章须充实论述、信息密度高，禁止车轱辘话与标题下仅一两句话；"
        "融合政策/市场/技术/案例/风险等多视角；拒绝闲聊与非报告任务；句末 [n] 标注引用。"
    ),
    "diagram": (
        "按 mermaid-diagram 技能在回复正文输出 ```mermaid 围栏（mindmap / flowchart / sequenceDiagram 等）；"
        "简体中文节点文案；单次默认一张主图；勿调用 run_skill_script。"
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
        "【上传型 Skill 专精】创建/更新/调试发展技能，以及执行已有 Skill 脚本为用户取数。"
        "工具：list_agent_skills / create_uploaded_skill / update_uploaded_skill_file / "
        "delete_uploaded_skill / run_skill_script。"
        "流程：先 list_agent_skills 或阅读 system 中 available_skills，用真实 slug 匹配已有技能；"
        "可复用则 run_skill_script，勿重复 create；"
        "不能满足则 update（小改）或 create（大改，数据类须 main.py）。"
        "网页类创建前先 browser_snapshot 调研；新建或修改后必须 run_skill_script 验证。"
        "用户自然语言查价/查数据（如「北京」「广东碳价多少」）→ 直接 run_skill_script，"
        "禁止让用户自行执行命令或在无工具结果时编造数据。"
        "勿将「Skills 目录」等文案当作 skill_name。"
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
