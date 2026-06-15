"""PageIndex 可选依赖桥接：索引依赖上游包，检索可读取本地 workspace JSON。"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PAGEINDEX_IMPORT_ERROR: str | None = None
_PAGEINDEX_SELFHOSTED = False

try:
    from pageindex import PageIndexClient  # type: ignore[import-untyped]

    _PAGEINDEX_SELFHOSTED = callable(getattr(PageIndexClient, "index", None))
    _PAGEINDEX_AVAILABLE = _PAGEINDEX_SELFHOSTED
    if not _PAGEINDEX_SELFHOSTED:
        _PAGEINDEX_IMPORT_ERROR = (
            "已安装 PyPI 版 pageindex（云端 SDK），缺少自托管 index()。"
            "请执行: pip install -e ./third_party/pageindex-upstream"
        )
except Exception as exc:  # pragma: no cover - optional dependency
    PageIndexClient = None  # type: ignore[assignment,misc]
    _PAGEINDEX_AVAILABLE = False
    _PAGEINDEX_IMPORT_ERROR = str(exc)


def pageindex_package_available() -> bool:
    return _PAGEINDEX_AVAILABLE


def pageindex_is_selfhosted() -> bool:
    return _PAGEINDEX_SELFHOSTED


def pageindex_import_error() -> str | None:
    return _PAGEINDEX_IMPORT_ERROR


def _litellm_model_name(base_url: str, model: str) -> str:
    """将平台模型名映射为 LiteLLM 可识别的 provider/model。"""
    base_lower = (base_url or "").lower()
    name = (model or "").strip()
    if not name:
        name = "deepseek-chat"
    if "/" in name and not name.startswith("openai/"):
        return name
    if "deepseek" in base_lower:
        return name if name.startswith("deepseek/") else f"deepseek/{name}"
    return name if name.startswith("openai/") else f"openai/{name}"


def configure_pageindex_llm_from_platform() -> tuple[str, str, str]:
    """把平台语言模型配置写入 LiteLLM 环境变量，返回 (key, base_url, litellm_model)。"""
    from app.config import get_settings
    from app.integrations.deepseek_client import is_configured, resolve_credentials

    settings = get_settings()
    model_override = (settings.pageindex_model or "").strip()

    if is_configured():
        key, base, model = resolve_credentials()
    else:
        key = (settings.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        base = (
            settings.deepseek_base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).strip().rstrip("/")
        model = (
            settings.deepseek_model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"
        ).strip()

    if not key:
        raise RuntimeError("语言模型未配置，无法运行 PageIndex 索引")

    litellm_model = model_override or _litellm_model_name(base, model)
    os.environ["OPENAI_API_KEY"] = key
    os.environ["DEEPSEEK_API_KEY"] = key
    if base:
        os.environ["OPENAI_API_BASE"] = base
    return key, base, litellm_model


def build_pageindex_client(*, workspace: Path, model: str | None = None) -> Any:
    if not _PAGEINDEX_AVAILABLE or PageIndexClient is None:
        raise RuntimeError(
            "未安装自托管 PageIndex。请在 platform 目录执行："
            "pip install -e ./third_party/pageindex-upstream"
        )
    api_key, _base, platform_model = configure_pageindex_llm_from_platform()
    use_model = (model or "").strip() or platform_model
    return PageIndexClient(
        api_key=api_key,
        model=use_model,
        workspace=str(workspace),
    )


def index_file_with_pageindex(
    *,
    workspace: Path,
    file_path: Path,
    model: str | None = None,
) -> str:
    client = build_pageindex_client(workspace=workspace, model=model)
    return str(client.index(str(file_path)))


def write_temp_file(content: bytes, file_name: str) -> Path:
    suffix = Path(file_name).suffix or ".bin"
    fd, raw_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    path = Path(raw_path)
    path.write_bytes(content)
    return path


_PAGEINDEX_DIRECT_SUFFIXES = frozenset({".pdf", ".md", ".markdown"})
_PAGEINDEX_CONVERT_SUFFIXES = frozenset({".txt", ".text", ".doc", ".docx", ".rtf"})
PAGEINDEX_SUPPORTED_SUFFIXES = _PAGEINDEX_DIRECT_SUFFIXES | _PAGEINDEX_CONVERT_SUFFIXES


def pageindex_supported_formats() -> list[str]:
    """供 UI / meta 展示的可索引格式。"""
    return ["pdf", "markdown", "word", "txt"]


def is_pageindex_supported_file(file_name: str) -> bool:
    return Path(file_name or "").suffix.lower() in PAGEINDEX_SUPPORTED_SUFFIXES


def prepare_pageindex_index_path(
    *,
    content: bytes,
    file_name: str,
    mime_type: str = "",
    title: str = "",
) -> tuple[Path, list[Path]]:
    """写入临时文件供 PageIndex index() 使用。

    PDF / Markdown 原样索引；Word / 纯文本先转为 PDF 再建树（便于页级引用预览）。
    返回 (索引用路径, 需清理的临时路径列表)。
    """
    name = (file_name or "").strip() or "document"
    suffix = Path(name).suffix.lower()
    cleanup: list[Path] = []

    if suffix in _PAGEINDEX_DIRECT_SUFFIXES:
        path = write_temp_file(content, name)
        cleanup.append(path)
        return path, cleanup

    if suffix in _PAGEINDEX_CONVERT_SUFFIXES:
        from app.integrations.html_document_export import convert_file_bytes_to_pdf_for_citation

        converted = convert_file_bytes_to_pdf_for_citation(
            name,
            content,
            mime_type,
            title=title or name.rsplit(".", 1)[0],
        )
        if not converted:
            raise ValueError(f"无法将「{name}」转为 PageIndex 可索引的 PDF")
        pdf_name, pdf_bytes, _ = converted
        path = write_temp_file(pdf_bytes, pdf_name)
        cleanup.append(path)
        return path, cleanup

    raise ValueError(f"不支持的 PageIndex 索引格式：{name}")


def load_pageindex_doc(workspace: Path, doc_id: str) -> dict | None:
    path = workspace / f"{doc_id}.json"
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 PageIndex 索引失败 %s: %s", doc_id, exc)
        return None


def count_tree_nodes(structure: Any) -> int:
    total = 0

    def walk(nodes: Any) -> None:
        nonlocal total
        if isinstance(nodes, dict):
            nodes = [nodes]
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            total += 1
            walk(node.get("nodes"))

    walk(structure)
    return total


def remove_fields(data: Any, *, fields: set[str]) -> Any:
    if isinstance(data, dict):
        return {
            k: remove_fields(v, fields=fields)
            for k, v in data.items()
            if k not in fields
        }
    if isinstance(data, list):
        return [remove_fields(item, fields=fields) for item in data]
    return data


def create_node_mapping(tree: Any) -> dict[str, dict]:
    mapping: dict[str, dict] = {}

    def walk(nodes: Any) -> None:
        if isinstance(nodes, dict):
            nodes = [nodes]
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("node_id")
            if node_id:
                mapping[str(node_id)] = node
            walk(node.get("nodes"))

    walk(tree)
    return mapping
