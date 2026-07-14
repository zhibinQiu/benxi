"""系统资源配置（模型、OCR、语音、翻译等）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderEndpointOut(BaseModel):
    """单个服务源配置（响应用户端）。"""

    id: str = ""
    label: str = ""
    base_url: str = ""
    api_key_configured: bool = False
    api_key_masked: str = ""
    model_name: str | None = None


class ProviderEndpointUpdate(BaseModel):
    """单个服务源配置（用户提交）。"""

    id: str = ""
    label: str = ""
    base_url: str = ""
    api_key: str = ""
    model_name: str | None = None


class ModelEndpointOut(BaseModel):
    base_url: str = ""
    api_key_configured: bool = False
    api_key_masked: str = ""
    model_name: str | None = None
    providers: list[ProviderEndpointOut] = Field(default_factory=list)
    active_provider: str = ""


class KnowledgeInfraOut(BaseModel):
    """KnowFlow / RAGFlow 知识库后台与数据库连接。"""

    knowflow_enabled: bool = False
    ragflow_api_url: str = ""
    ragflow_api_key_configured: bool = False
    ragflow_api_key_masked: str = ""
    knowflow_backend_url: str = ""
    knowflow_ui_url: str = ""
    knowflow_ui_public_url: str = ""
    knowflow_ui_proxy_prefix: str = ""
    ragflow_mysql_host: str = ""
    ragflow_mysql_port: int = 3306
    ragflow_mysql_db: str = ""
    ragflow_mysql_password_configured: bool = False
    ragflow_mysql_password_masked: str = ""
    ragflow_mysql_container: str = ""


class ClientConfigOut(BaseModel):
    """前端启动时拉取的公开配置（无需登录）。"""

    api_base: str = ""
    app_title: str = ""
    default_theme: str = "system"
    color_scheme: str = "blue"
    primary_color: str = ""


class ModelSettingsOut(BaseModel):
    effective_source: str = Field(default="environment")
    editable: bool = False
    notice: str = ""
    platform_api_base_url: str = ""
    frontend_app_title: str = ""
    frontend_default_theme: str = "system"
    frontend_color_scheme: str = "blue"
    frontend_primary_color: str = ""
    llm: ModelEndpointOut
    multimodal: ModelEndpointOut
    embedding: ModelEndpointOut
    vl: ModelEndpointOut
    rerank: ModelEndpointOut
    knowledge: KnowledgeInfraOut
    paddleocr: ModelEndpointOut
    paddleocr_url: str = ""
    tts: ModelEndpointOut
    speech_service_url: str = ""
    pdf2zh_api_url: str = ""
    embedding_factory: str | None = None
    searxng_url: str = ""
    searxng_timeout_seconds: float = 15.0
    firecrawl_api_key: str = ""
    firecrawl_api_url: str = "https://api.firecrawl.dev"
    firecrawl_read_full_max_urls: int = 3
    agent_browser_enabled: bool = False
    agent_browser_headless: bool = True
    agent_browser_allowed_domains: str = ""
    agent_browser_max_steps_per_session: int = 50
    agent_browser_auto_task_enabled: bool = True
    agent_browser_auto_task_max_steps: int = 15


class ModelSettingsUpdate(BaseModel):
    platform_api_base_url: str | None = None
    frontend_app_title: str | None = None
    frontend_default_theme: str | None = None
    frontend_color_scheme: str | None = None
    frontend_primary_color: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_providers: list[ProviderEndpointUpdate] | None = None
    llm_active_provider: str | None = None
    multimodal_base_url: str | None = None
    multimodal_api_key: str | None = None
    multimodal_model: str | None = None
    multimodal_providers: list[ProviderEndpointUpdate] | None = None
    multimodal_active_provider: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_factory: str | None = None
    embedding_providers: list[ProviderEndpointUpdate] | None = None
    embedding_active_provider: str | None = None
    rerank_base_url: str | None = None
    rerank_api_key: str | None = None
    rerank_model: str | None = None
    rerank_providers: list[ProviderEndpointUpdate] | None = None
    rerank_active_provider: str | None = None
    vl_base_url: str | None = None
    vl_api_key: str | None = None
    vl_model: str | None = None
    vl_providers: list[ProviderEndpointUpdate] | None = None
    vl_active_provider: str | None = None
    # 兼容旧字段名 vision_*（与 vl_* 等价）
    vision_base_url: str | None = None
    vision_api_key: str | None = None
    vision_model: str | None = None
    paddleocr_base_url: str | None = None
    paddleocr_api_key: str | None = None
    paddleocr_model: str | None = None
    paddleocr_url: str | None = None
    paddleocr_providers: list[ProviderEndpointUpdate] | None = None
    paddleocr_active_provider: str | None = None
    tts_base_url: str | None = None
    tts_api_key: str | None = None
    tts_model: str | None = None
    tts_providers: list[ProviderEndpointUpdate] | None = None
    tts_active_provider: str | None = None
    speech_service_url: str | None = None
    pdf2zh_api_url: str | None = None
    ragflow_api_url: str | None = None
    ragflow_api_key: str | None = None
    knowflow_backend_url: str | None = None
    knowflow_ui_url: str | None = None
    knowflow_ui_public_url: str | None = None
    knowflow_ui_proxy_prefix: str | None = None
    ragflow_mysql_host: str | None = None
    ragflow_mysql_port: int | None = None
    ragflow_mysql_db: str | None = None
    ragflow_mysql_password: str | None = None
    ragflow_mysql_container: str | None = None
    searxng_url: str | None = None
    searxng_timeout_seconds: float | None = None
    firecrawl_api_key: str | None = None
    firecrawl_api_url: str | None = None
    firecrawl_read_full_max_urls: int | None = None
    agent_browser_enabled: bool | None = None
    agent_browser_headless: bool | None = None
    agent_browser_allowed_domains: str | None = None
    agent_browser_max_steps_per_session: int | None = None
    agent_browser_auto_task_enabled: bool | None = None
    agent_browser_auto_task_max_steps: int | None = None


class ProviderHealthItemOut(BaseModel):
    """单个服务源（provider）的连通性探测结果。"""

    provider_id: str = ""
    provider_label: str = ""
    configured: bool = False
    healthy: bool | None = None
    message: str = ""


class ResourceHealthItemOut(BaseModel):
    configured: bool = False
    healthy: bool | None = None
    message: str = ""
    providers: list[ProviderHealthItemOut] = Field(default_factory=list)


class ResourceHealthOut(BaseModel):
    items: dict[str, ResourceHealthItemOut] = Field(default_factory=dict)


class ResourceHealthTestIn(BaseModel):
    """保存前按表单草稿探测单项连通性。"""

    resource_id: str
    draft: ModelSettingsUpdate = Field(default_factory=ModelSettingsUpdate)
