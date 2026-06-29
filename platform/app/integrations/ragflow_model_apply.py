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


def normalize_ragflow_rerank_api_base(base_url: str, factory: str = "") -> str:
    """RAGFlow 写入 tenant_llm.api_base 时的 rerank 端点规范化。

    - SILICONFLOW：使用完整 ``.../v1/rerank``（RAGFlow SILICONFLOWRerank 默认路径）。
    - OpenAI-API-Compatible：在 ``/v1`` 基址上追加 ``/rerank``。
    """
    url = (base_url or "").strip().rstrip("/")
    factory_name = (factory or infer_llm_factory(url)).strip()
    if factory_name.upper() == "SILICONFLOW":
        if not url:
            return "https://api.siliconflow.cn/v1/rerank"
        if url.endswith("/rerank"):
            return url
        if url.endswith("/v1"):
            return f"{url}/rerank"
        return f"{url}/v1/rerank"
    if factory_name == "OpenAI-API-Compatible":
        if not url:
            return url
        if url.endswith("/rerank"):
            return url
        if url.endswith("/v1"):
            return f"{url}/rerank"
        return f"{url}/v1/rerank"
    return url


def normalize_ragflow_embedding_api_base(base_url: str, factory: str = "") -> str:
    """RAGFlow 写入 tenant_llm.api_base 时的兼容规范化。

    - SILICONFLOW：使用完整 ``.../v1/embeddings``，避免部分版本拼出 ``/v1/v1/embeddings``。
    - OpenAI-API-Compatible：去掉末尾 ``/v1``，由 RAGFlow 自行追加 ``/v1/embeddings``。
    """
    url = (base_url or "").strip().rstrip("/")
    factory_name = (factory or infer_llm_factory(url)).strip()
    if factory_name.upper() == "SILICONFLOW":
        if not url:
            return "https://api.siliconflow.cn/v1/embeddings"
        if "/embeddings" in url:
            return url
        if url.endswith("/v1"):
            return f"{url}/embeddings"
        return f"{url}/v1/embeddings"
    if factory_name == "OpenAI-API-Compatible" and url.endswith("/v1"):
        return url[:-3].rstrip("/")
    return url


def repair_ragflow_embedding_api_bases() -> int:
    """修复 KnowFlow 租户 embedding 的 api_base（幂等）。"""
    try:
        rows = _mysql_query(
            "SELECT CONCAT(tenant_id, '\t', llm_factory, '\t', IFNULL(api_base, '')) "
            "FROM tenant_llm WHERE model_type = 'embedding'"
        )
    except Exception as e:
        logger.debug("列举 tenant_llm embedding 跳过: %s", e)
        return 0
    repaired = 0
    for line in rows:
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        tenant_id, factory, api_base = parts[0].strip(), parts[1].strip(), parts[2].strip()
        normalized = normalize_ragflow_embedding_api_base(api_base, factory)
        if not normalized or normalized == api_base:
            continue
        safe_tid = _sql_literal(tenant_id)
        safe_factory = _sql_literal(factory)
        safe_url = _sql_literal(normalized)
        if _mysql_exec(
            "UPDATE tenant_llm SET api_base = '{url}' "
            "WHERE tenant_id = '{tid}' AND llm_factory = '{factory}' "
            "AND model_type = 'embedding' AND IFNULL(api_base, '') = '{old}'".format(
                url=safe_url,
                tid=safe_tid,
                factory=safe_factory,
                old=_sql_literal(api_base),
            )
        ):
            repaired += 1
    if repaired:
        logger.info("已修复 %s 条 KnowFlow embedding api_base", repaired)
    return repaired


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
    url = normalize_ragflow_embedding_api_base(url, llm_factory)
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


def apply_rerank_to_template_tenant(
    db: Session | None,
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    factory: str = "",
) -> bool:
    """写入 KnowFlow/RAGFlow 租户默认 RERANK 模型。"""
    template_id = resolve_template_tenant_id(db)
    if not template_id:
        logger.warning("未找到 RAGFlow 模板租户，跳过 Rerank 模型同步")
        return False

    model = (model_name or "").strip()
    key = (api_key or "").strip()
    url = (base_url or "").strip()
    if not model or not key:
        logger.warning("Rerank 模型名称或 API Key 未配置，跳过 RAGFlow 同步")
        return False

    llm_factory = infer_llm_factory(url, factory)
    url = normalize_ragflow_rerank_api_base(url, llm_factory)
    safe_tid = _sql_literal(template_id)
    safe_factory = _sql_literal(llm_factory)
    safe_model = _sql_literal(model)
    safe_key = _sql_literal(key)
    safe_url = _sql_literal(url)
    rerank_id = _sql_literal(f"{model}@{llm_factory}")

    delete_sql = (
        "DELETE FROM tenant_llm WHERE tenant_id = '{tid}' "
        "AND model_type = 'rerank' AND llm_name = '{model}'"
    ).format(tid=safe_tid, model=safe_model)

    insert_sql = f"""
INSERT INTO tenant_llm (
  tenant_id, llm_factory, model_type, llm_name, api_key, api_base, max_tokens, used_tokens
) VALUES (
  '{safe_tid}', '{safe_factory}', 'rerank', '{safe_model}',
  '{safe_key}', '{safe_url}', 8192, 0
);
"""
    update_tenant_sql = (
        f"UPDATE tenant SET rerank_id = '{rerank_id}' WHERE id = '{safe_tid}';"
    )

    ok = _mysql_exec(delete_sql) and _mysql_exec(insert_sql) and _mysql_exec(update_tenant_sql)
    if ok and db is not None:
        synced = sync_all_tenant_llm_configs(db)
        logger.info("Rerank 模型已写入模板租户并同步 %s 个用户", synced)
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


