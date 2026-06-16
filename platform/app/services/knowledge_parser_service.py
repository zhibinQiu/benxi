"""KnowFlow / RAGFlow 文档切片、PageIndex 结构索引与 OCR 选项。

本模块是「解析器 ID / 索引栈就绪 / 后台任务 parser 解析」的**唯一规则入口**。
上传推断、重新索引、后台 Job、Celery 调度均应调用此处函数，避免在各 service 重复
硬编码 ``pageindex`` / ``naive`` 或各自判断 KnowFlow 是否可用。

调用约定见 docs/zh/implementation/knowledge-implementation.md §3。
"""

from __future__ import annotations

from copy import deepcopy

from app.config import get_settings

# 与后端解析器对齐；label/hint 面向终端用户，不含内部产品名
CHUNK_METHODS: list[dict[str, str]] = [
    {"id": "smart", "label": "智能分块", "hint": "适用于大多数 PDF 与 Word", "group": "modern"},
    {"id": "title", "label": "标题分块", "hint": "按章节标题切分", "group": "modern"},
    {"id": "regex", "label": "规则分块", "hint": "按自定义分隔规则切分", "group": "modern"},
    {"id": "parent_child", "label": "父子分块", "hint": "兼顾上下文与精确定位", "group": "modern"},
    {"id": "naive", "label": "通用分块", "hint": "适用于结构较简单的文档", "group": "classic"},
    {"id": "paper", "label": "论文", "hint": "学术论文结构", "group": "classic"},
    {"id": "book", "label": "书籍", "hint": "长文档按章节", "group": "classic"},
    {"id": "presentation", "label": "演示文稿", "hint": "幻灯片类文档", "group": "classic"},
    {"id": "laws", "label": "法规", "hint": "法律条文层级", "group": "classic"},
    {"id": "qa", "label": "问答", "hint": "问答对格式", "group": "classic"},
    {"id": "table", "label": "表格", "hint": "以表格为主", "group": "classic"},
    {"id": "picture", "label": "图片", "hint": "扫描件或图片 PDF", "group": "classic"},
    {"id": "one", "label": "整篇", "hint": "整篇作为一个片段", "group": "classic"},
    {"id": "email", "label": "邮件", "hint": "邮件正文结构", "group": "classic"},
    {
        "id": "pageindex",
        "label": "结构索引",
        "hint": "按章节结构建立索引；支持 PDF、Word、Markdown、TXT",
        "group": "experimental",
    },
]

LAYOUT_RECOGNIZERS: list[dict[str, str]] = [
    {"id": "PaddleOCR", "label": "标准识别（推荐）", "hint": "适用于扫描件与复杂版式"},
    {"id": "DeepDOC", "label": "内置识别", "hint": "适用于电子版 PDF"},
    {"id": "MinerU", "label": "高精度识别", "hint": "复杂版式，耗时较长"},
    {"id": "DOTS", "label": "增强识别", "hint": "图表较多的文档"},
    {"id": "Plain Text", "label": "纯文本", "hint": "跳过版式识别，适合已是文本的文件"},
]

_MODERN_LAYOUTS = frozenset({"MinerU", "DOTS", "PaddleOCR"})
_MODERN_PARSERS = frozenset({"smart", "title", "regex", "parent_child"})
_ALLOWED_PARSERS = frozenset(item["id"] for item in CHUNK_METHODS)
PARSER_PAGEINDEX = "pageindex"

_PARSER_DEFAULTS: dict[str, dict] = {
    "naive": {
        "chunk_token_num": 512,
        "delimiter": "\n",
        "html4excel": False,
        "raptor": {"use_raptor": False},
        "graphrag": {"use_graphrag": False},
    },
    "smart": {
        "chunk_token_num": 256,
        "min_chunk_tokens": 10,
        "raptor": {"use_raptor": False},
        "graphrag": {"use_graphrag": False},
    },
    "regex": {
        "chunk_token_num": 256,
        "min_chunk_tokens": 10,
        "regex_pattern": r"\n\n+",
        "raptor": {"use_raptor": False},
        "graphrag": {"use_graphrag": False},
    },
    "title": {
        "chunk_token_num": 256,
        "min_chunk_tokens": 10,
        "include_metadata": True,
        "split_level": 3,
        "raptor": {"use_raptor": False},
        "graphrag": {"use_graphrag": False},
    },
    "parent_child": {
        "chunk_token_num": 256,
        "min_chunk_tokens": 10,
        "parent_config": {
            "parent_chunk_size": 1024,
            "parent_chunk_overlap": 100,
            "retrieval_mode": "parent",
            "parent_split_level": 2,
        },
        "raptor": {"use_raptor": False},
        "graphrag": {"use_graphrag": False},
    },
}


