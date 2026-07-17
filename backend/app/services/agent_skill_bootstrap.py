"""启动时同步示例 Agent Skills（mermaid-diagram、报告类型 Skills 等）。"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.phone import bootstrap_login_id
from app.core.report_skill_catalog import REPORT_SKILL_NAMES
from app.models.agent_skill import AgentSkill
from app.models.org import User
from app.services.agent_skill_router import MERMAID_DIAGRAM_SKILL

_logger = logging.getLogger(__name__)


def _example_skills_root() -> Path:
    """本机仓库根或 Docker /app 下的 examples/agent-skills。"""
    here = Path(__file__).resolve()
    for base in (here.parents[3], here.parents[2]):
        candidate = base / "examples" / "agent-skills"
        if candidate.is_dir():
            return candidate
    return here.parents[3] / "examples" / "agent-skills"


def _read_skill_folder_entries(skill_dir: Path) -> list[tuple[str, bytes]]:
    if not (skill_dir / "SKILL.md").is_file():
        return []
    entries: list[tuple[str, bytes]] = []
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(skill_dir).as_posix()
        entries.append((rel, path.read_bytes()))
    return entries


def ensure_example_skill(db: Session, skill_name: str) -> bool:
    """若库中无该 Skill 或未启用，则从 examples/agent-skills 导入。"""
    row = db.scalar(select(AgentSkill).where(AgentSkill.name == skill_name))
    if row is not None and row.enabled:
        return False

    skill_dir = _example_skills_root() / skill_name
    entries = _read_skill_folder_entries(skill_dir)
    if not entries:
        _logger.warning(
            "跳过 %s 种子：示例目录不存在或缺少 SKILL.md（%s）",
            skill_name,
            skill_dir,
        )
        return False

    admin = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    if admin is None:
        _logger.warning("跳过 %s 种子：未找到 bootstrap 管理员", skill_name)
        return False

    from app.services.agent_skill_service import upload_skill_folder

    upload_skill_folder(db, admin, entries, replace_existing=True)
    _logger.info("已同步内置示例技能 %s", skill_name)
    return True


def ensure_mermaid_diagram_skill(db: Session) -> bool:
    return ensure_example_skill(db, MERMAID_DIAGRAM_SKILL)


def ensure_report_type_skills(db: Session) -> int:
    seeded = 0
    for name in REPORT_SKILL_NAMES:
        if ensure_example_skill(db, name):
            seeded += 1
    return seeded


CARBON_CONSULTING_SKILL = "carbon-consulting"


def _example_skill_names() -> tuple[str, ...]:
    return (MERMAID_DIAGRAM_SKILL, CARBON_CONSULTING_SKILL, *REPORT_SKILL_NAMES)


def _all_example_skills_ready(db: Session) -> bool:
    """全部示例 Skill 已启用时跳过磁盘扫描与上传。"""
    names = _example_skill_names()
    rows = db.scalars(
        select(AgentSkill.name).where(
            AgentSkill.name.in_(names),
            AgentSkill.enabled.is_(True),
        )
    ).all()
    return len(set(rows)) >= len(names)


def ensure_carbon_consulting_skill(db: Session) -> bool:
    return ensure_example_skill(db, CARBON_CONSULTING_SKILL)


def ensure_example_agent_skills(db: Session) -> None:
    if _all_example_skills_ready(db):
        return
    ensure_mermaid_diagram_skill(db)
    ensure_carbon_consulting_skill(db)
    ensure_report_type_skills(db)
