"""平台资源配置：环境变量默认值 + 数据库覆盖，保存后同步到 RAGFlow / KnowFlow 与各内置服务。"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from app.config import Settings, get_settings
from app.integrations.ragflow_model_apply import (
    apply_embedding_to_template_tenant,
    apply_image2text_to_template_tenant,
    apply_llm_to_template_tenant,
    apply_rerank_to_template_tenant,
    fetch_template_embedding_defaults,
    infer_llm_factory,
    patch_knowflow_paddleocr_config,
    try_restart_knowflow_services,
)
from app.models.platform_model_settings import SINGLETON_ID, PlatformModelSettings
from app.schemas.model_settings import (
    KnowledgeInfraOut,
    ModelEndpointOut,
    ProviderEndpointOut,
    ModelSettingsOut,
    ModelSettingsUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

NOTICE_EFFECTIVE = (
    "所有模型（语言 / 嵌入 / VL / Rerank / OCR-VL）均在资源管理配置「API URL + 模型名 + Key」，"
    "保存后立即生效，无需改代码或重启；上线后仅改 URL 与模型名即可切换本地 vLLM/Ollama 等。"
    "嵌入 / VL / Rerank 保存后写入知识库模板租户并同步用户；OCR-VL 写入知识库服务配置。"
    ".env 中 PLATFORM_* 仅作首次部署引导，运行中以本页保存为准。"
)

_DEFAULT_PADDLEOCR_MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"
_DEFAULT_TTS_MODEL = "FunAudioLLM/CosyVoice2-0.5B"

# 语音合成仅能从支持 /audio/speech 的 OpenAI 兼容端点回退（如硅基流动），不能回退 DeepSeek 等纯 LLM。
_TTS_INCOMPATIBLE_HOST_MARKERS = ("deepseek.com",)
_TTS_COMPATIBLE_HOST_MARKERS = (
    "siliconflow.cn",
    "siliconflow.com",
    "api.openai.com",
    "openai.azure.com",
)
_TTS_FALLBACK_PREFIXES = ("llm", "vl", "embedding", "paddleocr")


def _url_host_supports_tts_fallback(base_url: str) -> bool:
    u = (base_url or "").strip().lower()
    if not u:
        return False
    for marker in _TTS_INCOMPATIBLE_HOST_MARKERS:
        if marker in u:
            return False
    for marker in _TTS_COMPATIBLE_HOST_MARKERS:
        if marker in u:
            return True
    return False


def _pick_tts_fallback_base_key(merged: dict[str, str]) -> tuple[str, str]:
    """未单独配置 TTS 时，从其它已配置端点借用 URL/Key（跳过不支持 TTS 的 LLM）。"""
    for prefix in _TTS_FALLBACK_PREFIXES:
        base, key, _ = _endpoint_fields(merged, prefix)
        if base and key and _url_host_supports_tts_fallback(base):
            return base, key
    return "", ""

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
    providers: list[ProviderEndpointOut] | None = None,
    active_provider: str = "",
) -> ModelEndpointOut:
    key = (api_key or "").strip()
    return ModelEndpointOut(
        base_url=(base_url or "").strip(),
        api_key_configured=bool(key),
        api_key_masked=mask_secret(key),
        model_name=(model_name or "").strip() or None,
        providers=providers or [],
        active_provider=active_provider,
    )


def _endpoint_with_providers(
    effective: dict[str, str],
    prefix: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
) -> ModelEndpointOut:
    """从 effective 配置构造 ModelEndpointOut，含 providers 信息。"""
    b_url = base_url if base_url is not None else effective.get(f"{prefix}_base_url", "")
    a_key = api_key if api_key is not None else effective.get(f"{prefix}_api_key", "")
    m_name = model_name if model_name is not None else effective.get(f"{prefix}_model", "")
    prov_raw, active_id = _providers_from_payload(effective, prefix)
    if prov_raw:
        out_providers, eff_base, eff_key, eff_model = _providers_to_endpoint_out(prov_raw, active_id)
        b_url = b_url or eff_base
        a_key = a_key or eff_key
        m_name = m_name or eff_model
        return _endpoint(
            base_url=b_url,
            api_key=a_key,
            model_name=m_name,
            providers=out_providers,
            active_provider=active_id,
        )
    # 无 providers 时从 flat 字段构造默认 provider（兼容旧配置）
    if b_url or a_key or m_name:
        default_providers = _build_providers_from_flat(b_url, a_key, m_name)
        out_providers, _, _, _ = _providers_to_endpoint_out(default_providers, "default")
        return _endpoint(
            base_url=b_url,
            api_key=a_key,
            model_name=m_name,
            providers=out_providers,
            active_provider="default",
        )
    return _endpoint(
        base_url=b_url,
        api_key=a_key,
        model_name=m_name,
    )


def _providers_from_payload(
    payload: dict[str, str], prefix: str,
) -> tuple[list[dict], str]:
    """从 payload 中读取 providers 列表和 active_provider ID。"""
    providers_key = f"{prefix}_providers"
    active_key = f"{prefix}_active_provider"
    raw = payload.get(providers_key, "")
    active_id = payload.get(active_key, "")
    if raw:
        try:
            import json
            providers = json.loads(raw)
            if isinstance(providers, list) and len(providers) > 0:
                return providers, active_id or providers[0].get("id", "")
        except (json.JSONDecodeError, TypeError, IndexError):
            pass
    return [], ""


def _providers_to_endpoint_out(
    providers_raw: list[dict], active_id: str,
) -> tuple[list[ProviderEndpointOut], str, str, str]:
    """将 providers 原始列表转为 ProviderEndpointOut，计算有效 base_url/api_key/model。"""
    out_providers = []
    effective_base = ""
    effective_key = ""
    effective_model = ""
    for p in providers_raw:
        pid = p.get("id", "")
        pwd = p.get("api_key", p.get("password", p.get("api_key_masked", "")))
        model = p.get("model_name", p.get("model", "")) or ""
        out_providers.append(
            ProviderEndpointOut(
                id=pid,
                label=p.get("label", "") or "",
                base_url=p.get("base_url", "") or "",
                api_key_configured=bool(pwd.strip()),
                api_key_masked=mask_secret(pwd),
                model_name=model.strip() or None,
            )
        )
    for p in providers_raw:
        if p.get("id", "") == active_id:
            effective_base = p.get("base_url", "") or ""
            effective_key = p.get("api_key", p.get("password", p.get("api_key_masked", ""))) or ""
            effective_model = p.get("model_name", p.get("model", "")) or ""
            break
    if not effective_base and providers_raw:
        p0 = providers_raw[0]
        effective_base = p0.get("base_url", "") or ""
        effective_key = p0.get("api_key", p0.get("password", p0.get("api_key_masked", ""))) or ""
        effective_model = p0.get("model_name", p0.get("model", "")) or ""
    return out_providers, effective_base, effective_key, effective_model


def _build_providers_from_flat(
    base_url: str, api_key: str, model_name: str,
) -> list[dict]:
    """从平铺字段构造单个默认 provider。"""
    return [
        {
            "id": "default",
            "label": "",
            "base_url": base_url,
            "api_key": api_key,
            "model_name": model_name,
        }
    ]


def _provider_payload_from_update(
    providers_in: list, active_in: str | None,
    cur_base: str = "", cur_key: str = "", cur_model: str = "",
    current: dict[str, str] | None = None,
    prefix: str = "",
) -> tuple[str, str, str, str, str]:
    """处理 provider 更新：返回 (providers_json, active, flat_base, flat_key, flat_model)。

    当 incoming providers 只携带 api_key_masked 时（前端不含真实 key 的保存请求），
    从 current 中查找先前存储的真实 key 来保持原值。
    """
    import json

    if not providers_in:
        return "", "", cur_base, cur_key, cur_model

    # 从 current 中加载当前已存储的 providers 索引，用于 key 还原
    prev_providers: list[dict] = []
    if current and prefix:
        raw = current.get(f"{prefix}_providers") or "[]"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            prev_providers = list(parsed) if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            prev_providers = []
    prev_by_id: dict[str, dict] = {str(p.get("id", "")): p for p in prev_providers}

    providers = list(providers_in)
    # Masked api key handling: 从 current 还原真实 key
    for p in providers:
        key_raw = p.get("api_key", "") or ""
        has_masked = "api_key_masked" in p
        if has_masked and not key_raw:
            prev = prev_by_id.get(str(p.get("id", "")))
            prev_key = (prev.get("api_key") or "") if prev else ""
            # 只有当 prev_key 是真实密钥（非 masked）时才使用它还原
            if prev_key and not _is_masked_secret(prev_key):
                p["api_key"] = prev_key
                continue
            # 否则不设 api_key（后续 fallback 到 cur_key）

    effective_base = ""
    effective_key = ""
    effective_model = ""
    active = active_in
    if not active and providers:
        active = providers[0].get("id", "")

    for p in providers:
        if p.get("id", "") == active:
            effective_base = p.get("base_url", "") or cur_base
            effective_key = p.get("api_key", "") or cur_key
            effective_model = p.get("model_name", "") or cur_model
            break
    if not effective_base and providers:
        p0 = providers[0]
        effective_base = p0.get("base_url", "") or cur_base
        effective_key = p0.get("api_key", "") or cur_key
        effective_model = p0.get("model_name", "") or cur_model

    providers_json = json.dumps(providers, ensure_ascii=False)
    return providers_json, active, effective_base, effective_key, effective_model


def _normalize_frontend_theme(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in ("light", "dark", "system"):
        return v
    return "system"


def _normalize_frontend_color_scheme(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in ("green", "purple", "blue", "custom"):
        return "green" if v == "purple" else v
    return "blue"


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_DEFAULT_PRIMARY_COLOR = "#0067ff"


def _normalize_frontend_primary_color(value: str | None) -> str:
    raw = (value or "").strip()
    if _HEX_COLOR_RE.match(raw):
        return raw.lower()
    return _DEFAULT_PRIMARY_COLOR


def _rerank_env_defaults(settings: Settings) -> tuple[str, str, str]:
    """Rerank：显式 PLATFORM_RERANK_* 优先，否则回退嵌入 / VL（硅基流动等同 Key）。"""
    base = (settings.platform_rerank_base_url or "").strip()
    key = (settings.platform_rerank_api_key or "").strip()
    model = (settings.platform_rerank_model or "").strip()

    emb_base = (settings.platform_embedding_base_url or "").strip()
    emb_key = (settings.platform_embedding_api_key or "").strip()
    vl_base = (settings.platform_vl_base_url or "").strip()
    vl_key = (settings.platform_vl_api_key or "").strip()

    if not base:
        base = emb_base or vl_base
    if not key:
        key = emb_key or vl_key
    return base, key, model


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


def _tts_env_defaults(settings: Settings) -> tuple[str, str, str]:
    """语音合成：显式 PLATFORM_TTS_* 优先；否则从硅基流动等兼容端点回退（非 DeepSeek LLM）。"""
    base = (settings.platform_tts_base_url or "").strip()
    key = (settings.platform_tts_api_key or "").strip()
    model = (settings.platform_tts_model or "").strip()
    if not base or not key:
        env_merged = {
            "llm_base_url": (settings.platform_llm_base_url or "").strip()
            or (settings.deepseek_base_url or ""),
            "llm_api_key": (settings.platform_llm_api_key or "").strip()
            or (settings.deepseek_api_key or ""),
            "vl_base_url": (settings.platform_vl_base_url or "").strip(),
            "vl_api_key": (settings.platform_vl_api_key or "").strip(),
            "embedding_base_url": (settings.platform_embedding_base_url or "").strip(),
            "embedding_api_key": (settings.platform_embedding_api_key or "").strip(),
            "paddleocr_base_url": (settings.platform_paddleocr_base_url or "").strip(),
            "paddleocr_api_key": (settings.platform_paddleocr_api_key or "").strip(),
        }
        fb_base, fb_key = _pick_tts_fallback_base_key(env_merged)
        if not base:
            base = fb_base
        if not key:
            key = fb_key
    if not model:
        model = _DEFAULT_TTS_MODEL
    return base, key, model


def _env_defaults(settings: Settings) -> dict[str, str]:
    llm_url = (settings.platform_llm_base_url or "").strip() or settings.deepseek_base_url
    llm_key = (settings.platform_llm_api_key or "").strip() or settings.deepseek_api_key
    llm_model = (settings.platform_llm_model or "").strip() or settings.deepseek_model
    multimodal_url = (settings.platform_multimodal_base_url or "").strip()
    multimodal_key = (settings.platform_multimodal_api_key or "").strip()
    multimodal_model = (settings.platform_multimodal_model or "").strip()
    paddle_base, paddle_key, paddle_model, paddle_legacy_url = _paddleocr_env_defaults(settings)
    rerank_base, rerank_key, rerank_model = _rerank_env_defaults(settings)
    tts_base, tts_key, tts_model = _tts_env_defaults(settings)
    return {
        "llm_base_url": llm_url or "",
        "llm_api_key": llm_key or "",
        "llm_model": llm_model or "",
        "multimodal_base_url": multimodal_url,
        "multimodal_api_key": multimodal_key,
        "multimodal_model": multimodal_model,
        "embedding_base_url": (settings.platform_embedding_base_url or "").strip(),
        "embedding_api_key": (settings.platform_embedding_api_key or "").strip(),
        "embedding_model": (settings.platform_embedding_model or "").strip(),
        "embedding_factory": (settings.platform_embedding_factory or "").strip(),
        "rerank_base_url": rerank_base,
        "rerank_api_key": rerank_key,
        "rerank_model": rerank_model,
        "vl_base_url": (settings.platform_vl_base_url or "").strip(),
        "vl_api_key": (settings.platform_vl_api_key or "").strip(),
        "vl_model": (settings.platform_vl_model or "").strip(),
        "paddleocr_base_url": paddle_base,
        "paddleocr_api_key": paddle_key,
        "paddleocr_model": paddle_model,
        "paddleocr_url": paddle_legacy_url,
        "tts_base_url": tts_base,
        "tts_api_key": tts_key,
        "tts_model": tts_model,
        "speech_service_url": (settings.speech_service_url or "").strip(),
        "pdf2zh_api_url": (settings.pdf2zh_api_url or "").strip(),
        "platform_api_base_url": (settings.platform_api_base_url or "").strip().rstrip("/"),
        "frontend_app_title": (settings.frontend_app_title or "").strip(),
        "frontend_default_theme": _normalize_frontend_theme(settings.frontend_default_theme),
        "frontend_color_scheme": _normalize_frontend_color_scheme(settings.frontend_color_scheme),
        "frontend_primary_color": _normalize_frontend_primary_color(settings.frontend_primary_color),
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
        "firecrawl_api_key": (settings.firecrawl_api_key or "").strip(),
        "firecrawl_api_url": (settings.firecrawl_api_url or "https://api.firecrawl.dev").strip(),
        "firecrawl_read_full_max_urls": str(int(settings.firecrawl_read_full_max_urls or 3)),
        "agent_browser_enabled": str(settings.agent_browser_enabled).lower(),
        "agent_browser_headless": str(settings.agent_browser_headless).lower(),
        "agent_browser_allowed_domains": (settings.agent_browser_allowed_domains or "").strip(),
        "agent_browser_max_steps_per_session": str(settings.agent_browser_max_steps_per_session),
        "agent_browser_auto_task_enabled": str(settings.agent_browser_auto_task_enabled).lower(),
        "agent_browser_auto_task_max_steps": str(settings.agent_browser_auto_task_max_steps),
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
    # 先加载 DB 覆盖（用户已保存的配置），避免不必要的 RAGFlow 查询
    db_payload = _load_db_payload(db)
    for key, val in db_payload.items():
        if val == "":
            continue
        # 跳过已损坏的 masked API key（如 sk-d••••b550），
        # 避免覆盖 .env 中的真实密钥
        if key.endswith("_api_key") and _is_masked_secret(val):
            continue
        if key.endswith("_password") and _is_masked_secret(val):
            continue
        merged[key] = val
    # 仅当环境变量和 DB 都未配置 embedding_model 时，才从 RAGFlow 模板查询默认值
    if fill_embedding_from_ragflow and not merged.get("embedding_model"):
        rag_defaults = fetch_template_embedding_defaults(db)
        for key, val in rag_defaults.items():
            if val and not merged.get(key):
                merged[key] = val
    return merged


def get_effective_model_config(db: Session | None = None) -> dict[str, str]:
    return _merge_effective(get_settings(), db)


def get_llm_credentials(db: Session | None = None) -> tuple[str, str, str]:
    """语言模型凭证（资源管理 / .env 合并，每次调用读库）。"""
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return _endpoint_fields(merged, "llm")


def _is_masked_secret(val: str) -> bool:
    """检测值是否为 masked 格式（如 sk-d••••b550 或 sk-****550），非真实密钥。"""
    if not val:
        return False
    # mask_secret() 用 •••• 或星号变体
    return "••••" in val or "****" in val or "***" in val


def get_provider_credentials_by_id(
    provider_id: str, db: Session | None = None,
) -> tuple[str, str, str] | None:
    """按 provider_id 查凭证，跨 llm/multimodal 两种资源类型。

    返回 (api_key, base_url, model_name)，未找到时返回 None。
    当 provider 中的 api_key 为 masked 格式时，回退到 flat 字段的 {prefix}_api_key。
    """
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    for prefix in ("llm", "multimodal"):
        raw_providers = json.loads(merged.get(f"{prefix}_providers") or "[]") if isinstance(merged.get(f"{prefix}_providers"), str) else (merged.get(f"{prefix}_providers") or [])
        if not isinstance(raw_providers, list):
            continue
        active_id = merged.get(f"{prefix}_active_provider", "")
        for p in raw_providers:
            pid = p.get("id", "")
            if pid == provider_id or (provider_id == "__active__" and pid == active_id):
                key = p.get("api_key", p.get("password", p.get("api_key_masked", ""))) or ""
                base = p.get("base_url", "") or ""
                model = p.get("model_name", p.get("model", "")) or ""
                # 如果 key 是 masked 格式（曾经因 bug 被误存），回退到 flat 字段
                if key and _is_masked_secret(key):
                    flat_key = (merged.get(f"{prefix}_api_key") or "").strip()
                    if flat_key and not _is_masked_secret(flat_key):
                        key = flat_key
                return key, base, model
    return None


def get_embedding_credentials(db: Session | None = None) -> tuple[str, str, str]:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return _endpoint_fields(merged, "embedding")


def get_vl_credentials(db: Session | None = None) -> tuple[str, str, str]:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    return _endpoint_fields(merged, "vl")


def get_rerank_credentials(db: Session | None = None) -> tuple[str, str, str]:
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    base, key, model = _endpoint_fields(merged, "rerank")
    if not base or not key:
        emb_base, emb_key, _ = _endpoint_fields(merged, "embedding")
        vl_base, vl_key, _ = _endpoint_fields(merged, "vl")
        if not base:
            base = emb_base or vl_base
        if not key:
            key = emb_key or vl_key
    return base, key, model


def get_tts_credentials(db: Session | None = None) -> tuple[str, str, str]:
    """语音合成凭证（资源管理 tts_*；未填时从硅基流动等兼容端点回退）。"""
    merged = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=False)
    base, key, model = _endpoint_fields(merged, "tts")
    if not base or not key:
        fb_base, fb_key = _pick_tts_fallback_base_key(merged)
        if not base:
            base = fb_base
        if not key:
            key = fb_key
    if not model:
        model = _DEFAULT_TTS_MODEL
    return base, key, model


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


def get_firecrawl_api_key(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    return (merged.get("firecrawl_api_key") or get_settings().firecrawl_api_key or "").strip()


def get_firecrawl_api_url(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    return (merged.get("firecrawl_api_url") or get_settings().firecrawl_api_url or "https://api.firecrawl.dev").strip()


def get_firecrawl_read_full_max_urls(db: Session | None = None) -> int:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    raw = merged.get("firecrawl_read_full_max_urls")
    if raw is None or raw == "":
        return int(get_settings().firecrawl_read_full_max_urls or 3)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 3


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
    return (get_settings().app_name or "").strip() or "本析"


def get_frontend_default_theme(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    return _normalize_frontend_theme(merged.get("frontend_default_theme"))


def get_frontend_color_scheme(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    return _normalize_frontend_color_scheme(merged.get("frontend_color_scheme"))


def get_frontend_primary_color(db: Session | None = None) -> str:
    merged = _effective_config(db, fill_embedding_from_ragflow=False)
    scheme = _normalize_frontend_color_scheme(merged.get("frontend_color_scheme"))
    if scheme != "custom":
        return ""
    return _normalize_frontend_primary_color(merged.get("frontend_primary_color"))


def _build_model_settings_out(effective: dict[str, str]) -> ModelSettingsOut:
    """从有效配置字典构造 ModelSettingsOut（不读库，适用于保存后返回）。"""
    vl_base, vl_key, vl_model = _endpoint_fields(effective, "vl")
    paddle_base, paddle_key, paddle_model = _endpoint_fields(effective, "paddleocr")
    if not paddle_base:
        paddle_base = _legacy_paddleocr_base_url(effective)
    tts_base = (effective.get("tts_base_url") or "").strip()
    tts_key = (effective.get("tts_api_key") or "").strip()
    tts_model = (effective.get("tts_model") or "").strip()
    if not tts_base or not tts_key:
        fb_base, fb_key = _pick_tts_fallback_base_key(effective)
        if not tts_base:
            tts_base = fb_base
        if not tts_key:
            tts_key = fb_key
    if not tts_model:
        tts_model = _DEFAULT_TTS_MODEL
    return ModelSettingsOut(
        effective_source="platform_model_settings",
        editable=True,
        notice=NOTICE_EFFECTIVE,
        platform_api_base_url=(effective.get("platform_api_base_url") or "/ai").strip(),
        frontend_app_title=(effective.get("frontend_app_title") or "").strip(),
        frontend_default_theme=_normalize_frontend_theme(effective.get("frontend_default_theme")),
        frontend_color_scheme=_normalize_frontend_color_scheme(
            effective.get("frontend_color_scheme")
        ),
        frontend_primary_color=_normalize_frontend_primary_color(
            effective.get("frontend_primary_color")
        )
        if _normalize_frontend_color_scheme(effective.get("frontend_color_scheme")) == "custom"
        else "",
        llm=_endpoint_with_providers(effective, "llm"),
        multimodal=_endpoint_with_providers(effective, "multimodal"),
        embedding=_endpoint_with_providers(effective, "embedding"),
        vl=_endpoint_with_providers(effective, "vl", base_url=vl_base, api_key=vl_key, model_name=vl_model),
        rerank=_endpoint_with_providers(effective, "rerank"),
        paddleocr=_endpoint_with_providers(effective, "paddleocr", base_url=paddle_base, api_key=paddle_key, model_name=paddle_model),
        paddleocr_url=paddle_base or effective.get("paddleocr_url") or "",
        tts=_endpoint_with_providers(effective, "tts", base_url=tts_base, api_key=tts_key, model_name=tts_model),
        speech_service_url=effective.get("speech_service_url") or "",
        pdf2zh_api_url=effective.get("pdf2zh_api_url") or "",
        embedding_factory=effective.get("embedding_factory") or None,
        searxng_url=effective.get("searxng_url") or "",
        searxng_timeout_seconds=float(effective.get("searxng_timeout_seconds") or 15.0),
        firecrawl_api_key=mask_secret(effective.get("firecrawl_api_key") or ""),
        firecrawl_api_url=(effective.get("firecrawl_api_url") or "https://api.firecrawl.dev").strip(),
        firecrawl_read_full_max_urls=int(effective.get("firecrawl_read_full_max_urls") or 3),
        agent_browser_enabled=(effective.get("agent_browser_enabled") or "false").lower()
        in {"1", "true", "yes", "on"},
        agent_browser_headless=(effective.get("agent_browser_headless") or "true").lower()
        not in {"0", "false", "no", "off"},
        agent_browser_allowed_domains=effective.get("agent_browser_allowed_domains") or "",
        agent_browser_max_steps_per_session=int(
            effective.get("agent_browser_max_steps_per_session") or 50
        ),
        agent_browser_auto_task_enabled=(
            effective.get("agent_browser_auto_task_enabled") or "true"
        ).lower()
        not in {"0", "false", "no", "off"},
        agent_browser_auto_task_max_steps=int(
            effective.get("agent_browser_auto_task_max_steps") or 15
        ),
        knowledge=_knowledge_infra_out(effective),
    )


def get_model_settings(
    db: Session | None = None, *, fill_embedding_from_ragflow: bool = True
) -> ModelSettingsOut:
    effective = _merge_effective(get_settings(), db, fill_embedding_from_ragflow=fill_embedding_from_ragflow)
    return _build_model_settings_out(effective)


def _keep_secret(incoming: str | None, previous: str) -> str:
    if incoming is None:
        return previous
    val = (incoming or "").strip()
    if not val or val == mask_secret(previous):
        return previous
    return val


def _apply_providers_to_payload(
    payload: dict[str, str],
    body: ModelSettingsUpdate,
    current: dict[str, str],
    prefix: str,
) -> dict[str, str]:
    """处理 provider 更新：如果 body 包含 providers，则计算 flat 字段并存储 providers/active_provider。"""
    providers_attr = f"{prefix}_providers"
    active_attr = f"{prefix}_active_provider"
    providers_in = getattr(body, providers_attr, None)
    active_in = getattr(body, active_attr, None)

    if providers_in is None:
        return payload

    prov_json, active, eff_base, eff_key, eff_model = _provider_payload_from_update(
        [p.model_dump() for p in providers_in],
        active_in,
        payload.get(f"{prefix}_base_url", ""),
        payload.get(f"{prefix}_api_key", ""),
        payload.get(f"{prefix}_model", ""),
        current=current,
        prefix=prefix,
    )

    if prov_json:
        payload[f"{prefix}_providers"] = prov_json
        payload[f"{prefix}_active_provider"] = active
        if eff_base:
            payload[f"{prefix}_base_url"] = eff_base
        if eff_key:
            for p in providers_in:
                if p.id == active and p.api_key:
                    payload[f"{prefix}_api_key"] = p.api_key
                    break
        if eff_model:
            payload[f"{prefix}_model"] = eff_model
    return payload


def _sync_ragflow_after_save(payload: dict[str, str]) -> None:
    """后台线程：将模型配置同步到 RAGFlow / KnowFlow（不阻塞平台 HTTP 响应）。"""
    try:
        from app.database import SessionLocal

        with SessionLocal() as session:
            apply_saved_settings(session, payload)
    except Exception as exc:
        logger.warning("后台同步配置到知识库失败: %s", exc, exc_info=True)


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
        "multimodal_base_url": (
            body.multimodal_base_url
            if body.multimodal_base_url is not None
            else current.get("multimodal_base_url", "")
        ),
        "multimodal_model": (
            body.multimodal_model
            if body.multimodal_model is not None
            else current.get("multimodal_model", "")
        ),
        "multimodal_api_key": _keep_secret(
            body.multimodal_api_key, current.get("multimodal_api_key", "")
        ),
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
        "tts_base_url": (
            body.tts_base_url if body.tts_base_url is not None else current.get("tts_base_url", "")
        ),
        "tts_model": (
            body.tts_model if body.tts_model is not None else current.get("tts_model", "")
        ),
        "tts_api_key": _keep_secret(body.tts_api_key, current.get("tts_api_key", "")),
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
        "frontend_color_scheme": (
            _normalize_frontend_color_scheme(body.frontend_color_scheme)
            if body.frontend_color_scheme is not None
            else _normalize_frontend_color_scheme(current.get("frontend_color_scheme"))
        ),
        "frontend_primary_color": (
            _normalize_frontend_primary_color(body.frontend_primary_color)
            if body.frontend_primary_color is not None
            else _normalize_frontend_primary_color(current.get("frontend_primary_color"))
            if (
                _normalize_frontend_color_scheme(
                    body.frontend_color_scheme
                    if body.frontend_color_scheme is not None
                    else current.get("frontend_color_scheme")
                )
                == "custom"
            )
            else ""
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
        "firecrawl_api_key": _keep_secret(
            body.firecrawl_api_key, current.get("firecrawl_api_key", "")
        ),
        "firecrawl_api_url": (
            (body.firecrawl_api_url or "https://api.firecrawl.dev").strip()
            if body.firecrawl_api_url is not None
            else current.get("firecrawl_api_url", "https://api.firecrawl.dev")
        ),
        "firecrawl_read_full_max_urls": (
            str(max(0, int(body.firecrawl_read_full_max_urls)))
            if body.firecrawl_read_full_max_urls is not None
            else current.get("firecrawl_read_full_max_urls", "3")
        ),
        "agent_browser_enabled": (
            str(bool(body.agent_browser_enabled)).lower()
            if body.agent_browser_enabled is not None
            else current.get("agent_browser_enabled", "false")
        ),
        "agent_browser_headless": (
            str(bool(body.agent_browser_headless)).lower()
            if body.agent_browser_headless is not None
            else current.get("agent_browser_headless", "true")
        ),
        "agent_browser_allowed_domains": (
            (body.agent_browser_allowed_domains or "").strip()
            if body.agent_browser_allowed_domains is not None
            else current.get("agent_browser_allowed_domains", "")
        ),
        "agent_browser_max_steps_per_session": (
            str(max(1, int(body.agent_browser_max_steps_per_session)))
            if body.agent_browser_max_steps_per_session is not None
            else current.get("agent_browser_max_steps_per_session", "50")
        ),
        "agent_browser_auto_task_enabled": (
            str(bool(body.agent_browser_auto_task_enabled)).lower()
            if body.agent_browser_auto_task_enabled is not None
            else current.get("agent_browser_auto_task_enabled", "true")
        ),
        "agent_browser_auto_task_max_steps": (
            str(max(1, int(body.agent_browser_auto_task_max_steps)))
            if body.agent_browser_auto_task_max_steps is not None
            else current.get("agent_browser_auto_task_max_steps", "15")
        ),
    }

    # 处理各模型类型的 provider 更新（覆盖 flat 字段）
    for prefix in ("llm", "multimodal", "embedding", "vl", "rerank", "paddleocr", "tts"):
        payload = _apply_providers_to_payload(payload, body, current, prefix)

    row = db.get(PlatformModelSettings, SINGLETON_ID)
    if row is None:
        row = PlatformModelSettings(id=SINGLETON_ID, payload=payload)
        db.add(row)
    else:
        row.payload = payload
    db.commit()

    try:
        from app.core.platform_cache import invalidate_system_config_cache

        invalidate_system_config_cache()
    except Exception:
        pass

    # 将配置同步到 RAGFlow/KnowFlow 在后台执行，不阻塞 HTTP 响应
    try:
        from app.core.background_executor import submit_background

        submit_background("sync-model-settings", _sync_ragflow_after_save, payload)
    except Exception:
        logger.warning("提交后台同步任务失败", exc_info=True)

    effective = dict(_env_defaults(get_settings()))
    for k, v in payload.items():
        if v:
            effective[k] = v
    return _build_model_settings_out(effective)


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
    rerank_base, rerank_key, rerank_model = _endpoint_fields(payload, "rerank")
    if not rerank_base or not rerank_key:
        emb_base, emb_key, _ = _endpoint_fields(payload, "embedding")
        if not rerank_base:
            rerank_base = emb_base or vl_base
        if not rerank_key:
            rerank_key = emb_key or vl_key
    if rerank_key and rerank_model:
        apply_rerank_to_template_tenant(
            db,
            base_url=rerank_base,
            api_key=rerank_key,
            model_name=rerank_model,
            factory=payload.get("embedding_factory", ""),
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