def parser_id_raw(parser_id: str | None) -> str:
    """上传同步 / 自动推断场景的原始 parser_id（未归一化到白名单）。

    实现思路：显式传入优先；否则读 ``KNOWLEDGE_DEFAULT_PARSER_ID``（默认 naive）。
    不做 PageIndex 特殊分支——上传默认仍走 KnowFlow 向量分块。
    """
    settings = get_settings()
    return (parser_id or settings.knowledge_default_parser_id or "naive").strip().lower()


def reindex_parser_id_raw(parser_id: str | None) -> str:
    """重新索引场景的原始 parser_id（未归一化）。

    实现思路：与 ``parser_id_raw`` 分离，默认读 ``KNOWLEDGE_REINDEX_DEFAULT_PARSER_ID``
    （默认 pageindex），使「文档详情 → 重新索引」与上传默认解耦。
    """
    settings = get_settings()
    return (
        parser_id or settings.knowledge_reindex_default_parser_id or PARSER_PAGEINDEX
    ).strip().lower()


def is_pageindex_parser(parser_id: str | None) -> bool:
    return (parser_id or "").strip().lower() == PARSER_PAGEINDEX


def is_pageindex_reindex(*, mode: str, parser_id: str | None) -> bool:
    return mode == "reindex" and is_pageindex_parser(parser_id)


def resolve_job_parser_id(payload: dict) -> str:
    """后台索引任务 payload → 已解析的 parser_id（上传 index / 重新索引 reindex）。

    实现思路：``mode=reindex`` 走重索引默认；``mode=index``（上传后首次索引）走上传默认。
    避免对上传 Job 误用 ``reindex_parser_id_raw`` 导致默认变成 pageindex。
    """
    mode = str(payload.get("mode") or "index")
    raw = payload.get("parser_id")
    if mode == "reindex":
        return reindex_parser_id_raw(raw)
    return parser_id_raw(raw)


def job_payload_uses_pageindex(payload: dict) -> bool:
    return is_pageindex_parser(resolve_job_parser_id(payload))


def index_stack_block_reason(parser_id: str | None, *, reindex: bool = False) -> str | None:
    """索引栈不可用时返回用户可见原因；可用时返回 None。

    实现思路：先按场景解析 parser_id；PageIndex 只检查 ``PAGEINDEX_ENABLED``，
    其余解析器经 ``knowledge.enabled()`` + ``knowledge.stack_reachable()``。
    API 层 ``assert_index_stack_ready`` 与后台 Job 失败文案共用此函数，保证一致性。
    """
    pid = reindex_parser_id_raw(parser_id) if reindex else parser_id_raw(parser_id)
    if is_pageindex_parser(pid):
        if not get_settings().pageindex_enabled:
            return "文档索引功能未启用，请联系管理员"
        return None
    from app.domains.knowledge.gateway import knowledge

    if not knowledge.enabled():
        return "知识库同步未启用"
    if not knowledge.stack_reachable():
        return "知识服务不可用，请稍后重试"
    return None


def assert_index_stack_ready(parser_id: str | None) -> None:
    """索引任务启动前：PageIndex 走本地树索引，其余解析器需 KnowFlow 栈可用。"""
    from app.core.exceptions import bad_request

    reason = index_stack_block_reason(parser_id, reindex=True)
    if reason:
        raise bad_request(reason)


def normalize_parser_id(parser_id: str | None) -> str:
    raw = parser_id_raw(parser_id)
    if raw == PARSER_PAGEINDEX:
        return PARSER_PAGEINDEX
    return raw if raw in _ALLOWED_PARSERS else "naive"


def default_reindex_parser_id() -> str:
    return normalize_parser_id(get_settings().knowledge_reindex_default_parser_id)


def normalize_layout_recognize(layout: str | None) -> str:
    settings = get_settings()
    raw = (layout or settings.knowledge_default_layout_recognize or "DeepDOC").strip()
    allowed = {item["id"] for item in LAYOUT_RECOGNIZERS}
    return raw if raw in allowed else "DeepDOC"


def coerce_parser_layout(parser_id: str, layout_recognize: str) -> tuple[str, str]:
    """现代 OCR 需配合 smart 等分块；经典分块配合 DeepDOC/纯文本更稳。"""
    parser = normalize_parser_id(parser_id)
    layout = normalize_layout_recognize(layout_recognize)
    if layout in _MODERN_LAYOUTS and parser not in _MODERN_PARSERS:
        parser = "smart"
    return parser, layout


