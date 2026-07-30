"""Pydantic → 紧凑 JSON Schema → OpenAI function calling spec。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def compact_tool_parameters_schema(model: type[BaseModel]) -> dict[str, Any]:
    """从 Pydantic Model 生成紧凑 JSON Schema（移除冗余 title/description）。

    产物直接嵌入 LLM function calling 的 ``parameters`` 字段。

    Args:
        model: Pydantic BaseModel 子类。
    Returns:
        紧凑 JSON Schema dict（type + properties + 可选 required + $defs）。
    """
    schema = model.model_json_schema(mode="validation")
    props = schema.get("properties")
    if isinstance(props, dict):
        for spec in props.values():
            if isinstance(spec, dict):
                spec.pop("title", None)
                spec.pop("description", None)
    out: dict[str, Any] = {
        "type": "object",
        "properties": props or {},
    }
    required = schema.get("required")
    if required:
        out["required"] = required
    defs = schema.get("$defs")
    if defs:
        for item in defs.values():
            if isinstance(item, dict) and "properties" in item:
                for spec in item["properties"].values():
                    if isinstance(spec, dict):
                        spec.pop("title", None)
                        spec.pop("description", None)
        out["$defs"] = defs
    return out


def build_function_tool_spec(
    *,
    name: str,
    description: str,
    args_model: type[BaseModel],
) -> dict[str, Any]:
    """构建 OpenAI function calling 格式的 tool spec。

    Args:
        name: 工具名。
        description: 工具描述。
        args_model: Pydantic BaseModel 参数模型。
    Returns:
        符合 OpenAI tools 数组元素的 dict。
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": compact_tool_parameters_schema(args_model),
        },
    }
