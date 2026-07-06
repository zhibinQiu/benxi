"""workflow.json 确定性回放（不依赖录制时的 ref，按 role/name 重新匹配）。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.integrations.browser_automation.playwright_session import (
    BrowserSessionManager,
    BrowserSessionState,
)


_PARAM_RE = re.compile(r"\{\{(\w+)\}\}")


def apply_params(value: str, params: dict[str, str]) -> str:
    text = str(value or "")

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(params.get(key, match.group(0)))

    return _PARAM_RE.sub(_repl, text)


def _find_ref_by_hint(snapshot: dict[str, Any], hint: dict[str, Any]) -> str | None:
    role = str(hint.get("role") or "").lower()
    name = str(hint.get("name") or "").strip().lower()
    ref_hint = str(hint.get("ref") or "").strip()
    refs = snapshot.get("refs") or []
    if ref_hint:
        for item in refs:
            if item.get("ref") == ref_hint:
                return ref_hint
    for item in refs:
        item_role = str(item.get("role") or "").lower()
        item_name = str(item.get("name") or "").strip().lower()
        if role and item_role != role:
            continue
        if name and name not in item_name and item_name not in name:
            continue
        return str(item.get("ref") or "")
    return None


async def replay_workflow_steps(
    mgr: BrowserSessionManager,
    state: BrowserSessionState,
    steps: list[dict[str, Any]],
    params: dict[str, str],
    *,
    allowed_domains: str = "",
    screenshot_max_kb: int = 800,
) -> dict[str, Any]:
    """回放步骤序列，返回最终页面信息与可选截图 bytes。"""
    last_shot: bytes | None = None
    logs: list[str] = []

    for idx, step in enumerate(steps):
        action = str(step.get("action") or "").strip()
        if action == "navigate":
            url = apply_params(str(step.get("url") or ""), params)
            result = await mgr.navigate(state, url, allowed_domains=allowed_domains)
            logs.append(f"#{idx + 1} navigate → {result.get('title')}")
            continue

        snapshot = await mgr.snapshot(state)

        if action == "click":
            ref = str(step.get("ref") or "")
            if not state.ref_map.get(ref):
                ref = _find_ref_by_hint(snapshot, step) or ref
            await mgr.click(state, ref)
            logs.append(f"#{idx + 1} click {ref}")
        elif action == "type":
            ref = str(step.get("ref") or "")
            if not state.ref_map.get(ref):
                ref = _find_ref_by_hint(snapshot, step) or ref
            text = apply_params(str(step.get("text") or ""), params)
            await mgr.type_text(
                state,
                ref,
                text,
                submit=bool(step.get("submit")),
            )
            logs.append(f"#{idx + 1} type {ref}")
        elif action == "fill":
            fields = []
            for item in step.get("fields") or []:
                if not isinstance(item, dict):
                    continue
                ref = str(item.get("ref") or "")
                if not state.ref_map.get(ref):
                    ref = _find_ref_by_hint(snapshot, item) or ref
                fields.append(
                    {
                        "ref": ref,
                        "value": apply_params(str(item.get("value") or ""), params),
                    }
                )
            await mgr.fill_fields(state, fields)
            logs.append(f"#{idx + 1} fill x{len(fields)}")
        elif action == "screenshot":
            last_shot, _, _ = await mgr.screenshot_png(
                state,
                full_page=bool(step.get("full_page")),
                max_kb=screenshot_max_kb,
            )
            logs.append(f"#{idx + 1} screenshot")
        else:
            logs.append(f"#{idx + 1} skip unknown action: {action}")

    title = ""
    url = ""
    if state.page:
        title = await state.page.title()
        url = state.page.url
    return {
        "url": url,
        "title": title,
        "logs": logs,
        "screenshot_png": last_shot,
    }


def parse_replay_params(argv: list[str]) -> dict[str, str]:
    """解析 key=value 或 JSON 对象参数。"""
    if not argv:
        return {}
    if len(argv) == 1 and argv[0].strip().startswith("{"):
        try:
            body = json.loads(argv[0])
            if isinstance(body, dict):
                return {str(k): str(v) for k, v in body.items()}
        except json.JSONDecodeError:
            pass
    out: dict[str, str] = {}
    for arg in argv:
        if "=" in arg:
            k, v = arg.split("=", 1)
            out[k.strip()] = v.strip()
    return out
