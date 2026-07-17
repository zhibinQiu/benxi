"""工具参数运行时校验 — 适配 LLM 输出特征。

提供 LLM 常见序列化错误的自动修正（JSON 字符串 → dict/list 等）。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.agentkit.tools.registry import ToolRegistry


# ── 通用字段强制类型转换 ──────────────────────────────────


def coerce_dict_field(value: object) -> dict[str, Any]:
    """LLM 常将 dict 参数序列化为 JSON 字符串；统一归一化为 dict。

    适用于 ``@field_validator(..., mode="before")``。
    """
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
    """LLM 常将 list 参数序列化为 JSON 字符串；统一归一化为 list。

    适用于 ``@field_validator(..., mode="before")``。
    """
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
    """将值统一转为字符串列表。

    接受 list[str]、JSON 数组字符串、单个字符串的包装。
    """
    raw = coerce_list_field(value)
    return [str(x).strip() for x in raw if x is not None and str(x).strip()]


def format_validation_error(exc: ValidationError, *, max_errors: int = 4) -> str:
    """将 Pydantic ValidationError 格式化为 LLM 友好的错误消息。

    Args:
        exc: 捕获的 ValidationError。
        max_errors: 最多显示前 N 条错误（默认 4）。
    Returns:
        形如 "参数无效：query: 字符串长度不足；max_items: 输入超出范围"。
    """
    parts: list[str] = []
    for err in exc.errors()[:max_errors]:
        loc = ".".join(str(x) for x in err.get("loc") or ())
        msg = str(err.get("msg") or "无效")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "参数无效：" + "；".join(parts)


def validate_tool_arguments(
    registry: ToolRegistry,
    tool_name: str,
    raw_args: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """校验工具参数的完整流程：查注册表 → Pydantic 校验 → 返回清理后 dict。

    典型用法：:

        cleaned, error = validate_tool_arguments(registry, "web_search", raw)
        if error:
            reply = f"工具调用失败：{error}"
        else:
            result = await execute_tool("web_search", cleaned)

    Args:
        registry: 已注册工具的 ToolRegistry。
        tool_name: LLM 调用的工具名。
        raw_args: LLM 传入的原始参数字典（可为 None）。
    Returns:
        (cleaned_args_dict | None, error_str | None)。
        - 成功时 cleaned 为 dict、error 为 None。
        - 失败时 cleaned 为 None、error 为 LLM 友好的错误描述。
    """
    name = (tool_name or "").strip()
    defn = registry.get(name)
    if defn is None:
        return None, f"未注册工具: {name}"

    payload = dict(raw_args or {})
    try:
        model = defn.args_model.model_validate(payload)
        return model.model_dump(exclude_none=True), None
    except ValidationError as exc:
        return None, format_validation_error(exc)
