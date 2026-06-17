from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLATFORM_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _PLATFORM_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "企业 AI 知识库平台"
    platform_version: str = "4.0.7"
    debug: bool = False
    debug_sql: bool = False
    remote_deps: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = (
        "postgresql+psycopg2://platform:platform@127.0.0.1:5432/platform"
    )
    # SQLAlchemy 连接池（200 人在线建议单进程 DB_POOL_SIZE=20 DB_MAX_OVERFLOW=20，多 worker 需分摊 PG max_connections）
    db_pool_size: int = 15
    db_max_overflow: int = 15
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_connect_timeout: int = 10
    # 进程内有界后台池（Celery 不可用时的兜底；登录预热等轻任务）
    background_job_max_workers: int = 4
    # 重任务（文档索引/导入/上传后处理）优先走 Celery 队列
    background_jobs_use_celery: bool = True
    # auto：schema 版本已对齐则仅同步种子数据；full/light/off 强制全量/轻量/跳过
    db_startup_bootstrap: str = "auto"

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

    bootstrap_admin_phone: str = "admin"  # 唯一系统管理员登录账号（存 users.phone）
    bootstrap_admin_display_name: str = "系统管理员"
    bootstrap_admin_username: str = "admin"  # 兼容旧配置，等同显示名
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_email: str = "admin@local"
    allow_public_register: bool = True

    cors_origins: str = "*"
    # 系统说明文档根目录（默认：仓库根或容器内 /app/system-docs）
    system_docs_root: str = ""
    # 经网关对外暴露时的路径前缀（如 http://<IP>/ai/api/v1）；后端仍注册 /api/v1
    api_public_path_prefix: str = "/ai"

    pdf2zh_api_url: str = "http://127.0.0.1:7861"

    knowflow_enabled: bool = False
    knowflow_backend_url: str = "http://127.0.0.1:5001"
    # KnowFlow / RAGFlow 自带 Web UI（浏览器 iframe 基址见 knowflow_ui_public_url）
    knowflow_ui_url: str = "http://127.0.0.1:9380"
    # embed-proxy 反代上游（Docker 栈内通常为 http://ragflow:80）
    knowflow_ui_upstream_url: str = ""
    # 浏览器 iframe 完整基址（如 http://127.0.0.1:40005/ragflow-ui）；留空则用 proxy 前缀
    knowflow_ui_public_url: str = ""
    # iframe：平台内嵌完整界面；redirect：跳转至源站全屏
    knowflow_ui_embed_mode: str = "iframe"
    ragflow_api_url: str = "http://127.0.0.1:9380"
    ragflow_api_key: str = ""
    # RAGFlow HTTP：remote-dev 默认 12s；0 表示按环境自动（远程 12 / 本地 30）
    ragflow_http_timeout: float = 0
    # 连续失败后熔断秒数（逐次递增，上限 120s）
    ragflow_http_cooldown_sec: int = 20
    # 远程 RAGFlow MySQL（TCP）超时，避免拖垮 API
    ragflow_mysql_connect_timeout: int = 5
    ragflow_mysql_read_timeout: int = 8
    ragflow_mysql_write_timeout: int = 10
    # mapped：每平台用户独立 RAGFlow 账号（推荐，文档权限可隔离）
    # shared：全员共用管理员（仅开发/演示，无法隔离文档）
    ragflow_account_mode: str = "mapped"
    ragflow_shared_email: str = "admin@gmail.com"
    ragflow_shared_password: str = "admin"
    # KnowFlow 分级知识库需用户能创建 dataset；mapped 模式默认开启（经 KnowFlow RBAC）
    ragflow_grant_global_admin: bool = True
    ragflow_mysql_container: str = "ragflow-mysql"
    ragflow_mysql_password: str = "infini_rag_flow"
    ragflow_mysql_db: str = "rag_flow"
    # 容器内直连 KnowFlow MySQL（优先于 docker exec，供模型配置同步）
    ragflow_mysql_host: str = ""
    ragflow_mysql_port: int = 3306
    # 已废弃全局单库；每用户使用 zt-platform-{user_id}
    ragflow_dataset_name: str = "平台知识库"
    ragflow_dataset_prefix: str = "zt-platform"
    ragflow_personal_dataset_prefix: str = "zt-personal"
    ragflow_company_dataset_name: str = "zt-company"
    ragflow_dept_dataset_prefix: str = "zt-dept"
    ragflow_sync_doc_limit: int = 100
    # 平台登录后全量同步文档（耗时长，建议关闭；进入知识问答页时由 embed 触发）
    ragflow_sync_on_login: bool = False
    ragflow_sync_on_login_limit: int = 50
    # 进入知识问答页时是否同步文档（关闭可加快首屏；前端可后台 sync=1 补同步）
    ragflow_sync_on_embed: bool = False
    # 新用户/登录时从 RAGFlow 模板账号复制模型供应商与 API（全员共用，默认开启）
    ragflow_llm_shared_from_template: bool = True
    # 模板账号邮箱，留空则用 bootstrap 平台账号 / 已配置最全的租户 / admin@gmail.com
    ragflow_llm_template_email: str = ""
    # 模板租户 RAGFlow user id（留空则自动解析）
    ragflow_llm_template_tenant_id: str = ""
    # 开发环境前端代理前缀，如 /ragflow-ui（同源，供阶段 2 SSO）
    knowflow_ui_proxy_prefix: str = ""
    knowflow_theme_primary: str = "#18a058"
    knowflow_theme_primary_hover: str = "#36ad6a"
    knowflow_theme_primary_pressed: str = "#0c7a43"
    knowflow_theme_app_name: str = "企业 AI 知识库平台"
    knowflow_theme_logo_url: str = "/logo.svg"
    knowflow_theme_favicon_url: str = "/favicon.svg"
    knowflow_hide_file_manager: bool = True

    # 录音转文字（FunASR Docker 服务）
    speech_service_url: str = "http://127.0.0.1:8765"
    funasr_asr_model: str = "paraformer-zh"
    diarization_enabled: bool = True
    stt_language: str = "zh"
    stt_max_file_mb: int = 100

    # 文档中心单文件上传上限（MB）
    document_upload_max_file_mb: int = 200

    # 单文档版本 Git 仓库存储根目录（每文档一个 repo，用于 git diff 版本对比）
    document_git_repos_root: str = ""

    # 知识库默认解析配置（上传同步 / 自动推断）
    knowledge_default_parser_id: str = "naive"
    # 重新索引弹窗与后台任务的默认分块方式
    knowledge_reindex_default_parser_id: str = "pageindex"
    knowledge_default_layout_recognize: str = "DeepDOC"
    knowledge_default_chunk_token_num: int = 512
    # 文档列表是否实时拉 RAGFlow 解析进度（关闭后仅读库内 index_completed_at，1000+ 文档列表显著加快）
    knowledge_list_live_index_meta: bool = False
    # 文档详情是否实时拉 RAGFlow 解析进度（默认关闭，显著加快详情首屏；刷新可传 live_index=1）
    knowledge_detail_live_index_meta: bool = False
    knowledge_ragflow_meta_cache_ttl_sec: int = 60
    # 知识库解析等待：主任务线程内最长阻塞（秒），超时后转后台续跑，不判失败
    knowledge_parse_initial_wait_sec: int = 1800
    # 后台续跑最长总时长（秒），大文件 / 繁忙队列下自动延长等待
    knowledge_parse_max_wait_sec: int = 86400
    # 解析仍进行中时，每次软延长等待（秒）
    knowledge_parse_soft_extend_sec: int = 600
    # 轮询 RAGFlow 解析状态间隔（秒）
    knowledge_parse_poll_interval_sec: int = 5
    # 解析中途失败（超时、繁忙等）时自动重新提交解析的最大次数
    knowledge_parse_max_retries: int = 12
    # 每次自动重试解析前的等待（秒）
    knowledge_parse_retry_delay_sec: int = 90
    # 知识检索混合检索：向量相似度权重（其余为关键词权重，默认 0.3 / 0.7）
    knowledge_retrieval_vector_weight: float = 0.3
    # 知识检索召回条数（与 KnowFlow 对话默认可视引用接近，默认 5）
    knowledge_retrieval_top_k: int = 5
    # 向量相似度下限，低于此的 chunk 不进入引用（KnowFlow 默认约 0.2，略提高以减少弱相关引用）
    knowledge_retrieval_similarity_threshold: float = 0.32
    # Agentic RAG：LLM 规划子问题、多轮 retrieve_hits_for_qa 与充足性评估
    knowledge_agentic_enabled: bool = True
    knowledge_agentic_max_rounds: int = 2
    knowledge_agentic_qa_max_sub_questions: int = 4
    knowledge_agentic_report_max_sub_questions: int = 6

    # PageIndex 树形索引（独立于 KnowFlow；文档详情「结构索引」与知识检索自动切换）
    pageindex_enabled: bool = True
    pageindex_workspace_dir: str = ""
    pageindex_model: str = ""

    redis_socket_timeout_sec: float = 0.5

    # 平台 Redis/内存缓存（文档库分级、文件夹列表等；Redis 不可用时自动降级为进程内 TTL）
    platform_cache_enabled: bool = True
    platform_cache_ttl_sec: int = 60
    document_library_cache_ttl_sec: int = 180
    kb_folders_cache_ttl_sec: int = 120
    scope_tree_cache_ttl_sec: int = 300

    # 录音总结（DeepSeek 在线 API，可与 pdf2zh 翻译共用密钥）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_max_chars: int = 12000

    # 知识图谱：索引完成后 LLM 自动抽取实体/关系
    kg_extraction_enabled: bool = True
    kg_extraction_max_chars: int = 10000

    # 系统设置 · 模型配置（页面只读展示；未单独配置时语言模型回退 deepseek_*）
    platform_llm_base_url: str = ""
    platform_llm_api_key: str = ""
    platform_llm_model: str = ""
    platform_embedding_base_url: str = ""
    platform_embedding_api_key: str = ""
    platform_embedding_model: str = ""
    platform_embedding_factory: str = ""
    platform_rerank_base_url: str = ""
    platform_rerank_api_key: str = ""
    platform_rerank_model: str = ""
    # VL 模型（KnowFlow IMAGE2TEXT / PDF 图表增强）
    platform_vl_base_url: str = ""
    platform_vl_api_key: str = ""
    platform_vl_model: str = ""
    # 语音合成（硅基流动 / OpenAI 兼容 /v1/audio/speech）
    platform_tts_base_url: str = ""
    platform_tts_api_key: str = ""
    platform_tts_model: str = ""

    @model_validator(mode="after")
    def _apply_legacy_vl_env_aliases(self) -> "Settings":
        """兼容旧环境变量 PLATFORM_VISION_*（曾用 vision 命名）。"""
        if not (self.platform_vl_base_url or "").strip():
            self.platform_vl_base_url = os.environ.get("PLATFORM_VISION_BASE_URL", "").strip()
        if not (self.platform_vl_api_key or "").strip():
            self.platform_vl_api_key = os.environ.get("PLATFORM_VISION_API_KEY", "").strip()
        if not os.environ.get("PLATFORM_VL_MODEL", "").strip():
            legacy_model = os.environ.get("PLATFORM_VISION_MODEL", "").strip()
            if legacy_model:
                self.platform_vl_model = legacy_model
        return self
    platform_paddleocr_url: str = ""
    # PaddleOCR-VL：OpenAI 兼容推理地址或自建 layout-parsing 根地址
    platform_paddleocr_base_url: str = ""
    platform_paddleocr_api_key: str = ""
    platform_paddleocr_model: str = ""
    platform_api_base_url: str = ""
    frontend_app_title: str = ""
    frontend_default_theme: str = "system"

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
    carbon_platform_url: str = (
        "http://carbon3.hy.05351757.xyz/login?redirect=/index"
    )
    # 智能预测：direct=直连上游（无需登录）；vite=前端 /smart-forecast-ui 代理
    smart_forecast_embed_mode: str = "direct"
    smart_forecast_upstream_url: str = "http://127.0.0.1:8501"
    smart_forecast_proxy_prefix: str = "/smart-forecast-ui"

    # 碳资产行情（CEA：上海环交所官网；可选 JSON 覆盖）
    carbon_market_live_enabled: bool = True
    carbon_market_cneeex_base_url: str = "https://www.cneeex.com"
    carbon_market_cache_ttl_seconds: int = 900
    carbon_market_fetch_timeout_seconds: float = 15.0
    carbon_market_quotes_json_url: str = ""
    # CCER：全国温室气体自愿减排交易系统日行情（ccer.com.cn）
    carbon_market_ccer_base_url: str = "https://www.ccer.com.cn"
    carbon_market_ccer_use_llm_parse: bool = False
    # 无 CCER 官方源时，按 CEA 收盘价比例生成参考价（0 表示不估算）
    carbon_market_ccer_cea_ratio: float = 0.8
    carbon_market_history_max_fetch: int = 30
    # CEA 历史日行情：收盘后定时同步（上海时区）
    carbon_market_history_sync_hour: int = 18
    carbon_market_history_sync_minute: int = 0

    # 数据分析（Excel + Notebook 代码执行）
    data_analysis_storage_dir: str = ""
    data_analysis_max_file_mb: int = 50
    data_analysis_exec_timeout_seconds: int = 60

    # 网站收藏 · 在线搜索（SearXNG JSON API 基址，如 http://host:8080）
    searxng_url: str = ""
    searxng_timeout_seconds: float = 15.0

    @property
    def broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def knowflow_ui_upstream(self) -> str:
        """API 容器内反代 KnowFlow Web 的上游地址。"""
        raw = (self.knowflow_ui_upstream_url or "").strip()
        if raw:
            return raw.rstrip("/")
        legacy = (self.knowflow_ui_url or "").strip().rstrip("/")
        if legacy.startswith("http://ragflow") or legacy.startswith("http://ragflow-server"):
            return legacy
        if self.knowflow_enabled:
            return "http://ragflow:80"
        return legacy or "http://127.0.0.1:9380"

    def _knowflow_public_path(self) -> str:
        public = (self.knowflow_ui_public_url or "").strip()
        if not public:
            return ""
        if public.startswith("/"):
            return public.rstrip("/")
        return urlparse(public).path.rstrip("/")

    @property
    def knowflow_ui_asset_prefix(self) -> str:
        """KnowFlow HTML 内静态资源改写前缀（须与浏览器 iframe 基址路径一致）。"""
        public_path = self._knowflow_public_path()
        explicit = (self.knowflow_ui_proxy_prefix or "").strip().rstrip("/")
        # 浏览器基址为完整 URL 时，静态资源前缀须与其 path 一致（避免 compose 默认 /ragflow-ui 与 dev 直连冲突）
        if public_path and (not explicit or (explicit == "/ragflow-ui" and public_path != "/ragflow-ui")):
            return public_path
        if explicit:
            return explicit
        if public_path:
            return public_path
        return ""

    @property
    def knowflow_ui_browser_base(self) -> str:
        """浏览器 iframe 使用的基址（完整 URL 或同源路径前缀）。"""
        public = (self.knowflow_ui_public_url or "").strip().rstrip("/")
        if public:
            return public
        proxy = (self.knowflow_ui_proxy_prefix or "").strip().rstrip("/")
        if proxy:
            return proxy
        return (self.knowflow_ui_url or "http://127.0.0.1:9380").strip().rstrip("/")

    @property
    def resolved_document_git_repos_root(self) -> Path:
        explicit = (self.document_git_repos_root or "").strip()
        if explicit:
            return Path(explicit)
        return _PLATFORM_DIR / "data" / "document-git-repos"


@lru_cache
def get_settings() -> Settings:
    return Settings()
