"""系统资源配置（模型、OCR、语音、翻译等）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelEndpointOut(BaseModel):
    base_url: str = ""
    api_key_configured: bool = False
    api_key_masked: str = ""
    model_name: str | None = None


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
    color_scheme: str = "purple"


class ModelSettingsOut(BaseModel):
    effective_source: str = Field(default="environment")
    editable: bool = False
    notice: str = ""
    platform_api_base_url: str = ""
    frontend_app_title: str = ""
    frontend_default_theme: str = "system"
    frontend_color_scheme: str = "purple"
    llm: ModelEndpointOut
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
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_factory: str | None = None
    rerank_base_url: str | None = None
    rerank_api_key: str | None = None
    rerank_model: str | None = None
    vl_base_url: str | None = None
    vl_api_key: str | None = None
    vl_model: str | None = None
    # 兼容旧字段名 vision_*（与 vl_* 等价）
    vision_base_url: str | None = None
    vision_api_key: str | None = None
    vision_model: str | None = None
    paddleocr_base_url: str | None = None
    paddleocr_api_key: str | None = None
    paddleocr_model: str | None = None
    paddleocr_url: str | None = None
    tts_base_url: str | None = None
    tts_api_key: str | None = None
    tts_model: str | None = None
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
    agent_browser_enabled: bool | None = None
    agent_browser_headless: bool | None = None
    agent_browser_allowed_domains: str | None = None
    agent_browser_max_steps_per_session: int | None = None
    agent_browser_auto_task_enabled: bool | None = None
    agent_browser_auto_task_max_steps: int | None = None


class ResourceHealthItemOut(BaseModel):
    configured: bool = False
    healthy: bool | None = None
    message: str = ""


class ResourceHealthOut(BaseModel):
    items: dict[str, ResourceHealthItemOut] = Field(default_factory=dict)


class ResourceHealthTestIn(BaseModel):
    """保存前按表单草稿探测单项连通性。"""

    resource_id: str
    draft: ModelSettingsUpdate = Field(default_factory=ModelSettingsUpdate)
