"""声明式工具注册表（ToolRegistry）—— 工具名 → 描述 + Pydantic 参数模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from agentkit_tools.schema import build_function_tool_spec


@dataclass(frozen=True)
class ToolDef:
    """单个工具的定义。

    Attributes:
        name: 工具唯一名（LLM 调用时使用）。
        description: 工具用途描述（LLM 理解用）。
        args_model: Pydantic BaseModel，定义工具参数结构。
        categories: 工具所属分类标签（可选，用于权限/分组）。
    """

    name: str
    description: str
    args_model: type[BaseModel]
    categories: frozenset[str] = field(default_factory=frozenset)


class ToolRegistry:
    """声明式工具注册表。

    用法：:

        registry = ToolRegistry()
        registry.register("web_search", "联网搜索", WebSearchArgs)
        spec = registry.build_specs()
        assert "web_search" in registry
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        *,
        categories: set[str] | None = None,
    ) -> ToolDef:
        """注册一个工具。

        Args:
            name: 工具唯一名。
            description: 工具用途描述。
            args_model: Pydantic BaseModel 参数模型。
            categories: 可选分类标签。
        Returns:
            创建的 ToolDef。
        Raises:
            ValueError: 工具已注册。
        """
        key = name.strip()
        if not key:
            raise ValueError("工具名不能为空")
        if key in self._tools:
            raise ValueError(f"工具已注册: {key}")
        defn = ToolDef(
            name=key,
            description=description.strip(),
            args_model=args_model,
            categories=frozenset(categories or set()),
        )
        self._tools[key] = defn
        return defn

    def get(self, name: str) -> ToolDef | None:
        """按名称查询工具定义。"""
        return self._tools.get(name.strip())

    def __contains__(self, name: str) -> bool:
        return name.strip() in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def names_by_category(self, *categories: str) -> tuple[str, ...]:
        """返回属于指定分类的工具名列表（任一匹配）。"""
        cats = set(categories)
        if not cats:
            return tuple(self._tools)
        return tuple(
            name for name, defn in self._tools.items()
            if cats & defn.categories
        )

    def build_specs(
        self,
        *,
        names: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """批量生成 OpenAI function calling 格式的 tool spec。

        Args:
            names: 可选工具名白名单，None 表示全部。
        Returns:
            OpenAI function calling spec 列表。
        """
        if names is not None:
            target = frozenset(names)
            defns = [d for d in self._tools.values() if d.name in target]
        else:
            defns = list(self._tools.values())
        return [
            build_function_tool_spec(
                name=d.name,
                description=d.description,
                args_model=d.args_model,
            )
            for d in defns
        ]
