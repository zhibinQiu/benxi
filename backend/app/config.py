"""平台配置 — 环境变量驱动，Pydantic BaseSettings。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLATFORM_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _PLATFORM_DIR / ".env"


class Settings(BaseSettings):
    """平台全局配置。所有字段可通过环境变量覆盖。"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 平台基础 ──────────────────────────────────────────────────────────────
    app_name: str = "本析"
    platform_version: str = "4.8.1"
    debug: bool = False
    debug_sql: bool = False
    remote_deps: bool = False
    api_prefix: str = "/api/v1"
    api_public_path_prefix: str = "/ai"
    platform_api_base_url: str = ""
    frontend_app_title: str = ""
    frontend_default_theme: str = "system"
    frontend_color_scheme: str = "blue"
    frontend_primary_color: str = ""
    cors_origins: str = "*"

    # ── 数据库 ────────────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg2://platform:platform@127.0.0.1:5432/platform"
    database_read_url: str = ""
    db_pool_size: int = 15
    db_max_overflow: int = 15
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_connect_timeout: int = 10
    db_statement_timeout_ms: int = 30000
    db_slow_query_log_ms: int = 500
    db_circuit_enabled: bool = True
    db_circuit_failure_threshold: int = 5
    db_circuit_cooldown_sec: int = 20
    db_startup_bootstrap: str = "auto"

    # ── 缓存 / 消息队列 ───────────────────────────────────────────────────────
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_socket_timeout_sec: float = 0.5
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    platform_cache_enabled: bool = True
    platform_cache_ttl_sec: int = 60
    platform_cache_client_config_ttl_sec: int = 300
    platform_cache_dashboard_ttl_sec: int = 30
    platform_cache_features_ttl_sec: int = 60
    platform_cache_document_detail_ttl_sec: int = 90
    document_library_cache_ttl_sec: int = 180
    kb_folders_cache_ttl_sec: int = 120
    scope_tree_cache_ttl_sec: int = 300
    kg_graph_cache_ttl_sec: int = 120

    # ── 对象存储（MinIO）───────────────────────────────────────────────────────
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"
    minio_secure: bool = False
    minio_region: str = "us-east-1"

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    refresh_token_expire_days: int = 7

    # ── 用户 ──────────────────────────────────────────────────────────────────
    bootstrap_admin_phone: str = "admin"
    bootstrap_admin_display_name: str = "系统管理员"
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_email: str = "admin@local"
    allow_public_register: bool = True
    allow_trial: bool = True
    captcha_enabled: bool = True

    # ── 翻译（pdf2zh）──────────────────────────────────────────────────────────
    pdf2zh_api_url: str = "http://127.0.0.1:7861"

    # ── KnowFlow / RAGFlow 知识库 ────────────────────────────────────────────
    knowflow_enabled: bool = False
    knowflow_backend_url: str = "http://127.0.0.1:5001"
    knowflow_ui_url: str = "http://127.0.0.1:9380"
    knowflow_ui_upstream_url: str = ""
    knowflow_ui_public_url: str = ""
    knowflow_ui_embed_mode: str = "iframe"
    knowflow_ui_proxy_prefix: str = ""
    knowflow_content_reuse_allow_personal_from_org: bool = True

    ragflow_api_url: str = "http://127.0.0.1:9380"
    ragflow_api_key: str = ""
    ragflow_http_timeout: float = 0
    ragflow_http_cooldown_sec: int = 20
    ragflow_mysql_connect_timeout: int = 5
    ragflow_mysql_read_timeout: int = 30
    ragflow_mysql_write_timeout: int = 30
    ragflow_account_mode: str = "mapped"
    ragflow_shared_email: str = "admin@gmail.com"
    ragflow_shared_password: str = "admin"
    ragflow_grant_global_admin: bool = True
    ragflow_mysql_container: str = "ragflow-mysql"
    ragflow_mysql_password: str = "infini_rag_flow"
    ragflow_mysql_db: str = "rag_flow"
    ragflow_mysql_host: str = ""
    ragflow_mysql_port: int = 3306
    ragflow_dataset_name: str = "平台知识库"
    ragflow_dataset_prefix: str = "zt-platform"
    ragflow_personal_dataset_prefix: str = "zt-personal"
    ragflow_company_dataset_name: str = "zt-company"
    ragflow_dept_dataset_prefix: str = "zt-dept"
    ragflow_sync_doc_limit: int = 100
    ragflow_sync_on_login: bool = False
    ragflow_sync_on_login_limit: int = 50
    ragflow_sync_on_embed: bool = False
    ragflow_llm_shared_from_template: bool = True
    ragflow_llm_template_email: str = ""
    ragflow_llm_template_tenant_id: str = ""

    # ── 语音（FunASR 会议转写）────────────────────────────────────────────────
    speech_service_url: str = "http://127.0.0.1:8765"
    funasr_asr_model: str = "paraformer-zh"
    diarization_enabled: bool = True
    stt_language: str = "zh"
    stt_max_file_mb: int = 100

    # ── 文档 ──────────────────────────────────────────────────────────────────
    document_upload_max_file_mb: int = 200
    gotenberg_url: str = ""
    document_git_repos_root: str = ""

    # ── PageIndex 树形索引 ────────────────────────────────────────────────────
    pageindex_enabled: bool = True
    pageindex_workspace_dir: str = ""
    pageindex_model: str = ""

    # ── 流式 / SSE ────────────────────────────────────────────────────────────
    stream_max_concurrent_per_worker: int = 12
    stream_acquire_timeout: float = 8.0

    # ── 知识库检索 ────────────────────────────────────────────────────────────
    knowledge_default_parser_id: str = "naive"
    knowledge_reindex_default_parser_id: str = "naive"
    knowledge_default_layout_recognize: str = "DeepDOC"
    knowledge_default_chunk_token_num: int = 512
    knowledge_list_live_index_meta: bool = False
    knowledge_detail_live_index_meta: bool = False
    knowledge_ragflow_meta_cache_ttl_sec: int = 60
    knowledge_parse_initial_wait_sec: int = 1800
    knowledge_parse_max_wait_sec: int = 86400
    knowledge_parse_soft_extend_sec: int = 600
    knowledge_parse_poll_interval_sec: int = 5
    knowledge_parse_max_retries: int = 0
    knowledge_parse_retry_delay_sec: int = 90
    knowledge_retrieval_vector_weight: float = 0.3
    knowledge_retrieval_top_k: int = 5
    knowledge_retrieval_similarity_threshold: float = 0.32
    knowledge_agentic_enabled: bool = True
    knowledge_agentic_max_rounds: int = 2
    knowledge_agentic_qa_max_sub_questions: int = 4
    knowledge_agentic_report_max_sub_questions: int = 6

    # ── 后台任务 ──────────────────────────────────────────────────────────────
    background_job_max_workers: int = 4
    background_jobs_use_celery: bool = True
    background_job_stale_watchdog_enabled: bool = True
    background_job_stale_minutes: int = 30
    background_job_stale_watchdog_interval_sec: int = 120

    # ── KnowFlow 队列看门狗 ──────────────────────────────────────────────────
    knowflow_queue_watchdog_enabled: bool = True
    knowflow_queue_watchdog_interval_sec: int = 120
    knowflow_queue_watchdog_stuck_minutes: int = 10
    knowflow_queue_watchdog_min_pending: int = 1
    knowflow_queue_watchdog_recovery_cooldown_sec: int = 1800
    knowflow_queue_watchdog_cmd_timeout_sec: int = 600
    knowflow_queue_watchdog_internal_recovery: bool = True
    knowflow_queue_watchdog_cmd: str = ""

    # ── 通知 / 定时任务 ────────────────────────────────────────────────────────
    notification_scheduled_max_skew_sec: int = 5  # 定时提醒可容忍的时钟偏差（秒），应对系统时钟偏移

    # ── AI 智能体 ─────────────────────────────────────────────────────────────
    agent_max_tool_rounds: int = 40
    agent_max_adaptive_passes: int = 2
    agent_specialist_max_tool_rounds: int = 20
    agent_max_sequential_handoffs: int = 2
    agent_max_parallel_handoffs: int = 2
    agent_routing_llm_enabled: bool = False
    agent_skill_match_threshold: float = 0.3
    agent_capability_fallback_mode: str = "loose"
    agent_orchestrator_max_assist_rounds: int = 2
    agent_supervisor_max_global_rounds: int = 3
    agent_planning_enabled: bool = True
    agent_plan_cache_enabled: bool = True
    agent_plan_cache_ttl_sec: int = 86400
    agent_plan_cache_similarity_threshold: float = 0.85
    agent_plan_cache_max_entries: int = 120
    agent_tool_timeout_sec: int = 60  # 单次 Agent 工具调用超时（秒）
    agent_memory_read_max_chars: int = 2000
    agent_memory_max_chars: int = 8000
    agent_memory_entry_max_chars: int = 500

    # ── HITL（Human-in-the-Loop）─────────────────────────────────────────────
    hitl_confirm_tools: str = ""

    # ── Agent Skills（上传脚本执行）───────────────────────────────────────────
    agent_skill_max_zip_mb: int = 20
    agent_skill_max_files_per_skill: int = 100
    agent_skill_max_total_mb_per_skill: int = 10
    agent_skill_script_enabled: bool = True
    agent_skill_script_timeout_seconds: int = 30
    agent_skill_script_max_conclusion_chars: int = 4000
    sandbox_base_url: str = ""

    # ── 浏览器 RPA ────────────────────────────────────────────────────────────
    agent_browser_enabled: bool = False
    agent_browser_headless: bool = True
    agent_browser_session_ttl_seconds: int = 1800
    agent_browser_max_steps_per_session: int = 50
    agent_browser_allowed_domains: str = ""
    agent_browser_screenshot_max_kb: int = 800
    agent_browser_auto_task_max_steps: int = 15

    # ── 对话 LLM ──────────────────────────────────────────────────────────────
    chat_prompt_max_chars: int = 32000
    chat_report_prompt_max_chars: int = 48000
    chat_history_max_chars: int = 6000
    chat_history_max_messages: int = 8
    chat_context_max_chars: int = 10000
    chat_report_context_max_chars: int = 24000
    chat_user_message_max_chars: int = 4000
    chat_max_output_tokens: int = 0

    # ── DeepSeek API ──────────────────────────────────────────────────────────
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_max_chars: int = 12000

    # ── 知识图谱 ──────────────────────────────────────────────────────────────
    kg_extraction_enabled: bool = True
    kg_extraction_max_chars: int = 10000

    # ── Neo4j 图数据库（本体定义 + 知识图谱）────────────────────────────────
    neo4j_uri: str = "bolt://neo4j:7687"  # env NEO4J_URI
    neo4j_user: str = "neo4j"             # env NEO4J_USER
    neo4j_password: str = Field("", alias="NEO4J_PASSWORD")
    neo4j_database: str = "neo4j"         # env NEO4J_DATABASE

    # ── 系统设置 · 模型配置（页面只读展示，回退 deepseek_*）──────────────────
    platform_llm_base_url: str = ""
    platform_llm_api_key: str = ""
    platform_llm_model: str = ""
    platform_multimodal_base_url: str = "https://api.siliconflow.cn/v1"
    platform_multimodal_api_key: str = ""
    platform_multimodal_model: str = "Qwen/Qwen3.5-9B"
    platform_embedding_base_url: str = ""
    platform_embedding_api_key: str = ""
    platform_embedding_model: str = ""
    platform_embedding_factory: str = ""
    platform_rerank_base_url: str = ""
    platform_rerank_api_key: str = ""
    platform_rerank_model: str = ""
    platform_vl_base_url: str = ""
    platform_vl_api_key: str = ""
    platform_vl_model: str = ""
    platform_tts_base_url: str = ""
    platform_tts_api_key: str = ""
    platform_tts_model: str = ""
    platform_paddleocr_url: str = ""
    platform_paddleocr_base_url: str = ""
    platform_paddleocr_api_key: str = ""
    platform_paddleocr_model: str = ""

    @model_validator(mode="after")
    def _apply_legacy_vl_env_aliases(self) -> "Settings":
        if not (self.platform_vl_base_url or "").strip():
            self.platform_vl_base_url = os.environ.get("PLATFORM_VISION_BASE_URL", "").strip()
        if not (self.platform_vl_api_key or "").strip():
            self.platform_vl_api_key = os.environ.get("PLATFORM_VISION_API_KEY", "").strip()
        if not os.environ.get("PLATFORM_VL_MODEL", "").strip():
            legacy_model = os.environ.get("PLATFORM_VISION_MODEL", "").strip()
            if legacy_model:
                self.platform_vl_model = legacy_model
        return self

    # ── 智能问数 / 碳 AI（Dify 对话 API）───────────────────────────────────────
    embed_proxy_mode: str = "path"
    design_system_upstream_url: str = "http://127.0.0.1:40001"
    design_system_proxy_prefix: str = "/design-system-ui"
    smart_data_query_path: str = "/ai/smart-data-query"
    smart_data_query_v2_dify_base_url: str = "http://127.0.0.1:40001/v1"
    smart_data_query_v2_dify_api_key: str = ""
    carbon_qa_v2_chat_base_url: str = "http://127.0.0.1:40001/v1"
    carbon_qa_v2_chat_api_key: str = ""
    carbon_qa_path: str = "/ai/retrieval"
    carbon_ai_v1_path: str = "/ai"
    carbon_platform_url: str = ""

    # ── 智能预测 ──────────────────────────────────────────────────────────────
    smart_forecast_embed_mode: str = "direct"
    smart_forecast_upstream_url: str = "http://127.0.0.1:8501"
    smart_forecast_proxy_prefix: str = "/smart-forecast-ui"

    # ── AIP（GB/Z 185 智能体互联）─────────────────────────────────────────────
    aip_enabled: bool = True
    aip_country: str = "cn"
    aip_org_type: str = "inst"
    aip_org_id: str = "platform"
    aip_agent_serial: str = "001"
    aip_service_base_url: str = ""
    aip_external_agents_json: str = "[]"

    # ── MCP Skill 互联 ────────────────────────────────────────────────────────
    mcp_enabled: bool = True
    mcp_service_base_url: str = ""
    mcp_external_skills_json: str = "[]"

    # ── 免费网页 AI Bridge ────────────────────────────────────────────────────
    free_web_ai_headless: bool = False
    free_web_ai_cdp_port: int = 0
    free_web_ai_chrome_path: str = ""
    free_web_ai_profile_dir: str = ""
    free_web_ai_proxy_server: str = ""
    free_web_ai_timeout_ms: int = 120000
    free_web_ai_provider_timeout_ms: int = 180000
    free_web_ai_default_provider: str = "qwen"

    # ── 在线搜索 ──────────────────────────────────────────────────────────────
    searxng_url: str = ""
    searxng_timeout_seconds: float = 15.0
    firecrawl_api_key: str = ""
    firecrawl_api_url: str = "https://api.firecrawl.dev"
    firecrawl_read_full_max_urls: int = 3

    # ── 数据分析 ──────────────────────────────────────────────────────────────
    data_analysis_storage_dir: str = ""
    data_analysis_max_file_mb: int = 50
    data_analysis_exec_timeout_seconds: int = 60

    # ── AI 聊天附件 ──────────────────────────────────────────────────────────
    ai_chat_attachment_storage_dir: str = ""
    ai_chat_attachment_max_file_mb: int = 30
    ai_chat_attachment_max_files: int = 8
    ai_chat_attachment_ttl_hours: int = 24

    # ── 属性 ──────────────────────────────────────────────────────────────────

    @property
    def broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def resolved_document_git_repos_root(self) -> Path:
        explicit = (self.document_git_repos_root or "").strip()
        if explicit:
            return Path(explicit)
        return _PLATFORM_DIR / "data" / "document-git-repos"

    @property
    def knowflow_ui_upstream(self) -> str:
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
        public_path = self._knowflow_public_path()
        explicit = (self.knowflow_ui_proxy_prefix or "").strip().rstrip("/")
        if public_path and (not explicit or (explicit == "/ragflow-ui" and public_path != "/ragflow-ui")):
            return public_path
        if explicit:
            return explicit
        if public_path:
            return public_path
        return ""

    @property
    def knowflow_ui_browser_base(self) -> str:
        public = (self.knowflow_ui_public_url or "").strip().rstrip("/")
        if public:
            return public
        proxy = (self.knowflow_ui_proxy_prefix or "").strip().rstrip("/")
        if proxy:
            return proxy
        return (self.knowflow_ui_url or "http://127.0.0.1:9380").strip().rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
