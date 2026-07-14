"""ToolCenter 注册表 — 从现有原子 Tool 定义引导 descriptor。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.agentkit.tools.schema import compact_tool_parameters_schema as tool_parameters_schema
from app.core.agent_tool_args import TOOL_DEFINITIONS
from app.core.tool_def_loader import get_tool_description
from app.core.tool_skill_taxonomy import GLOBAL_ATOMIC_TOOL_NAMES
from app.core.tool_skill_taxonomy import ToolCategory, _TOOL_CATEGORIES
from app.tool_center.schemas import ToolDescriptor

_CATEGORY_TOOL_TYPE: dict[ToolCategory, str] = {
    ToolCategory.WEB: "io_http",
    ToolCategory.KNOWLEDGE: "io_knowledge",
    ToolCategory.GRAPH: "io_graph",
    ToolCategory.DOCUMENT: "io_document",
    ToolCategory.PLATFORM: "io_platform",
    ToolCategory.BROWSER: "io_browser",
    ToolCategory.ADMIN: "io_admin",
    ToolCategory.MEMORY: "io_memory",
}

def _default_output_schema(category: ToolCategory | None) -> dict[str, Any]:
    if category == ToolCategory.WEB:
        return {"items": "list[dict]", "query": "str"}
    if category == ToolCategory.KNOWLEDGE:
        return {"hits": "list[dict]", "mode": "str"}
    if category == ToolCategory.GRAPH:
        return {"context_text": "str", "entities": "list[dict]"}
    if category == ToolCategory.DOCUMENT:
        return {"result": "dict", "summary": "str"}
    return {"payload": "dict", "summary": "str"}


def _build_input_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = tool_parameters_schema(model)
    props = schema.get("properties") or {}
    out_props: dict[str, Any] = {}
    for key, spec in props.items():
        if isinstance(spec, dict):
            entry = {k: v for k, v in spec.items() if k in ("type", "default", "enum", "items", "format")}
            if "description" in spec:
                entry["desc"] = spec["description"]
            out_props[key] = entry
        else:
            out_props[key] = spec
    return {
        "type": "object",
        "required": list(schema.get("required") or []),
        "properties": out_props,
    }


class ToolCenter:
    """全局 Tool 注册中心（无业务状态）。"""

    def __init__(self) -> None:
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._input_models: dict[str, type[BaseModel]] = {}
        self._bootstrapped = False

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        for tool_id in sorted(GLOBAL_ATOMIC_TOOL_NAMES):
            if tool_id not in TOOL_DEFINITIONS:
                continue
            desc_text, model = TOOL_DEFINITIONS[tool_id]
            category = _TOOL_CATEGORIES.get(tool_id)
            tool_type = _CATEGORY_TOOL_TYPE.get(category, "io_generic") if category else "io_generic"
            md_desc = get_tool_description(tool_id)
            doc_text = md_desc if md_desc else ""
            descriptor = ToolDescriptor(
                tool_id=tool_id,
                tool_type=tool_type,
                description=desc_text,
                doc_text=doc_text,
                input_schema=_build_input_schema(model),
                output_schema=_default_output_schema(category),
            )
            self._descriptors[tool_id] = descriptor
            self._input_models[tool_id] = model
        self._bootstrapped = True

    def get(self, tool_id: str) -> ToolDescriptor | None:
        self.bootstrap()
        return self._descriptors.get((tool_id or "").strip())

    def input_model(self, tool_id: str) -> type[BaseModel] | None:
        self.bootstrap()
        return self._input_models.get((tool_id or "").strip())

    def list_descriptors(self) -> list[ToolDescriptor]:
        self.bootstrap()
        return list(self._descriptors.values())

    def register(self, descriptor: ToolDescriptor, *, input_model: type[BaseModel] | None = None) -> None:
        """扩展注册（如未来 db_mysql_query）。"""
        self.bootstrap()
        self._descriptors[descriptor.tool_id] = descriptor
        if input_model is not None:
            self._input_models[descriptor.tool_id] = input_model


_center = ToolCenter()


def get_tool_center() -> ToolCenter:
    return _center


def list_tool_descriptors() -> list[ToolDescriptor]:
    return get_tool_center().list_descriptors()