def infer_parser_for_upload_file(
    file_name: str,
    mime_type: str = "",
) -> tuple[str, str]:
    """按文件类型自动选择 KnowFlow 切片方法与版面识别（与 DocumentParserType 对齐）。

    实现思路：扩展名 + MIME 双判；表格/演示/图片走专用 parser；其余读配置默认。
    不在此自动选 PageIndex——结构索引由用户主动在「重新索引」中选择。
    """
    lower = (file_name or "").lower()
    mime = (mime_type or "").lower()
    settings = get_settings()
    default_layout = normalize_layout_recognize(
        settings.knowledge_default_layout_recognize
    )

    if lower.endswith(".md") or "markdown" in mime:
        return (
            normalize_parser_id(settings.knowledge_default_parser_id),
            default_layout,
        )
    if lower.endswith((".txt", ".csv", ".log", ".json", ".xml", ".yaml", ".yml")):
        return (
            normalize_parser_id(settings.knowledge_default_parser_id),
            default_layout,
        )
    if mime.startswith("text/") or mime in ("application/json", "application/xml"):
        return (
            normalize_parser_id(settings.knowledge_default_parser_id),
            default_layout,
        )
    if lower.endswith((".doc", ".docx", ".rtf")) or "word" in mime:
        return (
            normalize_parser_id(settings.knowledge_default_parser_id),
            default_layout,
        )
    if lower.endswith((".xlsx", ".xls")) or "spreadsheet" in mime or "excel" in mime:
        return "table", default_layout
    if (
        lower.endswith((".ppt", ".pptx"))
        or "presentation" in mime
        or "powerpoint" in mime
    ):
        return "presentation", default_layout
    if lower.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff")
    ) or mime.startswith("image/"):
        return "picture", default_layout
    if lower.endswith(".pdf") or mime == "application/pdf":
        return (
            normalize_parser_id(settings.knowledge_default_parser_id),
            default_layout,
        )

    return (
        normalize_parser_id(settings.knowledge_default_parser_id),
        default_layout,
    )


def build_parser_config(
    parser_id: str | None = None,
    layout_recognize: str | None = None,
    *,
    chunk_token_num: int | None = None,
) -> tuple[str, dict]:
    """生成 KnowFlow ``change_document_parser`` 所需的 (parser, parser_config)。

    实现思路：PageIndex 返回 ``{index_engine: pageindex}`` 占位，不走向量分块；
    其它 parser 合并 ``_PARSER_DEFAULTS``、``coerce_parser_layout`` 与 chunk_token 配置。
    """
    if is_pageindex_parser(parser_id):
        return PARSER_PAGEINDEX, {"index_engine": PARSER_PAGEINDEX}
    parser = normalize_parser_id(parser_id)
    settings = get_settings()
    parser, layout = coerce_parser_layout(
        normalize_parser_id(parser_id),
        normalize_layout_recognize(layout_recognize),
    )
    base = deepcopy(_PARSER_DEFAULTS.get(parser, _PARSER_DEFAULTS["smart"]))
    token = chunk_token_num or settings.knowledge_default_chunk_token_num
    base["chunk_token_num"] = token
    base["layout_recognize"] = layout
    if parser == "naive" and layout in _MODERN_LAYOUTS:
        base["layout_recognize"] = layout
    return parser, base


def list_parser_options() -> dict:
    """供 ``GET /knowledge/parsers`` 与前端重新索引弹窗使用的选项与默认值。

    实现思路：``defaults.parser_id`` 来自重索引默认（非上传默认），
    前端 ``useDocumentReindex`` 拉取后覆盖本地 ref，避免硬编码 pageindex。
    """
    settings = get_settings()
    defaults = {
        "parser_id": normalize_parser_id(settings.knowledge_reindex_default_parser_id),
        "layout_recognize": normalize_layout_recognize(
            settings.knowledge_default_layout_recognize
        ),
        "chunk_token_num": settings.knowledge_default_chunk_token_num,
    }
    return {
        "chunk_methods": CHUNK_METHODS,
        "layout_recognizers": LAYOUT_RECOGNIZERS,
        "defaults": defaults,
        "items": [m for m in CHUNK_METHODS if m["group"] == "classic"]
        + [m for m in CHUNK_METHODS if m["group"] == "modern"]
        + [m for m in CHUNK_METHODS if m["group"] == "experimental"],
        "config_hints": [
            "解析失败时请确认文档可正常打开，或更换索引方式后重试",
            "仍失败请联系管理员",
        ],
    }
