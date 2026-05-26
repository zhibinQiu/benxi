from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PLATFORM_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _PLATFORM_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "智碳平台AI系统"
    platform_version: str = "2.6.2"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = (
        "postgresql+psycopg2://platform:platform@127.0.0.1:5432/platform"
    )

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8
    refresh_token_expire_days: int = 7

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"
    minio_secure: bool = False
    minio_region: str = "us-east-1"

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_email: str = "admin@local"
    allow_public_register: bool = True

    cors_origins: str = "*"

    pdf2zh_api_url: str = "http://127.0.0.1:7861"

    knowflow_enabled: bool = False
    knowflow_backend_url: str = "http://127.0.0.1:5001"
    # KnowFlow / RAGFlow 自带 Web UI（须直连源站以保留溯源、PDF 定位等能力）
    knowflow_ui_url: str = "http://127.0.0.1:9380"
    # iframe：平台内嵌完整界面；redirect：跳转至源站全屏
    knowflow_ui_embed_mode: str = "iframe"
    ragflow_api_url: str = "http://127.0.0.1:9380"
    ragflow_api_key: str = ""
    # mapped：每平台用户独立 RAGFlow 账号（推荐，文档权限可隔离）
    # shared：全员共用管理员（仅开发/演示，无法隔离文档）
    ragflow_account_mode: str = "mapped"
    ragflow_shared_email: str = "admin@gmail.com"
    ragflow_shared_password: str = "admin"
    # mapped 下应为 false；shared 演示环境可为 true 以便创建知识库
    ragflow_grant_global_admin: bool = False
    ragflow_mysql_container: str = "ragflow-mysql"
    ragflow_mysql_password: str = "infini_rag_flow"
    ragflow_mysql_db: str = "rag_flow"
    # 已废弃全局单库；每用户使用 zt-platform-{user_id}
    ragflow_dataset_name: str = "智碳平台知识库"
    ragflow_dataset_prefix: str = "zt-platform"
    ragflow_personal_dataset_prefix: str = "zt-personal"
    ragflow_company_dataset_name: str = "zt-company"
    ragflow_dept_dataset_prefix: str = "zt-dept"
    ragflow_sync_doc_limit: int = 50
    # 平台登录后后台同步可访问文档到该用户知识库（mapped 推荐开启）
    ragflow_sync_on_login: bool = True
    ragflow_sync_on_login_limit: int = 30
    # 进入知识问答页时是否同步文档（关闭可加快首屏）
    ragflow_sync_on_embed: bool = False
    # 新用户/登录时从 RAGFlow 模板账号复制模型供应商与 API（全员共用，默认开启）
    ragflow_llm_shared_from_template: bool = True
    # 模板账号邮箱，留空则用 RAGFLOW_SHARED_EMAIL 或 admin@gmail.com
    ragflow_llm_template_email: str = ""
    # 开发环境前端代理前缀，如 /ragflow-ui（同源，供阶段 2 SSO）
    knowflow_ui_proxy_prefix: str = ""
    knowflow_theme_primary: str = "#18a058"
    knowflow_theme_primary_hover: str = "#36ad6a"
    knowflow_theme_primary_pressed: str = "#0c7a43"
    knowflow_theme_app_name: str = "智碳平台AI系统"
    knowflow_theme_logo_url: str = "/logo.svg"
    knowflow_theme_favicon_url: str = "/favicon.svg"
    knowflow_hide_file_manager: bool = True

    # 录音转文字（FunASR Docker 服务）
    speech_service_url: str = "http://127.0.0.1:8765"
    funasr_asr_model: str = "paraformer-zh"
    diarization_enabled: bool = True
    stt_language: str = "zh"
    stt_max_file_mb: int = 100

    # 录音总结（DeepSeek 在线 API，可与 pdf2zh 翻译共用密钥）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_max_chars: int = 12000

    # 系统设置 · 模型配置（页面只读展示；未单独配置时语言模型回退 deepseek_*）
    platform_llm_base_url: str = ""
    platform_llm_api_key: str = ""
    platform_llm_model: str = ""
    platform_embedding_base_url: str = ""
    platform_embedding_api_key: str = ""
    platform_rerank_base_url: str = ""
    platform_rerank_api_key: str = ""

    # 智能问数（设计系统 iframe）
    # 设计系统（智能问数）— 经同源 Nginx/Vite 代理，避免 iframe 跨域
    # embed：path=/ai 同源反代（推荐）；api=embed-proxy（不适配 /ai/_next 静态资源）；vite=/design-system-ui
    embed_proxy_mode: str = "path"
    design_system_upstream_url: str = "http://172.19.134.45:40001"
    design_system_proxy_prefix: str = "/design-system-ui"
    smart_data_query_path: str = "/ai/smart-data-query"
    # 智能问数 v2（对话 API，密钥勿提交仓库）
    smart_data_query_v2_dify_base_url: str = "http://172.19.134.45:40001/v1"
    smart_data_query_v2_dify_api_key: str = ""
    # 双碳问答 v2（对话 API 地址与问数一致，应用密钥独立）
    carbon_qa_v2_chat_base_url: str = "http://172.19.134.45:40001/v1"
    carbon_qa_v2_chat_api_key: str = ""
    carbon_qa_path: str = "/ai/retrieval"
    carbon_ai_v1_path: str = "/ai"
    # 智能预测：direct=直连上游（无需登录）；vite=前端 /smart-forecast-ui 代理
    smart_forecast_embed_mode: str = "direct"
    smart_forecast_upstream_url: str = "http://127.0.0.1:8501"
    smart_forecast_proxy_prefix: str = "/smart-forecast-ui"
    carbon_platform_url: str = (
        "http://carbon3.hy.05351757.xyz/login?redirect=/index"
    )

    @property
    def broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
