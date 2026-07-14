"""工具 MD 定义热加载器 — 继承 agentkit 通用 MarkdownConfigLoader。

配置目录: backend/tools/definitions/<name>.md
修改 MD 文件后，下次 get_tool_description() 调用即时生效（mtime 检测）。
无 MD 文件时回退 TOOL_DEFINITIONS 中的硬编码描述。
"""

from __future__ import annotations

from app.agentkit.config import MarkdownConfigLoader


class _ToolDefLoader(MarkdownConfigLoader):
    """工具定义加载器：从 tools/definitions/*.md 读取描述。"""

    _CONFIG_DIR = "tools/definitions"
    _SCAN_INTERVAL = 2.0
    _SKIP_FRONTMATTER = True


# 全局单例
_loader = _ToolDefLoader()


def get_tool_description(tool_name: str) -> str | None:
    """返回工具 MD 描述，无 MD 文件时返回 None（调用方回退硬编码）。"""
    return _loader.get(tool_name)


def reload_tool_def(tool_name: str) -> bool:
    """强制重新加载单个工具定义，常用于调试。"""
    return _loader.reload(tool_name)


def tool_def_files_status() -> list[dict]:
    """返回所有已加载工具的 MD 文件状态。"""
    return _loader.status()


def tool_defs_routing_text() -> str:
    """返回 tools.md 路由目录文本（如存在）。"""
    return _loader.text()
