"""系统说明文档：从仓库 docs 目录读取 Markdown 与静态资源。"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

from app.config import get_settings

_DOC_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HTML_IMG_RE = re.compile(
    r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'][^>]*>)',
    re.IGNORECASE,
)
_HTML_A_RE = re.compile(
    r'(<a\b[^>]*\bhref=["\'])([^"\']+)(["\'][^>]*>)',
    re.IGNORECASE,
)
_ADMONITION_RE = re.compile(
    r'^!!!\s+(\w+)(?:\s+"([^"]*)")?\s*\n((?:    .+\n?)*)',
    re.MULTILINE,
)
_ADMONITION_ICONS = {
    "warning": "⚠️",
    "note": "ℹ️",
    "tip": "💡",
    "info": "ℹ️",
    "danger": "⛔",
}


def _repo_root() -> Path:
    settings = get_settings()
    if settings.system_docs_root:
        root = Path(settings.system_docs_root).expanduser().resolve()
        if root.is_dir():
            return root

    bundled = Path("/app/system-docs")
    if (bundled / "docs").is_dir() or (bundled / "运维部署指南.md").is_file():
        return bundled

    service_file = Path(__file__).resolve()
    repo_candidate = service_file.parents[3]
    if (repo_candidate / "docs").is_dir():
        return repo_candidate

    platform_root = service_file.parents[2]
    nested = platform_root / "system-docs"
    if nested.is_dir():
        return nested

    if bundled.is_dir():
        return bundled

    return repo_candidate


def _catalog_raw() -> list[dict[str, Any]]:
    return [
        {
            "key": "ops",
            "title": "运维部署",
            "children": [
                {"key": "ops-main", "title": "运维部署指南", "path": "运维部署指南.md"},
                {"key": "ops-readme", "title": "文档索引", "path": "docs/zh/operations/README.md"},
                {"key": "ops-arch", "title": "系统架构", "path": "docs/zh/operations/architecture.md"},
                {"key": "ops-docker", "title": "Docker 容器说明", "path": "docs/zh/operations/docker-services.md"},
                {"key": "ops-network", "title": "网络与反代拓扑", "path": "docs/zh/operations/network-topology.md"},
                {"key": "ops-deploy", "title": "部署指南", "path": "docs/zh/operations/deployment.md"},
                {"key": "ops-server-deps", "title": "远程依赖开发", "path": "docs/zh/operations/server-deps.md"},
                {"key": "ops-single-server", "title": "单机迁移与热重载", "path": "docs/zh/operations/single-server-migration.md"},
                {"key": "ops-features", "title": "功能实现说明", "path": "docs/zh/operations/feature-implementation.md"},
                {"key": "ops-config", "title": "配置说明", "path": "docs/zh/operations/configuration.md"},
                {"key": "ops-db", "title": "数据库迁移", "path": "docs/zh/operations/database-migration.md"},
                {"key": "ops-perm", "title": "权限与账户", "path": "docs/zh/operations/permissions.md"},
                {"key": "ops-test", "title": "测试", "path": "docs/zh/operations/testing.md"},
                {"key": "ops-upgrade", "title": "升级", "path": "docs/zh/operations/upgrade.md"},
                {"key": "ops-security", "title": "安全", "path": "docs/zh/operations/security.md"},
                {"key": "ops-manual", "title": "日常操作手册", "path": "docs/zh/operations/operations-manual.md"},
            ],
        },
        {
            "key": "platform",
            "title": "平台说明",
            "children": [
                {"key": "plat-plugins", "title": "功能插件", "path": "docs/zh/platform/feature-plugins.md"},
                {"key": "plat-perm", "title": "权限模型与文档分级", "path": "docs/zh/platform/permission-model.md"},
                {"key": "plat-speech", "title": "语音模型", "path": "docs/zh/platform/speech-models.md"},
                {"key": "plat-compare", "title": "文档对比产品设计", "path": "docs/zh/platform/doc-compare-product-design.md"},
            ],
        },
        {
            "key": "dev",
            "title": "架构与开发",
            "children": [
                {"key": "dev-arch", "title": "系统架构概览", "path": "docs/zh/development/system-architecture-overview.md"},
                {"key": "dev-stack", "title": "Stack 命令速查", "path": "docs/zh/development/stack-deployment.md"},
                {"key": "dev-layer", "title": "分层架构", "path": "docs/zh/development/layered-architecture.md"},
                {"key": "dev-platform", "title": "平台架构索引", "path": "docs/zh/development/platform-architecture.md"},
                {"key": "dev-api", "title": "REST API", "path": "docs/zh/development/rest-api.md"},
                {"key": "impl-api", "title": "API 约定", "path": "docs/zh/implementation/api-conventions.md"},
                {"key": "impl-jobs", "title": "异步与任务", "path": "docs/zh/implementation/async-and-jobs.md"},
                {"key": "impl-docs", "title": "文档中心实现", "path": "docs/zh/implementation/documents-implementation.md"},
                {"key": "impl-knowledge", "title": "知识库实现", "path": "docs/zh/implementation/knowledge-implementation.md"},
            ],
        },
        {
            "key": "release",
            "title": "版本发布",
            "children": [
                {"key": "release-notes", "title": "RELEASE", "path": "RELEASE.md"},
            ],
        },
    ]


def _allowed_paths() -> set[str]:
    paths: set[str] = set()
    for group in _catalog_raw():
        for item in group.get("children") or []:
            path = str(item.get("path") or "").strip()
            if path:
                paths.add(path.replace("\\", "/"))
    return paths


def _normalize_doc_path(raw: str) -> str:
    path = (raw or "").strip().replace("\\", "/").lstrip("/")
    if not path or ".." in path.split("/"):
        raise ValueError("invalid path")
    if path not in _allowed_paths():
        raise ValueError("path not allowed")
    return path


def _resolve_asset_path(doc_path: str, asset_ref: str) -> str | None:
    ref = (asset_ref or "").strip()
    if not ref or ref.startswith("#"):
        return None
    if ref.startswith(("http://", "https://", "data:", "mailto:")):
        return ref
    doc_dir = Path(doc_path).parent
    if ref.startswith("/"):
        resolved = ref.lstrip("/")
    else:
        resolved = str((doc_dir / ref).as_posix())
    resolved = Path(resolved).as_posix()
    if ".." in resolved.split("/"):
        return None
    root = _repo_root()
    full = (root / resolved).resolve()
    try:
        full.relative_to(root.resolve())
    except ValueError:
        return None
    if not full.is_file():
        return None
    return resolved


def _asset_api_path(resolved: str) -> str:
    from urllib.parse import quote

    return f"/api/v1/system/docs/assets/{quote(resolved, safe='/')}"


def _convert_mkdocs_admonitions(md: str) -> str:
    def repl(match: re.Match[str]) -> str:
        kind = match.group(1)
        title = (match.group(2) or kind).strip()
        body = match.group(3) or ""
        lines = []
        for line in body.splitlines():
            lines.append(line[4:] if line.startswith("    ") else line)
        content = "\n".join(lines).strip()
        icon = _ADMONITION_ICONS.get(kind.lower(), "📌")
        quoted = [f"> **{icon} {title}**", ">"]
        quoted.extend(f"> {ln}" if ln else ">" for ln in content.splitlines())
        return "\n".join(quoted) + "\n"

    return _ADMONITION_RE.sub(repl, md)


def _rewrite_markdown_links(md: str, doc_path: str) -> str:
    def repl_img(match: re.Match[str]) -> str:
        alt, url = match.group(1), match.group(2).strip()
        resolved = _resolve_asset_path(doc_path, url)
        if not resolved:
            return match.group(0)
        if resolved.startswith(("http://", "https://")):
            return f"![{alt}]({resolved})"
        return f"![{alt}]({_asset_api_path(resolved)})"

    md = _DOC_LINK_RE.sub(repl_img, md)

    def repl_html_img(match: re.Match[str]) -> str:
        prefix, url, suffix = match.group(1), match.group(2).strip(), match.group(3)
        resolved = _resolve_asset_path(doc_path, url)
        if not resolved:
            return match.group(0)
        href = resolved if resolved.startswith(("http://", "https://")) else _asset_api_path(resolved)
        return f"{prefix}{href}{suffix}"

    md = _HTML_IMG_RE.sub(repl_html_img, md)
    return md


def list_doc_catalog() -> list[dict[str, Any]]:
    root = _repo_root()
    catalog: list[dict[str, Any]] = []
    for group in _catalog_raw():
        children = []
        for item in group.get("children") or []:
            path = str(item.get("path") or "").strip()
            full = root / path
            children.append(
                {
                    "key": item["key"],
                    "title": item["title"],
                    "path": path,
                    "available": full.is_file(),
                }
            )
        catalog.append({"key": group["key"], "title": group["title"], "children": children})
    return catalog


def read_doc_content(doc_path: str) -> dict[str, str]:
    path = _normalize_doc_path(doc_path)
    root = _repo_root()
    full = root / path
    if not full.is_file():
        raise FileNotFoundError(path)
    raw = full.read_text(encoding="utf-8")
    content = _convert_mkdocs_admonitions(raw)
    content = _rewrite_markdown_links(content, path)
    title = path.rsplit("/", 1)[-1]
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return {"path": path, "title": title, "content": content}


def resolve_doc_asset(asset_path: str) -> tuple[Path, str]:
    normalized = (asset_path or "").strip().replace("\\", "/").lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise ValueError("invalid asset path")
    root = _repo_root().resolve()
    full = (root / normalized).resolve()
    full.relative_to(root)
    if not full.is_file():
        raise FileNotFoundError(normalized)
    mime, _ = mimetypes.guess_type(full.name)
    return full, mime or "application/octet-stream"
