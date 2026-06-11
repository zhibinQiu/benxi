"""将平台模型配置写入 RAGFlow / KnowFlow 模板租户。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.integrations.paddleocr_client import normalize_paddleocr_service_url
from app.integrations.ragflow_llm_template import (
    _mysql_exec,
    _mysql_query,
    _sql_literal,
    resolve_template_tenant_id,
    sync_all_tenant_llm_configs,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def parse_embd_id(embd_id: str) -> tuple[str, str]:
    raw = (embd_id or "").strip()
    if "@" in raw:
        name, factory = raw.rsplit("@", 1)
        return name.strip(), factory.strip()
    return raw, ""


def infer_llm_factory(base_url: str, explicit: str = "") -> str:
    if (explicit or "").strip():
        return explicit.strip()
    host = (base_url or "").lower()
    if "siliconflow" in host:
        return "SILICONFLOW"
    if "openai" in host or "deepseek" in host:
        return "OpenAI"
    return "OpenAI-API-Compatible"


def fetch_template_embedding_defaults(db: Session | None) -> dict[str, str]:
    template_id = resolve_template_tenant_id(db)
    if not template_id:
        return {}
    safe = _sql_literal(template_id)
    rows = _mysql_query(f"SELECT embd_id FROM tenant WHERE id = '{safe}' LIMIT 1")
    model_name, factory = parse_embd_id(rows[0] if rows else "")
    out = {"embedding_model": model_name, "embedding_factory": factory}
    if model_name:
        safe_name = _sql_literal(model_name)
        detail = _mysql_query(
            "SELECT llm_factory, api_base FROM tenant_llm "
            f"WHERE tenant_id = '{safe}' AND model_type = 'embedding' "
            f"AND llm_name = '{safe_name}' LIMIT 1"
        )
        if detail:
            parts = detail[0].split("\t") if "\t" in detail[0] else [detail[0]]
            if len(parts) >= 2 and parts[1].strip():
                out["embedding_base_url"] = parts[1].strip()
            if len(parts) >= 1 and parts[0].strip():
                out["embedding_factory"] = parts[0].strip()
    return out


def apply_embedding_to_template_tenant(
    db: Session | None,
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    factory: str = "",
) -> bool:
    template_id = resolve_template_tenant_id(db)
    if not template_id:
        logger.warning("未找到 RAGFlow 模板租户，跳过嵌入模型同步")
        return False

    model = (model_name or "").strip()
    key = (api_key or "").strip()
    url = (base_url or "").strip()
    if not model or not key:
        logger.warning("嵌入模型名称或 API Key 未配置，跳过 RAGFlow 同步")
        return False

    llm_factory = infer_llm_factory(url, factory)
    safe_tid = _sql_literal(template_id)
    safe_factory = _sql_literal(llm_factory)
    safe_model = _sql_literal(model)
    safe_key = _sql_literal(key)
    safe_url = _sql_literal(url)
    embd_id = _sql_literal(f"{model}@{llm_factory}")

    delete_sql = (
        "DELETE FROM tenant_llm WHERE tenant_id = '{tid}' "
        "AND model_type = 'embedding' AND llm_name = '{model}'"
    ).format(tid=safe_tid, model=safe_model)

    insert_sql = f"""
INSERT INTO tenant_llm (
  tenant_id, llm_factory, model_type, llm_name, api_key, api_base, max_tokens, used_tokens
) VALUES (
  '{safe_tid}', '{safe_factory}', 'embedding', '{safe_model}',
  '{safe_key}', '{safe_url}', 8192, 0
);
"""

    update_tenant_sql = (
        f"UPDATE tenant SET embd_id = '{embd_id}' WHERE id = '{safe_tid}';"
    )

    ok = _mysql_exec(delete_sql) and _mysql_exec(insert_sql) and _mysql_exec(update_tenant_sql)
    if ok and db is not None:
        synced = sync_all_tenant_llm_configs(db)
        logger.info("嵌入模型已写入模板租户并同步 %s 个用户", synced)
    return ok


def apply_llm_to_template_tenant(
    db: Session | None,
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    factory: str = "",
) -> bool:
    template_id = resolve_template_tenant_id(db)
    if not template_id:
        return False
    model = (model_name or "").strip()
    key = (api_key or "").strip()
    url = (base_url or "").strip()
    if not model or not key:
        return False

    llm_factory = infer_llm_factory(url, factory)
    safe_tid = _sql_literal(template_id)
    safe_factory = _sql_literal(llm_factory)
    safe_model = _sql_literal(model)
    safe_key = _sql_literal(key)
    safe_url = _sql_literal(url)
    llm_id = _sql_literal(f"{model}@{llm_factory}")

    delete_sql = (
        "DELETE FROM tenant_llm WHERE tenant_id = '{tid}' "
        "AND model_type = 'chat' AND llm_name = '{model}'"
    ).format(tid=safe_tid, model=safe_model)

    insert_sql = f"""
INSERT INTO tenant_llm (
  tenant_id, llm_factory, model_type, llm_name, api_key, api_base, max_tokens, used_tokens
) VALUES (
  '{safe_tid}', '{safe_factory}', 'chat', '{safe_model}',
  '{safe_key}', '{safe_url}', 8192, 0
);
"""
    update_sql = f"UPDATE tenant SET llm_id = '{llm_id}' WHERE id = '{safe_tid}';"
    return _mysql_exec(delete_sql) and _mysql_exec(insert_sql) and _mysql_exec(update_sql)


def patch_knowflow_paddleocr_url(service_url: str) -> bool:
    """更新 deploy/knowflow/settings.yaml 中 paddleocr.url。"""
    from pathlib import Path

    try:
        import yaml
    except ImportError:
        logger.warning("未安装 PyYAML，跳过 KnowFlow settings 更新")
        return False

    root = Path(__file__).resolve().parents[3]
    path = root / "deploy" / "knowflow" / "settings.yaml"
    if not path.is_file():
        logger.warning("未找到 %s", path)
        return False

    base = normalize_paddleocr_service_url(service_url)
    if not base:
        return False

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("paddleocr", {})
    data["paddleocr"]["url"] = base
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("已更新 KnowFlow paddleocr.url = %s", base)
    return True


def try_restart_knowflow_services() -> None:
    import subprocess

    try:
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                "zhitan",
                "restart",
                "knowflow-backend",
                "ragflow",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as e:
        logger.info("KnowFlow 服务重启跳过（可手动 restart knowflow-backend ragflow）: %s", e)
