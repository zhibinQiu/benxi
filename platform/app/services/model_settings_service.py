"""从环境变量组装系统模型配置（只读展示）。"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.schemas.model_settings import ModelEndpointOut, ModelSettingsOut

NOTICE = (
    "本页配置暂不生效，仅供查看与规划。实际调用请以服务器环境变量（platform/.env）为准，"
    "修改后需重启平台 API。知识问答的模型供应商在知识服务管理界面维护。"
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


def _resolve_llm(settings: Settings) -> ModelEndpointOut:
    url = (settings.platform_llm_base_url or "").strip() or settings.deepseek_base_url
    key = (settings.platform_llm_api_key or "").strip() or settings.deepseek_api_key
    model = (settings.platform_llm_model or "").strip() or settings.deepseek_model
    return _endpoint(base_url=url, api_key=key, model_name=model)


def _resolve_embedding(settings: Settings) -> ModelEndpointOut:
    return _endpoint(
        base_url=settings.platform_embedding_base_url,
        api_key=settings.platform_embedding_api_key,
    )


def _resolve_rerank(settings: Settings) -> ModelEndpointOut:
    return _endpoint(
        base_url=settings.platform_rerank_base_url,
        api_key=settings.platform_rerank_api_key,
    )


def get_model_settings() -> ModelSettingsOut:
    settings = get_settings()
    return ModelSettingsOut(
        effective_source="environment",
        editable=False,
        notice=NOTICE,
        llm=_resolve_llm(settings),
        embedding=_resolve_embedding(settings),
        rerank=_resolve_rerank(settings),
    )
