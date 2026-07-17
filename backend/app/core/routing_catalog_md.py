"""skills.md / agents.md 路由目录 — 调度层统一读取的简约描述。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.agentkit.skills.search import skill_query_tokens

_SKILLS_MD = Path(__file__).resolve().parent.parent / "skills" / "skills.md"
_AGENTS_MD = Path(__file__).resolve().parent / "agents.md"

_FIELD_ALIASES = {
    "use when": "use_when",
    "use_when": "use_when",
    "何时使用": "use_when",
    "don't use when": "dont_use_when",
    "dont use when": "dont_use_when",
    "dont_use_when": "dont_use_when",
    "何时不用": "dont_use_when",
    "output": "output",
    "返回": "output",
    "title": "title",
    "skills": "skills",
    "绑定 skills": "skills",
}


@dataclass(frozen=True, slots=True)
class RoutingEntry:
    id: str
    title: str = ""
    use_when: str = ""
    dont_use_when: str = ""
    output: str = ""
    skills: str = ""


def _truncate(text: str, limit: int = 72) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _parse_field_line(line: str) -> tuple[str, str] | None:
    body = line.strip()
    if not body.startswith("- "):
        return None
    body = body[2:].strip()
    if ":" not in body:
        return None
    key, value = body.split(":", 1)
    field = _FIELD_ALIASES.get(key.strip().lower())
    if not field:
        return None
    return field, value.strip()


def parse_routing_md(text: str) -> dict[str, RoutingEntry]:
    entries: dict[str, RoutingEntry] = {}
    current_id: str | None = None
    fields: dict[str, str] = {}

    def _flush() -> None:
        nonlocal current_id, fields
        if not current_id:
            return
        entries[current_id] = RoutingEntry(
            id=current_id,
            title=fields.get("title", ""),
            use_when=fields.get("use_when", ""),
            dont_use_when=fields.get("dont_use_when", ""),
            output=fields.get("output", ""),
            skills=fields.get("skills", ""),
        )
        current_id = None
        fields = {}

    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            _flush()
            current_id = line[3:].strip()
            continue
        parsed = _parse_field_line(raw)
        if parsed and current_id:
            fields[parsed[0]] = parsed[1]
    _flush()
    return entries


@lru_cache(maxsize=1)
def load_skills_routing_md() -> dict[str, RoutingEntry]:
    return parse_routing_md(_SKILLS_MD.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_agents_routing_md() -> dict[str, RoutingEntry]:
    return parse_routing_md(_AGENTS_MD.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def skills_routing_md_text() -> str:
    return _SKILLS_MD.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def agents_routing_md_text() -> str:
    return _AGENTS_MD.read_text(encoding="utf-8").strip()


def routing_entry_haystack(entry: RoutingEntry) -> str:
    return " ".join(
        filter(
            None,
            (entry.id, entry.title, entry.use_when, entry.dont_use_when, entry.output, entry.skills),
        )
    ).lower()


def format_skill_route_line(entry: RoutingEntry, *, tag: str = "") -> str:
    use = _truncate(entry.use_when or "任务明确匹配时")
    dont = _truncate(entry.dont_use_when or "闲聊、无关任务")
    output = _truncate(entry.output or "按 Skill 描述或脚本结论作答")
    prefix = f"`{entry.id}`"
    if tag:
        prefix = f"{prefix} {tag}"
    return f"- {prefix} — Use when: {use} | Don't: {dont} | Output: {output}"


def format_agent_route_line(entry: RoutingEntry) -> str:
    title = entry.title or entry.id
    use = _truncate(entry.use_when or "任务明确匹配该专精域时")
    dont = _truncate(entry.dont_use_when or "闲聊、无关任务")
    line = f"- `{entry.id}`（{title}）— Use when: {use} | Don't: {dont}"
    if entry.skills.strip():
        line += f" | Skills: {entry.skills.strip()}"
    return line


def rank_routing_entries(
    query: str,
    entries: dict[str, RoutingEntry],
    *,
    limit: int | None = None,
) -> list[tuple[int, str]]:
    tokens = skill_query_tokens(query)
    if not tokens:
        ordered = list(entries.keys())
        if limit is not None and limit > 0:
            ordered = ordered[:limit]
        return [(0, eid) for eid in ordered]

    scored: list[tuple[int, str]] = []
    for eid, entry in entries.items():
        use_l = (entry.use_when or "").lower()
        id_l = eid.lower()
        hay = routing_entry_haystack(entry)
        score = 0
        for t in tokens:
            if t in use_l:
                score += 3
            elif t in id_l:
                score += 2
            elif t in hay:
                score += 1
        if score > 0:
            scored.append((score, eid))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if limit is not None and limit > 0:
        scored = scored[:limit]
    return scored


def build_agents_catalog_text(*, enabled_ids: frozenset[str] | None = None) -> str:
    entries = load_agents_routing_md()
    lines = [agents_routing_md_text().split("\n", 1)[0], ""]
    for eid in entries:
        if eid == "orchestrator":
            continue
        if enabled_ids is not None and eid not in enabled_ids:
            continue
        lines.append(format_agent_route_line(entries[eid]))
    return "\n".join(lines)


def build_skills_routing_display(db) -> str:
    """skills.md 全文 + 发展技能自动合并段（管理页只读展示）。"""
    from app.skills.catalog import list_uploaded_skill_definitions

    lines = [skills_routing_md_text()]
    uploaded = list_uploaded_skill_definitions(db, include_disabled=False)
    if uploaded:
        lines.extend(["", "## 发展技能（自动合并 · 随上传包更新）", ""])
        for skill in sorted(uploaded, key=lambda s: s.name):
            use = (skill.use_when or skill.description or "用户点名该 Skill 或上下文匹配").strip()
            dont = (skill.dont_use_when or "任务与 Skill 无关时").strip()
            output = (skill.output or "按 SKILL.md 或脚本结论作答").strip()
            lines.extend(
                [
                    f"## {skill.name}",
                    f"- Use when: {use}",
                    f"- Don't use when: {dont}",
                    f"- Output: {output}",
                    "",
                ]
            )
    return "\n".join(lines).strip()


def build_agents_routing_display() -> str:
    """agents.md 全文（管理页只读展示）。"""
    return agents_routing_md_text()
