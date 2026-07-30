"""工具参数运行时校验 — 适配 LLM 输出特征。

提供 LLM 常见序列化错误的自动修正（JSON 字符串 → dict/list 等）。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError


def coerce_dict_field(value: object) -> dict[str, Any]:
    """LLM 常将 dict 参数序列化为 JSON 字符串；统一归一化为 dict。"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def coerce_list_field(value: object) -> list[Any]:
    """LLM 常将 list 参数序列化为 JSON 字符串；统一归一化为 list。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def coerce_string_list(value: object) -> list[str]:
    """将值统一转为字符串列表。"""
    raw = coerce_list_field(value)
    return [str(x).strip() for x in raw if x is not None and str(x).strip()]


def format_validation_error(exc: ValidationError, *, max_errors: int = 4) -> str:
    """将 Pydantic ValidationError 格式化为 LLM 友好的错误消息。"""
    parts: list[str] = []
    for err in exc.errors()[:max_errors]:
        loc = ".".join(str(x) for x in err.get("loc") or ())
        msg = str(err.get("msg") or "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "Invalid arguments: " + "; ".join(parts)
