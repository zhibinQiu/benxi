"""将 RAGFlow 超级管理员的模型供应商/API 配置同步给平台用户（全员共用）。"""

from __future__ import annotations

import logging
import subprocess

from app.config import get_settings

logger = logging.getLogger(__name__)


def _mysql_settings() -> tuple[str, str, str]:
    settings = get_settings()
    container = (settings.ragflow_mysql_container or "ragflow-mysql").strip()
    password = (settings.ragflow_mysql_password or "infini_rag_flow").strip()
    db = (settings.ragflow_mysql_db or "rag_flow").strip()
    return container, password, db


def _sql_literal(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("'", "''")


def _mysql_query(sql: str) -> list[str]:
    container, password, db = _mysql_settings()
    proc = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "mysql",
            "-uroot",
            f"-p{password}",
            db,
            "-N",
            "-B",
            "-e",
            sql,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "mysql query failed")
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return lines


def _mysql_exec(sql: str) -> bool:
    container, password, db = _mysql_settings()
    try:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "mysql",
                "-uroot",
                f"-p{password}",
                db,
                "-e",
                sql,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        logger.warning("RAGFlow LLM 同步失败: %s", e)
        return False
    if proc.returncode != 0:
        logger.warning(
            "RAGFlow LLM 同步 SQL 失败: %s",
            (proc.stderr or proc.stdout or "")[:400],
        )
        return False
    return True


def resolve_template_tenant_id() -> str | None:
    """取模板租户：优先配置邮箱，否则首个超级管理员。"""
    settings = get_settings()
    email = (
        (settings.ragflow_llm_template_email or "").strip()
        or (settings.ragflow_shared_email or "").strip()
        or "admin@gmail.com"
    )
    safe_email = _sql_literal(email.lower())
    rows = _mysql_query(
        "SELECT id FROM user "
        f"WHERE LOWER(email)='{safe_email}' "
        "ORDER BY is_superuser DESC, create_time ASC LIMIT 1"
    )
    if rows:
        return rows[0]
    rows = _mysql_query(
        "SELECT id FROM user WHERE is_superuser=1 ORDER BY create_time ASC LIMIT 1"
    )
    return rows[0] if rows else None


def sync_tenant_llm_from_template(target_tenant_id: str) -> bool:
    """把模板租户的模型供应商与 API 复制到目标租户（幂等，可重复执行）。"""
    target = (target_tenant_id or "").strip()
    if not target:
        return False
    settings = get_settings()
    if not settings.ragflow_llm_shared_from_template:
        return False
    try:
        template_id = resolve_template_tenant_id()
    except Exception as e:
        logger.warning("无法解析 RAGFlow LLM 模板租户: %s", e)
        return False
    if not template_id or template_id == target:
        return False

    safe_target = _sql_literal(target)
    safe_template = _sql_literal(template_id)

    tenant_sql = f"""
UPDATE tenant AS t
JOIN tenant AS src ON src.id = '{safe_template}'
SET
  t.llm_id = IFNULL(NULLIF(src.llm_id, ''), t.llm_id),
  t.embd_id = IFNULL(NULLIF(src.embd_id, ''), t.embd_id),
  t.asr_id = IFNULL(NULLIF(src.asr_id, ''), t.asr_id),
  t.img2txt_id = IFNULL(NULLIF(src.img2txt_id, ''), t.img2txt_id),
  t.rerank_id = IFNULL(NULLIF(src.rerank_id, ''), t.rerank_id),
  t.tts_id = IFNULL(NULLIF(src.tts_id, ''), t.tts_id)
WHERE t.id = '{safe_target}';
"""

    llm_sql = f"""
INSERT INTO tenant_llm (
  tenant_id, llm_factory, model_type, llm_name, api_key, api_base, max_tokens, used_tokens
)
SELECT
  '{safe_target}', llm_factory, model_type, llm_name, api_key, api_base, max_tokens, 0
FROM tenant_llm
WHERE tenant_id = '{safe_template}'
  AND api_key IS NOT NULL
  AND api_key <> ''
ON DUPLICATE KEY UPDATE
  api_key = VALUES(api_key),
  api_base = VALUES(api_base),
  max_tokens = VALUES(max_tokens);
"""

    ok = _mysql_exec(tenant_sql) and _mysql_exec(llm_sql)
    if ok:
        logger.info(
            "已从 RAGFlow 模板 %s 同步模型配置到租户 %s",
            template_id,
            target,
        )
    return ok


def ensure_shared_llm_config(ragflow_user_id: str | None) -> bool:
    if not ragflow_user_id:
        return False
    return sync_tenant_llm_from_template(ragflow_user_id)
