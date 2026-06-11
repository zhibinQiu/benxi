"""平台资源配置：环境变量默认值 + 数据库覆盖，保存后同步到 RAGFlow / KnowFlow 与各内置服务。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import Settings, get_settings
from app.integrations.ragflow_model_apply import (
    apply_embedding_to_template_tenant,
    apply_llm_to_template_tenant,
    fetch_template_embedding_defaults,
    patch_knowflow_paddleocr_url,
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
    "保存后立即生效：平台 API 根地址供浏览器请求后端；"
    "嵌入/语言模型写入 KnowFlow 模板租户并同步已开户用户；"
    "PaddleOCR 地址写入 deploy/knowflow/settings.yaml 并尝试重启 knowflow-backend；"
    "语音识别与 PDF 翻译地址供平台 API/Worker 调用；"
    "知识库 API / KnowFlow 后台与 Web UI / RAGFlow MySQL 供文档同步、iframe 嵌入与模型复制"
    "（默认来自 .env 中 PLATFORM_API_BASE_URL、RAGFLOW_*、KNOWFLOW_*）。"
)


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


def _env_defaults(settings: Settings) -> dict[str, str]:
    llm_url = (settings.platform_llm_base_url or "").strip() or settings.deepseek_base_url
    llm_key = (settings.platform_llm_api_key or "").strip() or settings.deepseek_api_key
    llm_model = (settings.platform_llm_model or "").strip() or settings.deepseek_model
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
        "paddleocr_url": (settings.platform_paddleocr_url or "").strip(),
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
    }


def _load_db_payload(db: Session | None) -> dict[str, str]:
    if db is None:
        return {}
    row = db.get(PlatformModelSettings, SINGLETON_ID)
    if not row or not isinstance(row.payload, dict):
        return {}
    return {str(k): str(v) if v is not None else "" for k, v in row.payload.items()}


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


def get_paddleocr_url(db: Session | None = None) -> str:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return merged.get("paddleocr_url") or ""


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
    return (get_settings().app_name or "").strip() or "AI原型演示系统"


def get_frontend_default_theme(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    return _normalize_frontend_theme(merged.get("frontend_default_theme"))


def get_model_settings(db: Session | None = None) -> ModelSettingsOut:
    effective = _merge_effective(get_settings(), db)
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
        rerank=_endpoint(
            base_url=effective["rerank_base_url"],
            api_key=effective["rerank_api_key"],
            model_name=effective["rerank_model"] or None,
        ),
        paddleocr_url=effective.get("paddleocr_url") or "",
        speech_service_url=effective.get("speech_service_url") or "",
        pdf2zh_api_url=effective.get("pdf2zh_api_url") or "",
        embedding_factory=effective.get("embedding_factory") or None,
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
    if payload.get("paddleocr_url"):
        if patch_knowflow_paddleocr_url(payload["paddleocr_url"]):
            try_restart_knowflow_services()
