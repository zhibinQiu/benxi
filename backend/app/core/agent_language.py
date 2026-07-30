"""智能体语言策略：最终回答跟用户语言，工作区思考优先中文。"""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def looks_like_chinese(text: str) -> bool:
    """粗判用户消息是否以中文为主（无文本时默认中文产品语境）。"""
    raw = (text or "").strip()
    if not raw:
        return True
    cjk = len(_CJK_RE.findall(raw))
    if cjk >= 2:
        return True
    latin = len(_LATIN_WORD_RE.findall(raw))
    if cjk == 0 and latin >= 3:
        return False
    return cjk >= latin


def assistant_language_rules(*, user_message: str = "") -> str:
    """注入 system 的语言约束。

    - 最终回答：自动对齐用户语言
    - 工作区可见思考/推理：尽量用简体中文（便于过程展示）
    """
    if looks_like_chinese(user_message):
        return (
            "【语言】最终回答使用简体中文（专有名词/技术术语可保留英文）。"
            "工作区展示的思考、推理、规划过程必须使用简体中文，禁止整段英文思考。"
        )
    return (
        "【Language】Write the final user-facing answer in the same language as the user. "
        "Prefer Simplified Chinese for workspace-visible thinking/reasoning/planning "
        "when possible; otherwise keep thinking in the user's language."
    )


def stamp_workflow_agent(
    data: dict,
    *,
    agent_id: str | None = None,
    loop_state: dict | None = None,
) -> dict:
    """为 workflow 事件补齐 agent_id / agent_title（已有字段不覆盖）。"""
    if not isinstance(data, dict):
        return data
    if data.get("agent_id") and data.get("agent_title"):
        return data
    aid = str(agent_id or data.get("agent_id") or "").strip()
    if not aid and isinstance(loop_state, dict):
        aid = str(loop_state.get("agent_id") or "").strip()
    if not aid:
        return data
    from app.core.agent_profiles import resolve_agent_title

    data["agent_id"] = aid
    if not str(data.get("agent_title") or "").strip():
        data["agent_title"] = resolve_agent_title(aid)
    return data
