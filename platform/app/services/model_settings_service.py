"""平台资源配置：环境变量默认值 + 数据库覆盖，保存后同步到 RAGFlow / KnowFlow 与各内置服务。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import Settings, get_settings
from app.integrations.ragflow_model_apply import (
    apply_embedding_to_template_tenant,
    apply_image2text_to_template_tenant,
    apply_llm_to_template_tenant,
    fetch_template_embedding_defaults,
    infer_llm_factory,
    patch_knowflow_paddleocr_config,
    try_restart_knowflow_services,
)
from app.models.platform_model_settings import SINGLETON_ID, PlatformModelSettings
from app.schemas.model_settings import (
    KnowledgeInfraOut,
    ModelEndpointOut,
    ModelSettingsOut,
    ModelSettingsUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

NOTICE_EFFECTIVE = (
    "所有模型（语言 / 嵌入 / VL / Rerank / OCR-VL）均在资源管理配置「API URL + 模型名 + Key」，"
    "保存后立即生效，无需改代码或重启；上线后仅改 URL 与模型名即可切换本地 vLLM/Ollama 等。"
    "嵌入与 VL 保存后写入 RAGFlow 模板租户并同步用户；OCR-VL 写入 KnowFlow settings.yaml。"
    ".env 中 PLATFORM_* 仅作首次部署引导，运行中以本页保存为准。"
)

_DEFAULT_PADDLEOCR_MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"

def _endpoint_fields(merged: dict[str, str], prefix: str) -> tuple[str, str, str]:
    return (
        (merged.get(f"{prefix}_base_url") or "").strip(),
        (merged.get(f"{prefix}_api_key") or "").strip(),
        (merged.get(f"{prefix}_model") or "").strip(),
    )


def _migrate_legacy_model_keys(payload: dict[str, str]) -> dict[str, str]:
    """资源管理曾用 vision_* 字段，统一为 vl_*。"""
    out = dict(payload)
    for old, new in (
        ("vision_base_url", "vl_base_url"),
        ("vision_api_key", "vl_api_key"),
        ("vision_model", "vl_model"),
    ):
        if (out.get(old) or "").strip() and not (out.get(new) or "").strip():
            out[new] = out[old]
    return out


def _vl_fields_from_update(body: ModelSettingsUpdate) -> tuple[str | None, str | None, str | None]:
    """合并 vl_* 与旧 vision_* 更新字段。"""
    base = body.vl_base_url if body.vl_base_url is not None else body.vision_base_url
    key = body.vl_api_key if body.vl_api_key is not None else body.vision_api_key
    model = body.vl_model if body.vl_model is not None else body.vision_model
    return base, key, model


def _legacy_paddleocr_base_url(merged: dict[str, str]) -> str:
    explicit = (merged.get("paddleocr_base_url") or "").strip()
    if explicit:
        return explicit
    return (merged.get("paddleocr_url") or "").strip()


def mask_secret(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "••••••••"
    return f"{v[:4]}••••{v[-4:]}"


def _endpoint(
    *,
    base_url: str,
    api_key: str,
    model_name: str | None = None,
) -> ModelEndpointOut:
    key = (api_key or "").strip()
    return ModelEndpointOut(
        base_url=(base_url or "").strip(),
        api_key_configured=bool(key),
        api_key_masked=mask_secret(key),
        model_name=(model_name or "").strip() or None,
    )


def _normalize_frontend_theme(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in ("light", "dark", "system"):
        return v
    return "system"


def _paddleocr_env_defaults(settings: Settings) -> tuple[str, str, str, str]:
    """PaddleOCR-VL：显式 PLATFORM_PADDLEOCR_* 优先，否则回退 VL / 嵌入（硅基流动等在线 API）。"""
    base = (settings.platform_paddleocr_base_url or "").strip()
    legacy_url = (settings.platform_paddleocr_url or "").strip()
    if not base:
        base = legacy_url
    key = (settings.platform_paddleocr_api_key or "").strip()
    model = (settings.platform_paddleocr_model or "").strip()

    vl_base = (settings.platform_vl_base_url or "").strip()
    vl_key = (settings.platform_vl_api_key or "").strip()
    emb_base = (settings.platform_embedding_base_url or "").strip()
    emb_key = (settings.platform_embedding_api_key or "").strip()

    if not base:
        base = vl_base or emb_base
    if not key:
        key = vl_key or emb_key
    if not model and base:
        model = _DEFAULT_PADDLEOCR_MODEL

    return base, key, model, legacy_url


def _env_defaults(settings: Settings) -> dict[str, str]:
    llm_url = (settings.platform_llm_base_url or "").strip() or settings.deepseek_base_url
    llm_key = (settings.platform_llm_api_key or "").strip() or settings.deepseek_api_key
    llm_model = (settings.platform_llm_model or "").strip() or settings.deepseek_model
    paddle_base, paddle_key, paddle_model, paddle_legacy_url = _paddleocr_env_defaults(settings)
    return {
        "llm_base_url": llm_url or "",
        "llm_api_key": llm_key or "",
        "llm_model": llm_model or "",
        "embedding_base_url": (settings.platform_embedding_base_url or "").strip(),
        "embedding_api_key": (settings.platform_embedding_api_key or "").strip(),
        "embedding_model": (settings.platform_embedding_model or "").strip(),
        "embedding_factory": (settings.platform_embedding_factory or "").strip(),
        "rerank_base_url": (settings.platform_rerank_base_url or "").strip(),
        "rerank_api_key": (settings.platform_rerank_api_key or "").strip(),
        "rerank_model": (settings.platform_rerank_model or "").strip(),
        "vl_base_url": (settings.platform_vl_base_url or "").strip(),
        "vl_api_key": (settings.platform_vl_api_key or "").strip(),
        "vl_model": (settings.platform_vl_model or "").strip(),
        "paddleocr_base_url": paddle_base,
        "paddleocr_api_key": paddle_key,
        "paddleocr_model": paddle_model,
        "paddleocr_url": paddle_legacy_url,
        "speech_service_url": (settings.speech_service_url or "").strip(),
        "pdf2zh_api_url": (settings.pdf2zh_api_url or "").strip(),
        "platform_api_base_url": (settings.platform_api_base_url or "").strip().rstrip("/"),
        "frontend_app_title": (settings.frontend_app_title or "").strip(),
        "frontend_default_theme": _normalize_frontend_theme(settings.frontend_default_theme),
        "ragflow_api_url": (settings.ragflow_api_url or "").strip(),
        "ragflow_api_key": (settings.ragflow_api_key or "").strip(),
        "knowflow_backend_url": (settings.knowflow_backend_url or "").strip(),
        "knowflow_ui_url": (settings.knowflow_ui_url or "").strip(),
        "knowflow_ui_public_url": (settings.knowflow_ui_public_url or "").strip(),
        "knowflow_ui_proxy_prefix": (settings.knowflow_ui_proxy_prefix or "").strip(),
        "ragflow_mysql_host": (settings.ragflow_mysql_host or "").strip(),
        "ragflow_mysql_port": str(int(settings.ragflow_mysql_port or 3306)),
        "ragflow_mysql_db": (settings.ragflow_mysql_db or "rag_flow").strip(),
        "ragflow_mysql_password": (settings.ragflow_mysql_password or "").strip(),
        "ragflow_mysql_container": (settings.ragflow_mysql_container or "ragflow-mysql").strip(),
        "searxng_url": (settings.searxng_url or "").strip(),
        "searxng_timeout_seconds": str(float(settings.searxng_timeout_seconds or 15.0)),
    }


def _load_db_payload(db: Session | None) -> dict[str, str]:
    if db is None:
        return {}
    row = db.get(PlatformModelSettings, SINGLETON_ID)
    if not row or not isinstance(row.payload, dict):
        return {}
    raw = {str(k): str(v) if v is not None else "" for k, v in row.payload.items()}
    return _migrate_legacy_model_keys(raw)


def _merge_effective(
    settings: Settings, db: Session | None, *, fill_embedding_from_ragflow: bool = True
) -> dict[str, str]:
    merged = _env_defaults(settings)
    if fill_embedding_from_ragflow and not merged.get("embedding_model"):
        rag_defaults = fetch_template_embedding_defaults(db)
        for key, val in rag_defaults.items():
            if val and not merged.get(key):
                merged[key] = val
    db_payload = _load_db_payload(db)
    for key, val in db_payload.items():
        if val != "":
            merged[key] = val
    return merged


def get_effective_model_config(db: Session | None = None) -> dict[str, str]:
    return _merge_effective(get_settings(), db)


def get_llm_credentials(db: Session | None = None) -> tuple[str, str, str]:
    """语言模型凭证（资源管理 / .env 合并，每次调用读库）。"""
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return _endpoint_fields(merged, "llm")


def get_embedding_credentials(db: Session | None = None) -> tuple[str, str, str]:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return _endpoint_fields(merged, "embedding")


def get_vl_credentials(db: Session | None = None) -> tuple[str, str, str]:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return _endpoint_fields(merged, "vl")


def get_rerank_credentials(db: Session | None = None) -> tuple[str, str, str]:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return _endpoint_fields(merged, "rerank")


def get_paddleocr_url(db: Session | None = None) -> str:
    base, _, _ = get_paddleocr_credentials(db)
    return base


def get_paddleocr_credentials(db: Session | None = None) -> tuple[str, str, str]:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    base, key, model = _endpoint_fields(merged, "paddleocr")
    if not base:
        base = _legacy_paddleocr_base_url(merged)
    return base, key, model


def sync_paddleocr_to_knowflow(db: Session | None = None) -> bool:
    """将平台 PaddleOCR 配置写入 KnowFlow settings.yaml（PDF layout=PaddleOCR 时由 KnowFlow 读取）。"""
    base, key, model = get_paddleocr_credentials(db)
    if not base:
        logger.info("未配置 PaddleOCR，跳过 KnowFlow settings 同步")
        return False
    ok = patch_knowflow_paddleocr_config(
        base_url=base,
        api_key=key,
        model_name=model,
    )
    if ok:
        logger.info("已同步 PaddleOCR 配置到 KnowFlow settings.yaml")
    return ok


def get_speech_service_url(db: Session | None = None) -> str:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return merged.get("speech_service_url") or ""


def resolve_ragflow_api_base(api_url: str, *, knowflow_enabled: bool | None = None) -> str:
    """RAGFlow HTTP API 基址（与 Settings.ragflow_api_base 一致）。"""
    from urllib.parse import urlparse

    settings = get_settings()
    enabled = settings.knowflow_enabled if knowflow_enabled is None else knowflow_enabled
    raw = (api_url or settings.ragflow_api_url or "").strip().rstrip("/")
    if not raw:
        return "http://127.0.0.1:9380"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if enabled and host in ("ragflow", "ragflow-server") and port in (9380, None):
        scheme = parsed.scheme or "http"
        return f"{scheme}://{parsed.hostname}:80"
    return raw


def _effective_config(db: Session | None, *, fill_embedding_from_ragflow: bool = False) -> dict[str, str]:
    """合并环境变量与库内覆盖；无 db 时尝试只读加载单例配置。"""
    settings = get_settings()
    if db is not None:
        return _merge_effective(settings, db, fill_embedding_from_ragflow=fill_embedding_from_ragflow)
    try:
        from app.database import SessionLocal

        with SessionLocal() as session:
            return _merge_effective(
                settings, session, fill_embedding_from_ragflow=fill_embedding_from_ragflow
            )
    except Exception:
        logger.debug("读取 platform_model_settings 失败，回退环境变量", exc_info=True)
        return _merge_effective(settings, None, fill_embedding_from_ragflow=fill_embedding_from_ragflow)


def get_ragflow_api_url(db: Session | None = None) -> str:
    merged = _effective_config(db)
    return merged.get("ragflow_api_url") or get_settings().ragflow_api_url or ""


def get_ragflow_api_key(db: Session | None = None) -> str:
    merged = _effective_config(db)
    return merged.get("ragflow_api_key") or get_settings().ragflow_api_key or ""


def get_ragflow_api_base(db: Session | None = None) -> str:
    return resolve_ragflow_api_base(get_ragflow_api_url(db))


def get_knowflow_backend_url(db: Session | None = None) -> str:
    merged = _effective_config(db)
    return (
        merged.get("knowflow_backend_url")
        or get_settings().knowflow_backend_url
        or "http://127.0.0.1:5001"
    )


def get_knowflow_ui_url(db: Session | None = None) -> str:
    merged = _effective_config(db)
    return (merged.get("knowflow_ui_url") or get_settings().knowflow_ui_url or "").strip()


def get_knowflow_ui_public_url(db: Session | None = None) -> str:
    merged = _effective_config(db)
    return (
        merged.get("knowflow_ui_public_url") or get_settings().knowflow_ui_public_url or ""
    ).strip()


def get_knowflow_ui_proxy_prefix(db: Session | None = None) -> str:
    merged = _effective_config(db)
    return (
        merged.get("knowflow_ui_proxy_prefix") or get_settings().knowflow_ui_proxy_prefix or ""
    ).strip()


def get_knowflow_ui_browser_base(db: Session | None = None) -> str:
    """浏览器 iframe / 跳转使用的基址。"""
    public = get_knowflow_ui_public_url(db).rstrip("/")
    if public:
        return public
    proxy = get_knowflow_ui_proxy_prefix(db).rstrip("/")
    if proxy:
        return proxy
    ui = get_knowflow_ui_url(db).rstrip("/")
    if ui:
        return ui
    return get_settings().knowflow_ui_browser_base


def resolve_ui_embed_base(db: Session | None = None) -> str:
    """前端 iframe 基址：优先同源代理前缀。"""
    proxy = get_knowflow_ui_proxy_prefix(db).strip()
    if proxy:
        return proxy.rstrip("/")
    ui = get_knowflow_ui_url(db).strip()
    if ui:
        return ui.rstrip("/")
    return get_settings().knowflow_ui_url.rstrip("/")


def get_ragflow_mysql_settings(db: Session | None = None) -> tuple[str, str, str, str, int]:
    """返回 (container, password, db, host, port)。"""
    settings = get_settings()
    merged = _effective_config(db)
    container = (merged.get("ragflow_mysql_container") or "ragflow-mysql").strip()
    password = (merged.get("ragflow_mysql_password") or "infini_rag_flow").strip()
    db_name = (merged.get("ragflow_mysql_db") or "rag_flow").strip()
    host = (merged.get("ragflow_mysql_host") or "").strip()
    if not host and settings.knowflow_enabled:
        host = "knowflow-mysql"
    try:
        port = int(merged.get("ragflow_mysql_port") or 3306)
    except (TypeError, ValueError):
        port = 3306
    return container, password, db_name, host, port


def _knowledge_infra_out(effective: dict[str, str]) -> KnowledgeInfraOut:
    settings = get_settings()
    mysql_pwd = effective.get("ragflow_mysql_password") or ""
    rag_key = effective.get("ragflow_api_key") or ""
    try:
        mysql_port = int(effective.get("ragflow_mysql_port") or 3306)
    except (TypeError, ValueError):
        mysql_port = 3306
    return KnowledgeInfraOut(
        knowflow_enabled=bool(settings.knowflow_enabled),
        ragflow_api_url=effective.get("ragflow_api_url") or "",
        ragflow_api_key_configured=bool(rag_key.strip()),
        ragflow_api_key_masked=mask_secret(rag_key),
        knowflow_backend_url=effective.get("knowflow_backend_url") or "",
        knowflow_ui_url=effective.get("knowflow_ui_url") or "",
        knowflow_ui_public_url=effective.get("knowflow_ui_public_url") or "",
        knowflow_ui_proxy_prefix=effective.get("knowflow_ui_proxy_prefix") or "",
        ragflow_mysql_host=effective.get("ragflow_mysql_host") or "",
        ragflow_mysql_port=mysql_port,
        ragflow_mysql_db=effective.get("ragflow_mysql_db") or "",
        ragflow_mysql_password_configured=bool(mysql_pwd.strip()),
        ragflow_mysql_password_masked=mask_secret(mysql_pwd),
        ragflow_mysql_container=effective.get("ragflow_mysql_container") or "",
    )


def get_pdf2zh_api_url(db: Session | None = None) -> str:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return merged.get("pdf2zh_api_url") or ""


def get_searxng_url(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    return (merged.get("searxng_url") or get_settings().searxng_url or "").strip()


def get_searxng_timeout_seconds(db: Session | None = None) -> float:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    raw = merged.get("searxng_timeout_seconds")
    if raw is None or raw == "":
        return max(3.0, float(get_settings().searxng_timeout_seconds or 15.0))
    try:
        return max(3.0, float(raw))
    except (TypeError, ValueError):
        return 15.0


def get_platform_api_base_url(db: Session | None = None) -> str:
    """浏览器请求平台后端的根地址（相对 /ai 或完整 URL）。"""
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    raw = (merged.get("platform_api_base_url") or "").strip().rstrip("/")
    if raw:
        return raw
    settings = get_settings()
    fallback = (settings.api_public_path_prefix or "/ai").strip().rstrip("/")
    return fallback or "/ai"


def get_frontend_app_title(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    title = (merged.get("frontend_app_title") or "").strip()
    if title:
        return title
    return (get_settings().app_name or "").strip() or "企业 AI 知识库平台"


def get_frontend_default_theme(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    return _normalize_frontend_theme(merged.get("frontend_default_theme"))


def get_model_settings(db: Session | None = None) -> ModelSettingsOut:
    effective = _merge_effective(get_settings(), db)
    vl_base, vl_key, vl_model = _endpoint_fields(effective, "vl")
    paddle_base, paddle_key, paddle_model = _endpoint_fields(effective, "paddleocr")
    if not paddle_base:
        paddle_base = _legacy_paddleocr_base_url(effective)
    return ModelSettingsOut(
        effective_source="platform_model_settings",
        editable=True,
        notice=NOTICE_EFFECTIVE,
        platform_api_base_url=get_platform_api_base_url(db),
        frontend_app_title=(effective.get("frontend_app_title") or "").strip(),
        frontend_default_theme=_normalize_frontend_theme(effective.get("frontend_default_theme")),
        llm=_endpoint(
            base_url=effective["llm_base_url"],
            api_key=effective["llm_api_key"],
            model_name=effective["llm_model"],
        ),
        embedding=_endpoint(
            base_url=effective["embedding_base_url"],
            api_key=effective["embedding_api_key"],
            model_name=effective["embedding_model"] or None,
        ),
        vl=_endpoint(
            base_url=vl_base,
            api_key=vl_key,
            model_name=vl_model or None,
        ),
        rerank=_endpoint(
            base_url=effective["rerank_base_url"],
            api_key=effective["rerank_api_key"],
            model_name=effective["rerank_model"] or None,
        ),
        paddleocr=_endpoint(
            base_url=paddle_base,
            api_key=paddle_key,
            model_name=paddle_model or None,
        ),
        paddleocr_url=paddle_base or effective.get("paddleocr_url") or "",
        speech_service_url=effective.get("speech_service_url") or "",
        pdf2zh_api_url=effective.get("pdf2zh_api_url") or "",
        embedding_factory=effective.get("embedding_factory") or None,
        searxng_url=effective.get("searxng_url") or "",
        searxng_timeout_seconds=float(effective.get("searxng_timeout_seconds") or 15.0),
        knowledge=_knowledge_infra_out(effective),
    )


def _keep_secret(incoming: str | None, previous: str) -> str:
    if incoming is None:
        return previous
    val = (incoming or "").strip()
    if not val or val == mask_secret(previous):
        return previous
    return val


def save_model_settings(
    db: Session,
    body: ModelSettingsUpdate,
) -> ModelSettingsOut:
    current = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    vl_base_in, vl_key_in, vl_model_in = _vl_fields_from_update(body)

    payload = {
        "llm_base_url": (body.llm_base_url if body.llm_base_url is not None else current["llm_base_url"]),
        "llm_model": (body.llm_model if body.llm_model is not None else current["llm_model"]),
        "llm_api_key": _keep_secret(body.llm_api_key, current["llm_api_key"]),
        "embedding_base_url": (
            body.embedding_base_url
            if body.embedding_base_url is not None
            else current["embedding_base_url"]
        ),
        "embedding_model": (
            body.embedding_model
            if body.embedding_model is not None
            else current["embedding_model"]
        ),
        "embedding_factory": (
            body.embedding_factory
            if body.embedding_factory is not None
            else current["embedding_factory"]
        ),
        "embedding_api_key": _keep_secret(
            body.embedding_api_key, current["embedding_api_key"]
        ),
        "rerank_base_url": (
            body.rerank_base_url if body.rerank_base_url is not None else current["rerank_base_url"]
        ),
        "rerank_model": (
            body.rerank_model if body.rerank_model is not None else current["rerank_model"]
        ),
        "rerank_api_key": _keep_secret(body.rerank_api_key, current["rerank_api_key"]),
        "vl_base_url": (
            vl_base_in if vl_base_in is not None else current.get("vl_base_url", "")
        ),
        "vl_model": (
            vl_model_in if vl_model_in is not None else current.get("vl_model", "")
        ),
        "vl_api_key": _keep_secret(vl_key_in, current.get("vl_api_key", "")),
        "paddleocr_base_url": (
            body.paddleocr_base_url
            if body.paddleocr_base_url is not None
            else current.get("paddleocr_base_url", "")
        ),
        "paddleocr_model": (
            body.paddleocr_model
            if body.paddleocr_model is not None
            else current.get("paddleocr_model", "")
        ),
        "paddleocr_api_key": _keep_secret(
            body.paddleocr_api_key, current.get("paddleocr_api_key", "")
        ),
        "paddleocr_url": (
            body.paddleocr_url if body.paddleocr_url is not None else current["paddleocr_url"]
        ),
        "speech_service_url": (
            body.speech_service_url
            if body.speech_service_url is not None
            else current["speech_service_url"]
        ),
        "pdf2zh_api_url": (
            body.pdf2zh_api_url if body.pdf2zh_api_url is not None else current["pdf2zh_api_url"]
        ),
        "platform_api_base_url": (
            (body.platform_api_base_url or "").strip().rstrip("/")
            if body.platform_api_base_url is not None
            else current["platform_api_base_url"]
        ),
        "frontend_app_title": (
            (body.frontend_app_title or "").strip()
            if body.frontend_app_title is not None
            else current.get("frontend_app_title", "")
        ),
        "frontend_default_theme": (
            _normalize_frontend_theme(body.frontend_default_theme)
            if body.frontend_default_theme is not None
            else _normalize_frontend_theme(current.get("frontend_default_theme"))
        ),
        "ragflow_api_url": (
            body.ragflow_api_url
            if body.ragflow_api_url is not None
            else current["ragflow_api_url"]
        ),
        "ragflow_api_key": _keep_secret(body.ragflow_api_key, current["ragflow_api_key"]),
        "knowflow_backend_url": (
            body.knowflow_backend_url
            if body.knowflow_backend_url is not None
            else current["knowflow_backend_url"]
        ),
        "knowflow_ui_url": (
            body.knowflow_ui_url
            if body.knowflow_ui_url is not None
            else current["knowflow_ui_url"]
        ),
        "knowflow_ui_public_url": (
            body.knowflow_ui_public_url
            if body.knowflow_ui_public_url is not None
            else current["knowflow_ui_public_url"]
        ),
        "knowflow_ui_proxy_prefix": (
            body.knowflow_ui_proxy_prefix
            if body.knowflow_ui_proxy_prefix is not None
            else current["knowflow_ui_proxy_prefix"]
        ),
        "ragflow_mysql_host": (
            body.ragflow_mysql_host
            if body.ragflow_mysql_host is not None
            else current["ragflow_mysql_host"]
        ),
        "ragflow_mysql_port": (
            str(body.ragflow_mysql_port)
            if body.ragflow_mysql_port is not None
            else current["ragflow_mysql_port"]
        ),
        "ragflow_mysql_db": (
            body.ragflow_mysql_db
            if body.ragflow_mysql_db is not None
            else current["ragflow_mysql_db"]
        ),
        "ragflow_mysql_password": _keep_secret(
            body.ragflow_mysql_password, current["ragflow_mysql_password"]
        ),
        "ragflow_mysql_container": (
            body.ragflow_mysql_container
            if body.ragflow_mysql_container is not None
            else current["ragflow_mysql_container"]
        ),
        "searxng_url": (
            (body.searxng_url or "").strip()
            if body.searxng_url is not None
            else current.get("searxng_url", "")
        ),
        "searxng_timeout_seconds": (
            str(max(3.0, float(body.searxng_timeout_seconds)))
            if body.searxng_timeout_seconds is not None
            else current.get("searxng_timeout_seconds", "15.0")
        ),
    }

    row = db.get(PlatformModelSettings, SINGLETON_ID)
    if row is None:
        row = PlatformModelSettings(id=SINGLETON_ID, payload=payload)
        db.add(row)
    else:
        row.payload = payload
    db.flush()

    apply_saved_settings(db, payload)
    db.commit()
    return get_model_settings(db)


def apply_saved_settings(db: Session, payload: dict[str, str]) -> None:
    if payload.get("embedding_api_key") and payload.get("embedding_model"):
        apply_embedding_to_template_tenant(
            db,
            base_url=payload.get("embedding_base_url", ""),
            api_key=payload.get("embedding_api_key", ""),
            model_name=payload.get("embedding_model", ""),
            factory=payload.get("embedding_factory", ""),
        )
    if payload.get("llm_api_key") and payload.get("llm_model"):
        apply_llm_to_template_tenant(
            db,
            base_url=payload.get("llm_base_url", ""),
            api_key=payload.get("llm_api_key", ""),
            model_name=payload.get("llm_model", ""),
        )
    vl_base, vl_key, vl_model = _endpoint_fields(payload, "vl")
    if vl_key and vl_model:
        apply_image2text_to_template_tenant(
            db,
            base_url=vl_base,
            api_key=vl_key,
            model_name=vl_model,
            factory=infer_llm_factory(vl_base, payload.get("embedding_factory", "")),
        )
    paddle_base, paddle_key, paddle_model = _endpoint_fields(payload, "paddleocr")
    if not paddle_base:
        paddle_base = _legacy_paddleocr_base_url(payload)
    if paddle_base:
        if patch_knowflow_paddleocr_config(
            base_url=paddle_base,
            api_key=paddle_key,
            model_name=paddle_model,
        ):
            try_restart_knowflow_services()
