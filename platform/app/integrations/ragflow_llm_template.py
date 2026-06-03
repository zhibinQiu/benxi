"""将 RAGFlow 模板租户的模型供应商/API 配置同步给平台用户（全员共用）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _mysql_settings() -> tuple[str, str, str, str, int]:
    settings = get_settings()
    container = (settings.ragflow_mysql_container or "ragflow-mysql").strip()
    password = (settings.ragflow_mysql_password or "infini_rag_flow").strip()
    db = (settings.ragflow_mysql_db or "rag_flow").strip()
    host = (settings.ragflow_mysql_host or "").strip()
    if not host and settings.knowflow_enabled:
        host = "knowflow-mysql"
    port = int(settings.ragflow_mysql_port or 3306)
    return container, password, db, host, port


def _sql_literal(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("'", "''")


def _mysql_query_tcp(host: str, port: int, password: str, db: str, sql: str) -> list[str]:
    import pymysql

    conn = pymysql.connect(
        host=host,
        port=port,
        user="root",
        password=password,
        database=db,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=20,
        write_timeout=30,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return [str(row[0]).strip() for row in rows if row and row[0] is not None]
    finally:
        conn.close()


def _mysql_exec_tcp(host: str, port: int, password: str, db: str, sql: str) -> bool:
    import pymysql

    conn = pymysql.connect(
        host=host,
        port=port,
        user="root",
        password=password,
        database=db,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=20,
        write_timeout=30,
    )
    try:
        with conn.cursor() as cur:
            for statement in _split_sql_statements(sql):
                cur.execute(statement)
        conn.commit()
        return True
    except Exception as e:
        logger.warning("RAGFlow LLM 同步 MySQL 失败: %s", e)
        return False
    finally:
        conn.close()


def _split_sql_statements(sql: str) -> list[str]:
    parts: list[str] = []
    for chunk in sql.split(";"):
        stmt = chunk.strip()
        if stmt:
            parts.append(stmt)
    return parts


def _mysql_query(sql: str) -> list[str]:
    import subprocess

    container, password, db, host, port = _mysql_settings()
    if host:
        try:
            return _mysql_query_tcp(host, port, password, db, sql)
        except Exception as e:
            logger.warning("RAGFlow MySQL TCP 查询失败，尝试 docker exec: %s", e)
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
    import subprocess

    container, password, db, host, port = _mysql_settings()
    if host:
        if _mysql_exec_tcp(host, port, password, db, sql):
            return True
        logger.warning("RAGFlow MySQL TCP 执行失败，尝试 docker exec")
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


def _template_tenant_from_platform_bootstrap(db: Session) -> str | None:
    """平台 bootstrap 系统管理员在 RAGFlow 中的租户 id（模型配置主账号）。"""
    from app.core.phone import bootstrap_login_id
    from app.models.org import User
    from app.models.ragflow_link import RagflowAccountLink

    bootstrap = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    if not bootstrap:
        return None
    link = db.scalar(
        select(RagflowAccountLink).where(
            RagflowAccountLink.platform_user_id == bootstrap.id
        )
    )
    if not link:
        return None
    uid = (link.ragflow_user_id or "").strip()
    if uid:
        return uid
    email = (link.ragflow_email or "").strip().lower()
    if not email:
        return None
    safe_email = _sql_literal(email)
    rows = _mysql_query(
        "SELECT id FROM user "
        f"WHERE LOWER(email)='{safe_email}' "
        "ORDER BY create_time ASC LIMIT 1"
    )
    return rows[0] if rows else None


def _richest_llm_template_tenant_id() -> str | None:
    """取 tenant_llm 配置最全的租户（管理员已在 KnowFlow 配好模型时）。"""
    rows = _mysql_query(
        "SELECT tenant_id FROM tenant_llm "
        "GROUP BY tenant_id "
        "ORDER BY COUNT(*) DESC, tenant_id ASC LIMIT 1"
    )
    return rows[0] if rows else None


def _template_tenant_by_email(email: str) -> str | None:
    safe_email = _sql_literal(email.lower())
    rows = _mysql_query(
        "SELECT id FROM user "
        f"WHERE LOWER(email)='{safe_email}' "
        "ORDER BY is_superuser DESC, create_time ASC LIMIT 1"
    )
    return rows[0] if rows else None


def _tenant_llm_row_count(tenant_id: str) -> int:
    safe = _sql_literal(tenant_id)
    rows = _mysql_query(
        f"SELECT COUNT(*) FROM tenant_llm WHERE tenant_id='{safe}'"
    )
    try:
        return int(rows[0]) if rows else 0
    except ValueError:
        return 0


def resolve_template_tenant_id(db: Session | None = None) -> str | None:
    """解析模型配置模板租户（全员复制来源）。"""
    settings = get_settings()
    explicit = (settings.ragflow_llm_template_tenant_id or "").strip()
    if explicit:
        return explicit

    bootstrap_tid: str | None = None
    if db is not None:
        try:
            bootstrap_tid = _template_tenant_from_platform_bootstrap(db)
        except Exception as e:
            logger.warning("解析 bootstrap 模型模板租户失败: %s", e)
        if bootstrap_tid and _tenant_llm_row_count(bootstrap_tid) > 0:
            return bootstrap_tid

    email = (settings.ragflow_llm_template_email or "").strip()
    if email:
        tid = _template_tenant_by_email(email)
        if tid and _tenant_llm_row_count(tid) > 0:
            return tid

    shared = (settings.ragflow_shared_email or "").strip()
    if shared and shared.lower() != email.lower():
        tid = _template_tenant_by_email(shared)
        if tid and _tenant_llm_row_count(tid) > 0:
            return tid

    try:
        richest = _richest_llm_template_tenant_id()
        if richest:
            return richest
    except Exception as e:
        logger.warning("按 tenant_llm 解析模型模板失败: %s", e)

    if bootstrap_tid:
        return bootstrap_tid

    email = (settings.ragflow_llm_template_email or "").strip()
    if email:
        tid = _template_tenant_by_email(email)
        if tid:
            return tid

    try:
        rows = _mysql_query(
            "SELECT id FROM user WHERE is_superuser=1 ORDER BY create_time ASC LIMIT 1"
        )
        return rows[0] if rows else None
    except Exception:
        return _template_tenant_by_email("admin@gmail.com")


def sync_tenant_llm_from_template(
    target_tenant_id: str, *, db: Session | None = None
) -> bool:
    """把模板租户的模型供应商与 API 完整复制到目标租户（幂等，可重复执行）。"""
    target = (target_tenant_id or "").strip()
    if not target:
        return False
    settings = get_settings()
    if not settings.ragflow_llm_shared_from_template:
        return False
    try:
        template_id = resolve_template_tenant_id(db)
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
  t.llm_id = src.llm_id,
  t.embd_id = src.embd_id,
  t.asr_id = src.asr_id,
  t.img2txt_id = src.img2txt_id,
  t.rerank_id = src.rerank_id,
  t.tts_id = src.tts_id
WHERE t.id = '{safe_target}';
"""

    delete_sql = f"DELETE FROM tenant_llm WHERE tenant_id = '{safe_target}';"

    llm_sql = f"""
INSERT INTO tenant_llm (
  tenant_id, llm_factory, model_type, llm_name, api_key, api_base, max_tokens, used_tokens
)
SELECT
  '{safe_target}', llm_factory, model_type, llm_name, api_key, api_base, max_tokens, 0
FROM tenant_llm
WHERE tenant_id = '{safe_template}';
"""

    ok = (
        _mysql_exec(tenant_sql)
        and _mysql_exec(delete_sql)
        and _mysql_exec(llm_sql)
    )
    if ok:
        logger.info(
            "已从 RAGFlow 模板 %s 同步模型配置到租户 %s",
            template_id,
            target,
        )
    return ok


def ensure_shared_llm_config(
    ragflow_user_id: str | None, *, db: Session | None = None
) -> bool:
    if not ragflow_user_id:
        return False
    return sync_tenant_llm_from_template(ragflow_user_id, db=db)


def sync_all_tenant_llm_configs(db: Session) -> int:
    """将模板模型配置推送到全部已开户平台用户（bootstrap 保存模型后调用）。"""
    from app.models.ragflow_link import RagflowAccountLink

    synced = 0
    seen: set[str] = set()
    for link in db.scalars(select(RagflowAccountLink)).all():
        uid = (link.ragflow_user_id or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        if sync_tenant_llm_from_template(uid, db=db):
            synced += 1
    return synced
