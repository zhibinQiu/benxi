"""Skill 目录聚合 — 内置 + 上传 + 权限/开关过滤。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import user_has_permission
from app.features.registry import ensure_plugins_loaded, get_plugin
from app.models.agent_skill import AgentSkill
from app.models.org import User
from app.skills.registry import all_builtin_skills, ensure_skills_loaded
from app.skills.types import SkillDefinition, SkillReadiness, SkillSource


def _binding_overrides(db: Session) -> dict[str, bool]:
    from app.models.agent_skill_binding import AgentSkillBinding

    try:
        rows = db.scalars(select(AgentSkillBinding)).all()
        return {row.name: row.enabled for row in rows}
    except Exception:
        db.rollback()
        return {}


def _is_feature_available(defn: SkillDefinition) -> bool:
    if not defn.feature_id:
        return True
    ensure_plugins_loaded()
    plugin = get_plugin(defn.feature_id)
    return bool(plugin and plugin.enabled)


def _effective_readiness(
    defn: SkillDefinition,
    *,
    user: User | None,
    db: Session | None,
    binding_overrides: dict[str, bool],
    admin_view: bool = False,
) -> SkillReadiness:
    if defn.source == SkillSource.BUILTIN:
        if defn.name in binding_overrides and not binding_overrides[defn.name]:
            return SkillReadiness.DISABLED
        if not _is_feature_available(defn):
            return SkillReadiness.DISABLED
        if defn.permission_code and db is not None and user is not None:
            if not admin_view and not user_has_permission(db, user, defn.permission_code):
                return SkillReadiness.NO_PERMISSION
        return defn.readiness
    return SkillReadiness.READY if defn.readiness == SkillReadiness.READY else defn.readiness


def resolve_skill_definition(
    db: Session,
    defn: SkillDefinition,
    *,
    user: User | None = None,
    admin_view: bool = False,
    bindings: dict[str, bool] | None = None,
) -> SkillDefinition:
    """返回带有效 readiness 的副本（frozen dataclass 需重建）。"""
    binding_overrides = bindings if bindings is not None else _binding_overrides(db)
    readiness = _effective_readiness(
        defn, user=user, db=db, binding_overrides=binding_overrides, admin_view=admin_view
    )
    enabled = readiness not in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION)
    if defn.source == SkillSource.BUILTIN and defn.name in binding_overrides:
        enabled = binding_overrides[defn.name]
    return SkillDefinition(
        name=defn.name,
        title=defn.title,
        description=defn.description,
        source=defn.source,
        tools=defn.tools,
        orchestrated_tools=defn.orchestrated_tools,
        feature_id=defn.feature_id,
        permission_code=defn.permission_code,
        readiness=readiness,
        skill_id=defn.skill_id,
        route=defn.route,
        source_type=defn.source_type,
        catalog_visible=defn.catalog_visible,
    )


def list_uploaded_skill_definitions(
    db: Session, *, include_disabled: bool = False
) -> list[SkillDefinition]:
    stmt = select(AgentSkill).where(AgentSkill.scope == "system").order_by(
        AgentSkill.name.asc()
    )
    if not include_disabled:
        stmt = stmt.where(AgentSkill.enabled.is_(True))
    rows = db.scalars(stmt).all()
    return [
        SkillDefinition(
            name=row.name,
            title=row.name,
            description=row.description,
            source=SkillSource.UPLOADED,
            tools=(),
            skill_id=row.id,
            readiness=SkillReadiness.READY if row.enabled else SkillReadiness.DISABLED,
            source_type=row.source_type,
        )
        for row in rows
    ]


def list_all_skill_definitions(
    db: Session,
    *,
    user: User | None = None,
    admin_view: bool = False,
    include_disabled: bool = False,
    exclude_feature_stubs: bool = True,
    catalog_only: bool = False,
) -> list[SkillDefinition]:
    """列出 Skill 定义。

    exclude_feature_stubs: 排除翻译/对比等系统功能占位项。
    catalog_only: 仅返回应对外展示的技能（隐藏单原子工具映射项）。
    """
    ensure_skills_loaded()
    bindings = _binding_overrides(db)
    out: list[SkillDefinition] = []
    for defn in all_builtin_skills():
        if exclude_feature_stubs and defn.readiness == SkillReadiness.STUB:
            continue
        resolved = resolve_skill_definition(
            db, defn, user=user, admin_view=admin_view, bindings=bindings
        )
        if include_disabled or resolved.readiness != SkillReadiness.DISABLED:
            if catalog_only and not resolved.catalog_visible:
                continue
            out.append(resolved)
    for defn in list_uploaded_skill_definitions(db, include_disabled=include_disabled):
        if include_disabled or defn.readiness != SkillReadiness.DISABLED:
            if catalog_only and not defn.catalog_visible:
                continue
            out.append(defn)
    return out


def get_merged_skill_definition(
    db: Session, name: str, *, user: User | None = None, admin_view: bool = False
) -> SkillDefinition | None:
    ensure_skills_loaded()
    from app.skills.registry import get_skill

    defn = get_skill(name)
    if defn:
        return resolve_skill_definition(db, defn, user=user, admin_view=admin_view)
    row = db.scalar(select(AgentSkill).where(AgentSkill.name == name))
    if row:
        return SkillDefinition(
            name=row.name,
            title=row.name,
            description=row.description,
            source=SkillSource.UPLOADED,
            tools=(),
            skill_id=row.id,
            readiness=SkillReadiness.READY if row.enabled else SkillReadiness.DISABLED,
            source_type=row.source_type,
        )
    return None


def build_agent_catalog_prompt(
    db: Session,
    user: User | None = None,
    *,
    admin_view: bool = False,
    skill_names: list[str] | None = None,
) -> str:
    """Discovery 阶段：注入 skill 描述符与选用规则（不含 SKILL.md 正文）。"""
    skills = list_all_skill_definitions(
        db, user=user, admin_view=admin_view, catalog_only=True
    )
    visible = [
        s
        for s in skills
        if s.readiness not in (SkillReadiness.DISABLED, SkillReadiness.NO_PERMISSION)
    ]
    if skill_names is not None:
        allow = {name.strip() for name in skill_names if (name or "").strip()}
        visible = [s for s in visible if s.name in allow]
    if not visible:
        return ""

    builtin = [s for s in visible if s.source == SkillSource.BUILTIN]
    uploaded = [s for s in visible if s.source == SkillSource.UPLOADED]

    lines = [
        "## Skills 目录（技能 · 选用规则）",
        "技能是对原子工具的编排说明；下列仅为摘要，**勿在开篇或无关任务时盲目 load**.",
        "",
        "### 何时调用原子工具",
        "- 闲聊、简单计算、直接可答的问题 → 不调工具，直接回答",
        "- 查企业文档 → `knowledge_retrieve`",
        "- 查本体图谱 → `kg_query`",
        "- 查互联网 → `web_search`",
        "- 知识问答需多路资料 → 按「知识综合检索」技能编排，依次调用 `knowledge_retrieve` / `kg_query` / `web_search`（按需，非每问必调）",
        "- 用户要**新建/编写 Skill** → 先调研，想清楚后再 `create_uploaded_skill`；"
        "**爬取/数据/自动化类必须在 extra_files 提供 main.py**，运行时 `run_skill_script` 直接执行；"
        "仅 mermaid/纯说明等极简任务可只有 SKILL.md；"
        "涉及网页时用 `browser_navigate` + `browser_snapshot` 探结构，**勿** `browser_screenshot`（除非用户明确要求）；"
        "勿猜测页面字段或重复创建已有同类技能\n",
        "- 用户任务匹配某**含脚本**的发展技能 → `run_skill_script`（系统自动注入 SKILL.md，勿 load）",
        "- 已有发展技能执行失败或无有效结论 → `update_uploaded_skill_file` 修复后重试，勿新建重复技能",
        "- 用户任务匹配**指令型**发展技能（如 mermaid-diagram）→ 按 SKILL.md 直接作答，**勿** run_skill_script",
        "- 你判断任务需要**含脚本**的发展技能时可调用 `run_skill_script`，无需用户明确要求",
    ]
    from app.integrations.browser_automation.browser_config import get_browser_rpa_config

    if get_browser_rpa_config(db).enabled:
        lines.extend(
            [
                "- 用户要**网页截图/可视化页面** → `browser_navigate` 后 `browser_screenshot`（**勿**用 `web-page-insight` 或 `run_skill_script`，脚本沙箱不能生成图片文件）",
                "- 需**点击/填表/操作网页**或 JavaScript 渲染页 → `browser_navigate` + `browser_snapshot` + `browser_click`/`browser_type`（先 snapshot 再 act；页面变化后重新 snapshot）；操作结果需展示给用户时才 `browser_screenshot`",
                "- 用户要求**保存网页操作流程** → `browser_save_workflow` 固化为 Skill",
                "- 回放已录制的 RPA Skill → `browser_replay_workflow` 或 `run_skill_script(entry=replay.py)`",
                "- 复杂目标一键探索 → `browser_run_task`；定时执行 → `schedule_browser_workflow`",
            ]
        )
    else:
        lines.extend(
            [
                "- 用户要**网页截图或浏览器交互** → 当前未启用浏览器 RPA，应说明需在「系统设置 → 模型设置 → 浏览器 RPA」开启；`web-page-insight` 仅能做文本摘要，**不能**截图或保存图片",
            ]
        )
    lines.extend(
        [
        "- 内置技能为选用说明，**禁止**对 builtin 使用 `load_uploaded_skill`",
        "- 发展技能（上传 / Agent 生成）才使用 `load_uploaded_skill`",
        "",
        ]
    )

    if builtin:
        lines.append("### 内置技能（编排原子工具；勿 load_uploaded_skill）")
        for skill in builtin:
            tools = "、".join(f"`{t}`" for t in skill.orchestrated_tools) or "—"
            lines.append(
                f"- `{skill.name}` [builtin]: {skill.description}"
                + (f"（编排: {tools}）" if skill.orchestrated_tools else "")
            )
        lines.append("")

    if uploaded:
        from app.services.agent_skill_service import uploaded_skill_has_script

        lines.append("### 发展技能（上传 / Agent 生成；匹配时系统自动加载 SKILL.md）")
        lines.append(
            "- **指令型**（仅 SKILL.md）：按说明直接作答，如图表用 ```mermaid`；**勿** run_skill_script"
        )
        lines.append(
            "- **脚本型**（含 main.py/run.py）：用 `run_skill_script` 沙箱执行"
            "（须 skill_runtime.finish 输出结论，不保存抓取原文）"
        )
        for skill in uploaded:
            tag = "[脚本型]" if uploaded_skill_has_script(db, skill.name) else "[指令型]"
            lines.append(f"- `{skill.name}` {tag}: {skill.description}")
        lines.append("")

    return "\n".join(lines).rstrip()


def set_builtin_binding(db: Session, name: str, *, enabled: bool) -> None:
    from app.models.agent_skill_binding import AgentSkillBinding

    row = db.get(AgentSkillBinding, name)
    if row:
        row.enabled = enabled
    else:
        db.add(AgentSkillBinding(name=name, enabled=enabled))
    db.commit()
