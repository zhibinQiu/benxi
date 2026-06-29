"""平台用户/部门列表 — 供 Agent 确定性回复，避免 LLM 编造数据。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org import Department


def summarize_user_list(data: dict[str, Any]) -> str:
    total = int(data.get("total") or 0)
    items = data.get("items") or []
    shown = len(items)
    if total <= shown:
        return f"共 {total} 个用户"
    page = int(data.get("page") or 1)
    return f"共 {total} 个用户（第 {page} 页展示 {shown} 条）"


def format_user_list_markdown(db: Session, data: dict[str, Any]) -> str:
    items = list(data.get("items") or [])
    total = int(data.get("total") or len(items))
    page = int(data.get("page") or 1)
    page_size = int(data.get("page_size") or max(len(items), 1))

    dept_ids: set[uuid.UUID] = set()
    for row in items:
        for raw in row.get("department_ids") or []:
            try:
                dept_ids.add(raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                continue
    dept_names: dict[uuid.UUID, str] = {}
    if dept_ids:
        for dept in db.scalars(
            select(Department).where(Department.id.in_(dept_ids))
        ).all():
            dept_names[dept.id] = dept.name

    lines = [f"系统中共有 **{total}** 个用户。", ""]
    if total > len(items):
        lines.append(
            f"> 当前为第 {page} 页（每页 {page_size} 条），"
            f"以下列出 {len(items)} 条；如需全部可说明「列出全部用户」。"
        )
        lines.append("")

    lines.extend(
        [
            "| 用户名 | 显示名 | 邮箱 | 手机 | 部门 | 角色 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in items:
        dept_labels = []
        for raw in row.get("department_ids") or []:
            try:
                uid = raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
            except (TypeError, ValueError):
                dept_labels.append("—")
                continue
            dept_labels.append(dept_names.get(uid, "—"))
        dept_label = "、".join(dept_labels) if dept_labels else "—"
        roles = "、".join(str(x) for x in (row.get("role_names") or [])) or "—"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("username") or "—"),
                    str(row.get("display_name") or "—"),
                    str(row.get("email") or "—"),
                    str(row.get("phone") or "—"),
                    dept_label,
                    roles,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def format_department_list_markdown(items: list[dict[str, Any]]) -> str:
    rows = list(items or [])
    lines = [f"系统中共有 **{len(rows)}** 个部门。", ""]
    if not rows:
        return lines[0]
    lines.extend(["| 部门名称 | 上级部门 ID |", "| --- | --- |"])
    name_by_id = {str(r.get("id") or ""): str(r.get("name") or "") for r in rows}
    for row in sorted(rows, key=lambda r: str(r.get("name") or "")):
        parent_id = str(row.get("parent_id") or "").strip()
        parent_label = name_by_id.get(parent_id, "—") if parent_id else "—"
        lines.append(f"| {row.get('name') or '—'} | {parent_label} |")
    return "\n".join(lines)


def capture_admin_list_deterministic_reply(
    db: Session,
    *,
    tool_name: str,
    result_text: str,
    loop_state: dict[str, Any] | None,
) -> None:
    """工具成功后写入 deterministic_reply，供 synthesize 直接输出。"""
    if loop_state is None:
        return
    try:
        import json

        body = json.loads(result_text)
    except json.JSONDecodeError:
        return
    if not isinstance(body, dict) or not body.get("ok"):
        return
    data = body.get("data")

    if tool_name == "list_users" and isinstance(data, dict):
        loop_state["deterministic_reply"] = format_user_list_markdown(db, data)
        return

    if tool_name == "list_departments":
        items = data if isinstance(data, list) else (data or {}).get("items")
        if isinstance(items, list):
            loop_state["deterministic_reply"] = format_department_list_markdown(items)
