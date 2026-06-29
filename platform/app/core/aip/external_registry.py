"""外部 AIP 智能体注册表 — 接入第三方符合 AIP 协议的服务智能体。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.config import get_settings
from app.core.aip.types import AipCapability

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExternalAgentRecord:
    """外部服务智能体登记项（GB/Z 185.4 + 185.5 精简）。"""

    aid: str
    name: str
    description: str
    service_endpoint: str
    capabilities: tuple[AipCapability, ...] = field(default_factory=tuple)
    enabled: bool = True
    source: str = "config"


def _parse_capabilities(raw_list: list[Any]) -> tuple[AipCapability, ...]:
    caps: list[AipCapability] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        cap_id = str(item.get("id") or "").strip()
        if not cap_id:
            continue
        caps.append(
            AipCapability(
                id=cap_id,
                name=str(item.get("name") or cap_id),
                description=str(item.get("description") or ""),
                input=dict(item.get("input") or {}),
                output=dict(item.get("output") or {}),
                constraints=dict(item.get("constraints") or {}),
            )
        )
    return tuple(caps)


def _record_from_config_item(item: dict[str, Any]) -> ExternalAgentRecord | None:
    aid = str(item.get("aid") or "").strip()
    endpoint = str(item.get("service_endpoint") or "").strip()
    if not aid or not endpoint:
        return None
    return ExternalAgentRecord(
        aid=aid,
        name=str(item.get("name") or aid),
        description=str(item.get("description") or ""),
        service_endpoint=endpoint,
        capabilities=_parse_capabilities(list(item.get("capabilities") or [])),
        enabled=bool(item.get("enabled", True)),
        source="config",
    )


@lru_cache(maxsize=1)
def load_config_external_agents() -> tuple[ExternalAgentRecord, ...]:
    """从配置 ``aip_external_agents_json`` 加载外部智能体列表。"""
    settings = get_settings()
    raw = (settings.aip_external_agents_json or "[]").strip()
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning("aip_external_agents_json 不是合法 JSON，已忽略")
        return ()
    if not isinstance(data, list):
        return ()

    records: list[ExternalAgentRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        record = _record_from_config_item(item)
        if record is not None:
            records.append(record)
    return tuple(records)


def _load_db_external_agents(db: Session) -> tuple[ExternalAgentRecord, ...]:
    from app.models.aip_external_agent import AipExternalAgent

    rows = db.scalars(select(AipExternalAgent).order_by(AipExternalAgent.created_at)).all()
    return tuple(
        ExternalAgentRecord(
            aid=row.aid,
            name=row.name,
            description=row.description or "",
            service_endpoint=row.service_endpoint,
            capabilities=(),
            enabled=bool(row.enabled),
            source="db",
        )
        for row in rows
    )


def load_external_agents(db: Session | None = None) -> tuple[ExternalAgentRecord, ...]:
    """合并 DB 登记与配置项；同 AID 时 DB 优先。"""
    config_records = load_config_external_agents()
    if db is None:
        return config_records
    db_records = _load_db_external_agents(db)
    by_aid = {record.aid: record for record in config_records}
    for record in db_records:
        by_aid[record.aid] = record
    return tuple(by_aid.values())


def get_external_agent(aid: str, db: Session | None = None) -> ExternalAgentRecord | None:
    """按 AID 查找外部智能体。"""
    target = (aid or "").strip()
    for record in load_external_agents(db):
        if record.aid == target and record.enabled:
            return record
    return None


def list_external_agents(
    db: Session | None = None,
    *,
    capability: str | None = None,
    keyword: str | None = None,
    include_disabled: bool = False,
) -> list[ExternalAgentRecord]:
    """发现外部智能体（能力 / 关键词过滤）。"""
    cap_filter = (capability or "").strip().lower()
    q = (keyword or "").strip().lower()
    out: list[ExternalAgentRecord] = []
    for record in load_external_agents(db):
        if not record.enabled and not include_disabled:
            continue
        cap_ids = [cap.id for cap in record.capabilities]
        if cap_filter:
            if cap_filter not in {c.lower() for c in cap_ids} and cap_filter not in record.aid.lower():
                continue
        if q:
            hay = f"{record.name} {record.description} {' '.join(cap_ids)}".lower()
            if q not in hay:
                continue
        out.append(record)
    return out


def is_external_aid(aid: str, db: Session | None = None) -> bool:
    return get_external_agent(aid, db) is not None


def clear_external_agent_cache() -> None:
    """配置热更新时清缓存（测试用）。"""
    load_config_external_agents.cache_clear()
