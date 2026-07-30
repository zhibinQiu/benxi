"""能力缺口回执 — 无匹配 Skill 时的标准化错误结构。"""

from __future__ import annotations

from typing import Any

MISSING_CAPABILITY_CODE = 8001


def build_missing_capability_receipt(
    user_demand: str,
    *,
    missing_capability: tuple[str, ...],
    supported_capability: tuple[str, ...],
    match_kind: str = "none",
    max_similarity: float = 0.0,
) -> dict[str, Any]:
    return {
        "success": False,
        "code": MISSING_CAPABILITY_CODE,
        "msg": "当前平台无匹配能力完成该需求",
        "detail": {
            "user_demand": (user_demand or "").strip()[:1200],
            "match_kind": match_kind,
            "max_similarity": round(max_similarity, 4),
            "missing_capability": list(missing_capability),
            "supported_capability": list(supported_capability),
        },
    }
