"""PageIndex 可选依赖桥接：索引依赖上游包，检索可读取本地 workspace JSON。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PAGEINDEX_IMPORT_ERROR: str | None = None
_PAGEINDEX_SELFHOSTED = False
_PAGEINDEX_AVAILABLE = False

PageIndexClient = None  # type: ignore[assignment,misc]

try:
    from pageindex import PageIndexClient as _PageIndexClient  # type: ignore[import-untyped]

    PageIndexClient = _PageIndexClient
    _PAGEINDEX_SELFHOSTED = callable(getattr(PageIndexClient, "index", None))
except Exception as exc:  # pragma: no cover - optional dependency
    _PAGEINDEX_IMPORT_ERROR = str(exc)


def _pageindex_module_dir() -> Path | None:
    try:
        import pageindex as pageindex_mod

        return Path(pageindex_mod.__file__).resolve().parent
    except Exception:
        return None


def _vendored_pageindex_config_sources() -> list[Path]:
    sources: list[Path] = []
    platform_roots: list[Path] = [Path(__file__).resolve().parents[2], Path("/app")]
    env_root = (os.environ.get("PLATFORM_ROOT") or os.environ.get("PLATFORM") or "").strip()
    if env_root:
        platform_roots.append(Path(env_root))
    for root in platform_roots:
        candidate = root / "third_party/pageindex/pageindex/config.yaml"
        if candidate not in sources:
            sources.append(candidate)
    return sources


def _bootstrap_pageindex_config(mod_dir: Path | None) -> bool:
    """安装包缺 config.yaml 时，从仓库内 third_party 拷贝补齐。"""
    if not mod_dir:
        return False
    target = mod_dir / "config.yaml"
    if target.is_file():
        return True
    for src in _vendored_pageindex_config_sources():
        if not src.is_file():
            continue
        try:
            shutil.copy2(src, target)
            logger.info("已补齐 PageIndex 配置文件：%s -> %s", src, target)
            return True
        except OSError as exc:
            logger.warning("补齐 PageIndex 配置文件失败 src=%s: %s", src, exc)
    return target.is_file()


def _refresh_pageindex_state() -> None:
    global _PAGEINDEX_AVAILABLE, _PAGEINDEX_IMPORT_ERROR

    if PageIndexClient is None:
        _PAGEINDEX_AVAILABLE = False
        return
    if not _PAGEINDEX_SELFHOSTED:
        _PAGEINDEX_AVAILABLE = False
        if not (_PAGEINDEX_IMPORT_ERROR or "").strip():
            _PAGEINDEX_IMPORT_ERROR = (
                "已安装 PyPI 版 pageindex（云端 SDK），缺少自托管 index()。"
                "请执行: pip install -e ./third_party/pageindex"
            )
        return

    mod_dir = _pageindex_module_dir()
    config_ready = _bootstrap_pageindex_config(mod_dir)
    _PAGEINDEX_AVAILABLE = config_ready
    if not config_ready:
        _PAGEINDEX_IMPORT_ERROR = "PageIndex 自托管包未完整安装（缺少 config.yaml）。"


_refresh_pageindex_state()


def pageindex_package_available() -> bool:
    if not _PAGEINDEX_AVAILABLE and _PAGEINDEX_SELFHOSTED and PageIndexClient is not None:
        _refresh_pageindex_state()
    return _PAGEINDEX_AVAILABLE


def pageindex_install_hint() -> str:
    return 'pip install -e ".[pageindex]"'


def pageindex_install_command() -> str:
    return f"{pageindex_install_hint()}  # 在 platform 目录执行"


def pageindex_stack_block_reason() -> str | None:
    """PageIndex 索引/重索引前检查：开关、自托管包、语言模型。"""
    from app.config import get_settings
    from app.integrations.deepseek_client import is_configured

    if not get_settings().pageindex_enabled:
        return "文档索引功能未启用，请联系管理员"
    if not pageindex_package_available():
        err = (_PAGEINDEX_IMPORT_ERROR or "").strip()
        if "config.yaml" in err or "配置文件" in err:
            return (
                "PageIndex 索引服务未完整安装（缺少配置文件）。"
                "请联系管理员重新构建镜像，或在 platform 目录执行 "
                f"{pageindex_install_hint()}"
            )
        if "PyPI" in err or "自托管" in err:
            return (
                "PageIndex 自托管包未正确安装。"
                f"请在 platform 目录执行：{pageindex_install_hint()}"
            )
        return (
            "文档索引服务未就绪：未安装 PageIndex 自托管包。"
            f"请在 platform 目录执行：{pageindex_install_hint()}"
        )
    if not is_configured():
        return "语言模型未配置，无法建立文档索引，请联系管理员"
    return None


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
    from app.integrations.deepseek_client import resolve_credentials

    settings = get_settings()
    model_override = (settings.pageindex_model or "").strip()
    key, base, model = resolve_credentials()
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


def _pdf_file_to_markdown_temp(pdf_path: Path, *, title: str = "") -> Path | None:
    """PDF 文本提取为 Markdown，供 PageIndex PDF 目录解析失败时兜底。"""
    try:
        import PyPDF2
    except ImportError:
        return None
    try:
        with pdf_path.open("rb") as f:
            reader = PyPDF2.PdfReader(f)
            parts: list[str] = []
            doc_title = (title or pdf_path.stem).strip()
            if doc_title:
                parts.append(f"# {doc_title}")
            for i, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                parts.append(f"## 第 {i} 页")
                parts.append(text)
            body = "\n\n".join(parts).strip()
            if len(body) < 40:
                return None
            md_name = f"{pdf_path.stem}.md" if pdf_path.suffix else "document.md"
            return write_temp_file(body.encode("utf-8"), md_name)
    except Exception as exc:
        logger.warning("PDF 转 Markdown 兜底失败 %s: %s", pdf_path, exc)
        return None


def _pdf_pageindex_should_fallback_to_markdown(exc: BaseException) -> bool:
    """PDF 结构索引失败时，是否改用 Markdown 管线（md_to_tree，不依赖 PDF 目录 LLM）。"""
    err = str(exc).lower()
    markers = (
        "toc transformation",
        "table of contents",
        "processing failed",
        "toc_detected",
        "failed to extract json",
        "failed to parse json",
    )
    return any(marker in err for marker in markers)


def index_file_with_pageindex(
    *,
    workspace: Path,
    file_path: Path,
    model: str | None = None,
) -> str:
    client = build_pageindex_client(workspace=workspace, model=model)
    path = Path(file_path)
    try:
        return str(client.index(str(path)))
    except Exception as exc:
        if path.suffix.lower() == ".pdf" and _pdf_pageindex_should_fallback_to_markdown(
            exc
        ):
            md_path = _pdf_file_to_markdown_temp(path, title=path.stem)
            if md_path:
                try:
                    logger.warning(
                        "PageIndex PDF 结构解析失败，改用 Markdown 索引: %s",
                        exc,
                    )
                    return str(client.index(str(md_path)))
                finally:
                    try:
                        md_path.unlink(missing_ok=True)
                    except OSError:
                        pass
        raise


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


def is_pageindex_supported_file(file_name: str, mime_type: str = "") -> bool:
    suffix = Path(file_name or "").suffix.lower()
    if suffix in PAGEINDEX_SUPPORTED_SUFFIXES:
        return True
    mime = (mime_type or "").split(";")[0].strip().lower()
    if not mime:
        return False
    if mime == "application/pdf":
        return True
    if mime in ("text/markdown", "text/x-markdown") or "markdown" in mime:
        return True
    if mime in (
        "text/plain",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/rtf",
        "text/rtf",
    ):
        return True
    if "wordprocessingml" in mime or mime.endswith(".word"):
        return True
    return False


def _office_bytes_to_markdown_temp(
    content: bytes,
    *,
    file_name: str,
    mime_type: str = "",
    title: str = "",
) -> Path | None:
    """Word / RTF / 纯文本提取为 Markdown 临时文件，供 PageIndex md 索引兜底。"""
    import uuid as _uuid

    from app.integrations.text_extract import extract_text_from_bytes

    name = (file_name or "").strip() or "document"
    lower = name.lower()
    try:
        parsed = extract_text_from_bytes(
            content,
            document_id=_uuid.UUID(int=0),
            file_name=name,
            mime_type=mime_type or "",
        )
    except Exception as exc:
        logger.debug("PageIndex Office 文本提取失败 file=%s: %s", name, exc)
        return None
    body = (parsed.full_text or "").strip()
    if not body:
        return None
    doc_title = (title or name.rsplit(".", 1)[0]).strip() or "文档"
    if not body.lstrip().startswith("#"):
        md = f"# {doc_title}\n\n{body}"
    else:
        md = body
    md_name = name
    if lower.endswith((".doc", ".docx", ".rtf", ".txt", ".text")):
        stem = name.rsplit(".", 1)[0] if "." in name else name
        md_name = f"{stem}.md"
    elif not lower.endswith((".md", ".markdown")):
        md_name = f"{doc_title}.md"
    path = write_temp_file(md.encode("utf-8"), md_name)
    return path


def prepare_pageindex_index_path(
    *,
    content: bytes,
    file_name: str,
    mime_type: str = "",
    title: str = "",
) -> tuple[Path, list[Path]]:
    """写入临时文件供 PageIndex index() 使用。

    PDF / Markdown 原样索引；Word / 纯文本优先转 Markdown（避免 PDF 目录 LLM 解析失败），
    失败时再尝试 PDF。
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
        md_path = _office_bytes_to_markdown_temp(
            content,
            file_name=name,
            mime_type=mime_type,
            title=title,
        )
        if md_path:
            cleanup.append(md_path)
            return md_path, cleanup

        from app.integrations.html_document_export import convert_file_bytes_to_pdf_for_citation

        converted = convert_file_bytes_to_pdf_for_citation(
            name,
            content,
            mime_type,
            title=title or name.rsplit(".", 1)[0],
        )
        if converted:
            pdf_name, pdf_bytes, _ = converted
            path = write_temp_file(pdf_bytes, pdf_name)
            cleanup.append(path)
            return path, cleanup

        raise ValueError(f"无法将「{name}」转为 PageIndex 可索引格式（Markdown / PDF）")

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


def flatten_pageindex_structure_text(structure: Any) -> str:
    """按树顺序拼接节点正文，供问答读取/本地检索（无需重新解析原文件）。"""
    parts: list[str] = []

    def walk(nodes: Any) -> None:
        if isinstance(nodes, dict):
            nodes = [nodes]
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = (node.get("title") or "").strip()
            text = (node.get("text") or node.get("summary") or "").strip()
            if title:
                parts.append(f"## {title}")
            if text:
                parts.append(text)
            walk(node.get("nodes"))

    walk(structure)
    return "\n\n".join(parts).strip()