def apply_image2text_to_template_tenant(
    db: Session | None,
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    factory: str = "",
) -> bool:
    """写入 KnowFlow/RAGFlow 租户默认 IMAGE2TEXT（PDF 图表增强）模型。"""
    template_id = resolve_template_tenant_id(db)
    if not template_id:
        logger.warning("未找到 RAGFlow 模板租户，跳过视觉模型同步")
        return False

    model = (model_name or "").strip()
    key = (api_key or "").strip()
    url = (base_url or "").strip()
    if not model or not key:
        logger.warning("视觉模型名称或 API Key 未配置，跳过 RAGFlow 同步")
        return False

    llm_factory = infer_llm_factory(url, factory)
    safe_tid = _sql_literal(template_id)
    safe_factory = _sql_literal(llm_factory)
    safe_model = _sql_literal(model)
    safe_key = _sql_literal(key)
    safe_url = _sql_literal(url)
    img2txt_id = _sql_literal(f"{model}@{llm_factory}")

    delete_sql = (
        "DELETE FROM tenant_llm WHERE tenant_id = '{tid}' "
        "AND model_type = 'image2text' AND llm_name = '{model}'"
    ).format(tid=safe_tid, model=safe_model)

    insert_sql = f"""
INSERT INTO tenant_llm (
  tenant_id, llm_factory, model_type, llm_name, api_key, api_base, max_tokens, used_tokens
) VALUES (
  '{safe_tid}', '{safe_factory}', 'image2text', '{safe_model}',
  '{safe_key}', '{safe_url}', 8192, 0
);
"""
    update_tenant_sql = (
        f"UPDATE tenant SET img2txt_id = '{img2txt_id}' WHERE id = '{safe_tid}';"
    )
    # 模板租户常残留硅基流动预置的 deepseek-vl2 等条目（已停用），
    # 同步到用户租户后仍会触发 IMAGE2TEXT 403 Model disabled。
    purge_other_sql = (
        "DELETE FROM tenant_llm WHERE tenant_id = '{tid}' "
        "AND model_type = 'image2text' AND llm_name != '{model}'"
    ).format(tid=safe_tid, model=safe_model)
    reconcile_sql = (
        f"UPDATE tenant SET img2txt_id = '{img2txt_id}' "
        f"WHERE img2txt_id LIKE '%deepseek-vl2%' OR img2txt_id = '';"
    )

    ok = (
        _mysql_exec(delete_sql)
        and _mysql_exec(insert_sql)
        and _mysql_exec(update_tenant_sql)
        and _mysql_exec(purge_other_sql)
        and _mysql_exec(reconcile_sql)
    )
    if ok and db is not None:
        synced = sync_all_tenant_llm_configs(db)
        logger.info("视觉模型已写入模板租户并同步 %s 个用户", synced)
    return ok


def patch_knowflow_paddleocr_config(
    *,
    base_url: str,
    api_key: str = "",
    model_name: str = "",
) -> bool:
    """更新 deploy/knowflow/settings.yaml 中 PaddleOCR-VL 配置（在线 API 或本地服务）。"""
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

    base = normalize_paddleocr_service_url(base_url)
    if not base:
        return False

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    paddle = data.setdefault("paddleocr", {})
    paddle["url"] = base
    if api_key:
        paddle["api_key"] = api_key.strip()
    if model_name:
        paddle["model"] = model_name.strip()
        paddle["algorithm"] = "PaddleOCR-VL"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    logger.info(
        "已更新 KnowFlow paddleocr.url=%s model=%s",
        base,
        model_name or paddle.get("model"),
    )
    return True


def patch_knowflow_paddleocr_url(service_url: str) -> bool:
    """更新 deploy/knowflow/settings.yaml 中 paddleocr.url（兼容旧配置）。"""
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

    return patch_knowflow_paddleocr_config(base_url=service_url)


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
