"""AgentKit Knowledge — 知识库通用模块。

包含知识库文件夹挂载管理、检索优先级等通用工具。
"""

from app.agentkit.knowledge.mount import (
    KnowledgeMountEntry,
    list_mounts,
    add_mount,
    remove_mount,
    resolve_mounts_to_doc_ids,
)

__all__ = [
    "KnowledgeMountEntry",
    "list_mounts",
    "add_mount",
    "remove_mount",
    "resolve_mounts_to_doc_ids",
]
