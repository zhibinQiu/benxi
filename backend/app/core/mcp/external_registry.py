"""外部 MCP Skill 注册表 — DB + 配置双源合并。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpExternalSkillRecord:
    name: str
    title: str
    description: str
    endpoint: str
    transport: str
    auth_token: str
    enabled: bool
    tools_cache: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    use_when: str = ""
    dont_use_when: str = ""
    output: str = ""
    source: str = "db"
    record_id: Any | None = None


def _tools_from_raw(raw: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and str(item.get("name") or "").strip():
            out.append(dict(item))
    return tuple(out)


def _record_from_config_item(item: dict[str, Any]) -> McpExternalSkillRecord | None:
    name = str(item.get("name") or "").strip()
    endpoint = str(item.get("endpoint") or "").strip()
    if not name or not endpoint:
        return None
    return McpExternalSkillRecord(
        name=name,
        title=str(item.get("title") or name),
        description=str(item.get("description") or ""),
        endpoint=endpoint,
        transport=str(item.get("transport") or "http").strip().lower() or "http",
        auth_token=str(item.get("auth_token") or ""),
        enabled=bool(item.get("enabled", True)),
        tools_cache=_tools_from_raw(item.get("tools") or item.get("tools_cache")),
        use_when=str(item.get("use_when") or ""),
        dont_use_when=str(item.get("dont_use_when") or ""),
        output=str(item.get("output") or ""),
        source="config",
    )


@lru_cache(maxsize=1)
def load_config_mcp_skills() -> tuple[McpExternalSkillRecord, ...]:
    settings = get_settings()
    raw = (settings.mcp_external_skills_json or "[]").strip()
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning("mcp_external_skills_json 不是合法 JSON，已忽略")
        return ()
    if not isinstance(data, list):
        return ()
    records: list[McpExternalSkillRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        record = _record_from_config_item(item)
        if record is not None:
            records.append(record)
    return tuple(records)


def _load_db_mcp_skills(db: Session) -> tuple[McpExternalSkillRecord, ...]:
    from app.models.mcp_external_skill import McpExternalSkill

    rows = db.scalars(select(McpExternalSkill).order_by(McpExternalSkill.created_at)).all()
    return tuple(
        McpExternalSkillRecord(
            name=row.name,
            title=row.title or row.name,
            description=row.description or "",
            endpoint=row.endpoint,
            transport=(row.transport or "http").strip().lower() or "http",
            auth_token=row.auth_token or "",
            enabled=bool(row.enabled),
            tools_cache=_tools_from_raw(row.tools_cache),
            use_when=row.use_when or "",
            dont_use_when=row.dont_use_when or "",
            output=row.output or "",
            source="db",
            record_id=row.id,
        )
        for row in rows
    )


def load_mcp_external_skills(db: Session | None = None) -> tuple[McpExternalSkillRecord, ...]:
    config_records = load_config_mcp_skills()
    if db is None:
        return config_records
    db_records = _load_db_mcp_skills(db)
    by_name = {record.name: record for record in config_records}
    for record in db_records:
        by_name[record.name] = record
    return tuple(by_name.values())


def get_mcp_skill_record(name: str, db: Session | None = None) -> McpExternalSkillRecord | None:
    target = (name or "").strip()
    for record in load_mcp_external_skills(db):
        if record.name == target and record.enabled:
            return record
    return None


def list_mcp_skill_records(
    db: Session | None = None,
    *,
    include_disabled: bool = False,
) -> list[McpExternalSkillRecord]:
    out: list[McpExternalSkillRecord] = []
    for record in load_mcp_external_skills(db):
        if not record.enabled and not include_disabled:
            continue
        out.append(record)
    return out


def clear_mcp_skill_cache() -> None:
    load_config_mcp_skills.cache_clear()
