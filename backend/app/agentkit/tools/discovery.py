"""agentkit-tools/discovery: 通用分层工具发现模式。

Hermes 风格的三层模型：

- **Core（第 1 层）**：始终可见的 `core_names` 白名单
- **Discovery（第 2 层）**：通过 `describe_tool` / `search_skills` 等发现工具
- **Unlocked（第 3 层）**：发现后按需解锁的工具

``ToolVisibility`` 管理这三层的合并，供平台 ``select_visible_tool_specs`` 使用。
"""

from __future__ import annotations

from typing import Any

from app.agentkit.loop.state import LoopState


class ToolVisibility:
    """工具可见性管理器。

    用法::

        visibility = ToolVisibility(core_names={"web_search", "send_notification"})
        visibility.register_unlocked(["create_library_document"])
        is_visible = visibility.is_visible("create_library_document")  # True
    """

    def __init__(
        self,
        core_names: set[str] | frozenset[str] | None = None,
    ) -> None:
        self._core: set[str] = set(core_names or frozenset())
        self._unlocked: set[str] = set()

    # ── 核心 API ────────────────────────────────────────────────────────

    @property
    def core_names(self) -> frozenset[str]:
        """始终可见的工具名集合（只读）。"""
        return frozenset(self._core)

    @property
    def unlocked(self) -> frozenset[str]:
        """已解锁的工具名集合。"""
        return frozenset(self._unlocked)

    @property
    def visible_names(self) -> frozenset[str]:
        """全部可见工具名 = 核心 + 已解锁。"""
        return frozenset(self._core | self._unlocked)

    def is_visible(self, name: str) -> bool:
        """判断工具是否可见。"""
        return (name or "").strip() in self.visible_names

    def register_unlocked(self, names: list[str]) -> None:
        """注册一批已解锁工具（describe_tool 成功后调用）。"""
        for n in names:
            s = (n or "").strip()
            if s:
                self._unlocked.add(s)

    def reset_unlocked(self) -> None:
        """清空已解锁集（切换会话等场景）。"""
        self._unlocked.clear()

    # ── 序列化 ──────────────────────────────────────────────────────────

    def to_loop_state(self) -> dict[str, Any]:
        """转为 loop_state 字典（与现有系统兼容）。"""
        return {"unlocked_tools": set(self._unlocked)}

    @classmethod
    def from_loop_state(
        cls,
        core_names: set[str] | frozenset[str] | None,
        loop_state: LoopState | None = None,
    ) -> "ToolVisibility":
        """从 loop_state 字典恢复可见性。"""
        vis = cls(core_names=core_names)
        if loop_state:
            raw = loop_state.get("unlocked_tools")
            if raw:
                vis.register_unlocked(list(raw))
        return vis

    @classmethod
    def from_loop_state_dict(
        cls,
        core_names: set[str] | frozenset[str] | None,
        loop_state: LoopState | None = None,
    ) -> "ToolVisibility":
        """兼容旧版：loop_state 可能是 None。"""
        return cls.from_loop_state(core_names, loop_state)


# ── 工具函数 ────────────────────────────────────────────────────────────────

def register_unlocked_tools(
    loop_state: LoopState | None,
    names: list[str],
) -> None:
    """兼容现有系统的 register_unlocked_tools（原地修改 loop_state）。"""
    if loop_state is None:
        return
    bucket: set[str] = loop_state.setdefault("unlocked_tools", set())
    for name in names:
        n = (str(name) or "").strip()
        if n:
            bucket.add(n)
