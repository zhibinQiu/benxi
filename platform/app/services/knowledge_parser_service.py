"""KnowFlow / RAGFlow 文档切片与 PDF 版面识别（OCR）选项。"""

from __future__ import annotations

from copy import deepcopy

from app.config import get_settings

# 与 KnowFlow DocumentParserType / ChunkMethod 对齐
CHUNK_METHODS: list[dict[str, str]] = [
    {"id": "smart", "label": "智能分块", "hint": "推荐；配合 PaddleOCR/MinerU 等现代 OCR", "group": "modern"},
    {"id": "title", "label": "标题分块", "hint": "按标题层级切分", "group": "modern"},
    {"id": "regex", "label": "正则分块", "hint": "按自定义分隔符切分", "group": "modern"},
    {"id": "parent_child", "label": "父子分块", "hint": "父块检索、子块精确定位", "group": "modern"},
    {"id": "naive", "label": "Naive（通用）", "hint": "原 KnowFlow Naive；配 DeepDOC/纯文本", "group": "classic"},
    {"id": "paper", "label": "论文", "hint": "学术论文结构", "group": "classic"},
    {"id": "book", "label": "书籍", "hint": "长文档按章节", "group": "classic"},
    {"id": "presentation", "label": "演示文稿", "hint": "PPT/PPTX", "group": "classic"},
    {"id": "laws", "label": "法规", "hint": "法律条文层级", "group": "classic"},
    {"id": "qa", "label": "问答", "hint": "问答对格式", "group": "classic"},
    {"id": "table", "label": "表格", "hint": "以表格为主", "group": "classic"},
    {"id": "picture", "label": "图片", "hint": "扫描件/图片 PDF", "group": "classic"},
    {"id": "one", "label": "单页", "hint": "整篇一个切片", "group": "classic"},
    {"id": "email", "label": "邮件", "hint": "邮件正文结构", "group": "classic"},
]

LAYOUT_RECOGNIZERS: list[dict[str, str]] = [
    {"id": "PaddleOCR", "label": "PaddleOCR", "hint": "版面 OCR（默认；使用资源管理中的 PaddleOCR-VL 服务）"},
    {"id": "DeepDOC", "label": "DeepDOC", "hint": "RAGFlow 内置版面分析"},
    {"id": "MinerU", "label": "MinerU", "hint": "高精度 PDF 解析（需部署 MinerU 服务）"},
    {"id": "DOTS", "label": "DOTS", "hint": "视觉理解 OCR（需部署 DOTS 服务）"},
    {"id": "Plain Text", "label": "纯文本", "hint": "跳过复杂版面分析，适合已提取文本"},
]

_MODERN_LAYOUTS = frozenset({"MinerU", "DOTS", "PaddleOCR"})
_MODERN_PARSERS = frozenset({"smart", "title", "regex", "parent_child"})
_ALLOWED_PARSERS = frozenset(item["id"] for item in CHUNK_METHODS)

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


def normalize_parser_id(parser_id: str | None) -> str:
    settings = get_settings()
    raw = (parser_id or settings.knowledge_default_parser_id or "naive").strip().lower()
    return raw if raw in _ALLOWED_PARSERS else "naive"


def normalize_layout_recognize(layout: str | None) -> str:
    settings = get_settings()
    raw = (layout or settings.knowledge_default_layout_recognize or "PaddleOCR").strip()
    allowed = {item["id"] for item in LAYOUT_RECOGNIZERS}
    return raw if raw in allowed else "PaddleOCR"


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
    """按文件类型自动选择 KnowFlow 切片方法与版面识别（与 DocumentParserType 对齐）。"""
    lower = (file_name or "").lower()
    mime = (mime_type or "").lower()
    settings = get_settings()
    default_layout = normalize_layout_recognize(
        settings.knowledge_default_layout_recognize
    )

    if lower.endswith(".md") or "markdown" in mime:
        return "naive", "Plain Text"
    if lower.endswith((".txt", ".csv", ".log", ".json", ".xml", ".yaml", ".yml")):
        return "naive", "Plain Text"
    if mime.startswith("text/") or mime in ("application/json", "application/xml"):
        return "naive", "Plain Text"
    if lower.endswith((".doc", ".docx", ".rtf")) or "word" in mime:
        return "naive", "Plain Text"
    if lower.endswith((".xlsx", ".xls")) or "spreadsheet" in mime or "excel" in mime:
        return "table", "Plain Text"
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
    settings = get_settings()
    defaults = {
        "parser_id": normalize_parser_id(settings.knowledge_default_parser_id),
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
        + [m for m in CHUNK_METHODS if m["group"] == "modern"],
        "config_hints": [
            "PDF 版面 OCR 地址在资源管理 PaddleOCR-VL 或 deploy/knowflow/settings.yaml 配置",
            "嵌入向量模型在「系统设置 → 模型配置」或 KnowFlow 管理后台配置",
            "解析失败常见原因：OCR 服务未启动、嵌入模型未启用、Infinity 向量库异常",
            "图表增强失败（403 Model disabled）：在资源管理配置视觉模型（IMAGE2TEXT）并保存同步",
        ],
    }
