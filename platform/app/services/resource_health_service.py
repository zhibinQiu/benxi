"""资源配置项连通性探测（管理页卡片状态指示）。"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.integrations.paddleocr_client import paddleocr_request_url
from app.integrations.ragflow_client import RagflowClient
from app.services.model_settings_service import (
    get_effective_model_config,
    mask_secret,
    resolve_ragflow_api_base,
)

PROBE_TIMEOUT = 5.0

TESTABLE_RESOURCE_IDS = frozenset(
    {
        "platform_api",
        "llm",
        "embedding",
        "rerank",
        "paddleocr",
        "speech",
        "pdf2zh",
        "ragflow_api",
        "knowflow_backend",
        "ragflow_mysql",
    }
)


def _item(
    *,
    configured: bool,
    healthy: bool | None,
    message: str = "",
) -> dict[str, Any]:
    return {
        "configured": configured,
        "healthy": healthy,
        "message": message,
    }


def merge_health_test_config(db, draft: dict[str, Any]) -> dict[str, str]:
    """将编辑抽屉草稿合并进当前生效配置（掩码密钥保留原值）。"""
    merged = dict(get_effective_model_config(db))
    for key, val in draft.items():
        if val is None:
            continue
        if key == "ragflow_mysql_port":
            try:
                merged[key] = str(int(val))
            except (TypeError, ValueError):
                continue
            continue
        s = str(val).strip()
        if not s:
            continue
        if "••••" in s:
            continue
        prev = merged.get(key, "")
        if prev and s == mask_secret(prev):
            continue
        merged[key] = s
    return merged


def _endpoint_configured(*, base_url: str, api_key: str, model_name: str) -> bool:
    return bool((base_url or "").strip() and (api_key or "").strip() and (model_name or "").strip())


def _normalize_openai_base(base_url: str) -> str:
    """去掉用户可能误填的 endpoint 后缀，统一为 API 根路径。"""
    root = (base_url or "").strip().rstrip("/")
    for suffix in (
        "/embeddings",
        "/rerank",
        "/chat/completions",
        "/models",
        "/completions",
    ):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
    return root.rstrip("/")


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }


def _probe_openai_compatible(base_url: str, api_key: str) -> tuple[bool, str]:
    root = _normalize_openai_base(base_url)
    if not root:
        return False, "未填写 API 地址"
    url = f"{root}/models"
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT) as client:
            r = client.get(url, headers=_auth_headers(api_key))
            if r.status_code < 400:
                return True, "连接正常"
            return False, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"无法连接：{exc}"


def _probe_embedding(base_url: str, api_key: str, model_name: str) -> tuple[bool, str]:
    """嵌入模型走 POST /embeddings；多数供应商不支持 GET /models。"""
    root = _normalize_openai_base(base_url)
    if not root:
        return False, "未填写 API 地址"
    url = f"{root}/embeddings"
    payload = {"model": model_name.strip(), "input": "health-check"}
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT) as client:
            r = client.post(url, headers=_auth_headers(api_key), json=payload)
            if r.status_code == 200:
                return True, "连接正常"
            if r.status_code in (401, 403):
                return False, f"Key 无效或无权 (HTTP {r.status_code})"
            if r.status_code == 404:
                return _probe_openai_compatible(root, api_key)
            return False, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"无法连接：{exc}"


def _probe_rerank(base_url: str, api_key: str, model_name: str) -> tuple[bool, str]:
    root = _normalize_openai_base(base_url)
    if not root:
        return False, "未填写 API 地址"
    url = f"{root}/rerank"
    payload = {
        "model": model_name.strip(),
        "query": "health-check",
        "documents": ["ping"],
    }
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT) as client:
            r = client.post(url, headers=_auth_headers(api_key), json=payload)
            if r.status_code == 200:
                return True, "连接正常"
            if r.status_code in (401, 403):
                return False, f"Key 无效或无权 (HTTP {r.status_code})"
            if r.status_code == 404:
                return _probe_openai_compatible(root, api_key)
            return False, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"无法连接：{exc}"


def _probe_http_get(url: str, *, accept_405: bool = True) -> tuple[bool, str]:
    target = (url or "").strip()
    if not target:
        return False, "未填写服务地址"
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
            r = client.get(target)
            if r.status_code < 400 or (accept_405 and r.status_code == 405):
                return True, "连接正常"
            return False, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"无法连接：{exc}"


def _probe_paddleocr(service_url: str) -> tuple[bool, str]:
    endpoint = paddleocr_request_url(service_url)
    if not endpoint:
        return False, "未填写服务地址"
    return _probe_http_get(endpoint)


def _probe_pdf2zh_url(base_url: str) -> tuple[bool, str]:
    base = (base_url or "").rstrip("/")
    if not base:
        return False, "未填写服务地址"
    ok, msg = _probe_http_get(f"{base}/docs")
    if ok:
        return ok, msg
    return _probe_http_get(f"{base}/openapi.json")


def _probe_ragflow_api_url(api_url: str, api_key: str) -> tuple[bool, str]:
    base = resolve_ragflow_api_base(api_url).rstrip("/")
    if not base:
        return False, "未填写 API 地址"
    key = (api_key or "").strip()
    try:
        client = RagflowClient(base_url=base, api_key=key or None)
        if client.health_ok():
            return True, "连接正常"
        return False, "API 无响应或返回异常"
    except Exception as exc:
        return False, f"无法连接：{exc}"


def _probe_knowflow_backend_urls(api_base: str, ui_base: str) -> tuple[bool, str]:
    api_base = (api_base or "").rstrip("/")
    ui_base = (ui_base or "").rstrip("/")
    if not api_base and not ui_base:
        return False, "未填写后台地址"

    messages: list[str] = []
    ok_all = True

    if api_base:
        api_ok = False
        api_msg = ""
        for path in ("/health", "/api/health", "/api/v1/health"):
            api_ok, api_msg = _probe_http_get(f"{api_base}{path}", accept_405=True)
            if api_ok:
                break
        if not api_ok:
            api_ok, api_msg = _probe_http_get(api_base, accept_405=True)
        messages.append(f"API：{api_msg if api_ok else api_msg}")
        ok_all = ok_all and api_ok

    if ui_base:
        ui_ok, ui_msg = _probe_http_get(ui_base, accept_405=True)
        messages.append(f"Web UI：{ui_msg if ui_ok else ui_msg}")
        ok_all = ok_all and ui_ok

    return ok_all, "；".join(messages)


def _resolve_mysql_from_cfg(cfg: dict[str, str]) -> tuple[str, str, str, int]:
    settings = get_settings()
    password = (cfg.get("ragflow_mysql_password") or "").strip()
    db_name = (cfg.get("ragflow_mysql_db") or "rag_flow").strip()
    host = (cfg.get("ragflow_mysql_host") or "").strip()
    if not host and settings.knowflow_enabled:
        host = "knowflow-mysql"
    try:
        port = int(cfg.get("ragflow_mysql_port") or 3306)
    except (TypeError, ValueError):
        port = 3306
    return host, password, db_name, port


def _probe_ragflow_mysql_cfg(cfg: dict[str, str]) -> tuple[bool, str]:
    host, password, db_name, port = _resolve_mysql_from_cfg(cfg)
    if not password:
        return False, "未填写 MySQL 密码"
    if not host:
        return False, "未填写 MySQL 主机（Docker 栈可留空以使用 knowflow-mysql）"
    try:
        import pymysql

        conn = pymysql.connect(
            host=host,
            port=port,
            user="root",
            password=password,
            database=db_name or "rag_flow",
            charset="utf8mb4",
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
        )
        conn.close()
        return True, "连接正常"
    except Exception as exc:
        return False, f"无法连接：{exc}"


def _probe_platform_api_url(base: str) -> tuple[bool, str]:
    base = (base or "").strip().rstrip("/")
    if not base:
        return False, "未配置平台 API 根地址"
    if base.startswith("/"):
        probe_url = "http://127.0.0.1:8000/health"
    else:
        probe_url = f"{base}/api/v1/system/version"
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT) as client:
            r = client.get(probe_url)
            if r.status_code == 200:
                return True, "连接正常"
            return False, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"无法访问：{exc}"


def _probe_speech_url(speech_url: str) -> tuple[bool, str]:
    base = (speech_url or "").strip().rstrip("/")
    if not base:
        return False, "未填写服务地址"
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{base}/health")
            healthy = r.status_code == 200
    except httpx.HTTPError:
        healthy = False
    return healthy, "连接正常" if healthy else "无法访问 /health"


def check_single_resource_health(resource_id: str, cfg: dict[str, str], db) -> dict[str, Any]:
    """按给定配置探测单项资源（用于保存前测试）。"""
    _ = db
    rid = (resource_id or "").strip()
    if rid not in TESTABLE_RESOURCE_IDS:
        raise ValueError(f"unsupported resource_id: {resource_id}")

    if rid == "platform_api":
        platform_base = (cfg.get("platform_api_base_url") or "").strip()
        if not platform_base:
            from app.services.model_settings_service import get_platform_api_base_url

            platform_base = get_platform_api_base_url(db)
        if not platform_base:
            return _item(configured=False, healthy=False, message="未配置平台 API 根地址")
        healthy, msg = _probe_platform_api_url(platform_base)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "llm":
        llm_ok_cfg = _endpoint_configured(
            base_url=cfg.get("llm_base_url", ""),
            api_key=cfg.get("llm_api_key", ""),
            model_name=cfg.get("llm_model", ""),
        )
        if not llm_ok_cfg:
            return _item(configured=False, healthy=False, message="请填写 API 地址、模型与 Key")
        healthy, msg = _probe_openai_compatible(cfg["llm_base_url"], cfg["llm_api_key"])
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "embedding":
        emb_ok_cfg = _endpoint_configured(
            base_url=cfg.get("embedding_base_url", ""),
            api_key=cfg.get("embedding_api_key", ""),
            model_name=cfg.get("embedding_model", ""),
        )
        if not emb_ok_cfg:
            return _item(configured=False, healthy=False, message="请填写 API 地址、模型与 Key")
        healthy, msg = _probe_embedding(
            cfg["embedding_base_url"],
            cfg["embedding_api_key"],
            cfg["embedding_model"],
        )
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "rerank":
        rerank_url = (cfg.get("rerank_base_url") or "").strip()
        rerank_model = (cfg.get("rerank_model") or "").strip()
        rerank_key = (cfg.get("rerank_api_key") or "").strip()
        if not rerank_url and not rerank_model:
            return _item(configured=False, healthy=None, message="可选，未配置")
        if not _endpoint_configured(
            base_url=rerank_url, api_key=rerank_key, model_name=rerank_model
        ):
            return _item(configured=False, healthy=False, message="配置不完整")
        healthy, msg = _probe_rerank(rerank_url, rerank_key, rerank_model)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "paddleocr":
        paddle_url = (cfg.get("paddleocr_url") or "").strip()
        if not paddle_url:
            return _item(configured=False, healthy=False, message="未填写服务地址")
        healthy, msg = _probe_paddleocr(paddle_url)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "speech":
        if not (cfg.get("speech_service_url") or "").strip():
            return _item(configured=False, healthy=False, message="未填写服务地址")
        healthy, msg = _probe_speech_url(cfg["speech_service_url"])
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "pdf2zh":
        pdf2zh_url = (cfg.get("pdf2zh_api_url") or "").strip()
        if not pdf2zh_url:
            return _item(configured=False, healthy=False, message="未填写服务地址")
        healthy, msg = _probe_pdf2zh_url(pdf2zh_url)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "ragflow_api":
        ragflow_url = (cfg.get("ragflow_api_url") or "").strip()
        if not ragflow_url:
            return _item(configured=False, healthy=False, message="未填写 RAGFlow API 地址")
        healthy, msg = _probe_ragflow_api_url(ragflow_url, cfg.get("ragflow_api_key", ""))
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "knowflow_backend":
        knowflow_url = (cfg.get("knowflow_backend_url") or "").strip()
        knowflow_ui = (cfg.get("knowflow_ui_url") or "").strip()
        if not knowflow_url and not knowflow_ui:
            return _item(
                configured=False,
                healthy=False,
                message="未填写 KnowFlow API 或 Web UI 后台地址",
            )
        healthy, msg = _probe_knowflow_backend_urls(knowflow_url, knowflow_ui)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "ragflow_mysql":
        mysql_host = (cfg.get("ragflow_mysql_host") or "").strip()
        mysql_pwd = (cfg.get("ragflow_mysql_password") or "").strip()
        if not mysql_pwd and not mysql_host:
            return _item(
                configured=False,
                healthy=None,
                message="可选；留空时使用 .env 默认（Docker 内 knowflow-mysql）",
            )
        if not mysql_pwd:
            return _item(configured=False, healthy=False, message="未填写 MySQL 密码")
        healthy, msg = _probe_ragflow_mysql_cfg(cfg)
        return _item(configured=True, healthy=healthy, message=msg)

    raise ValueError(f"unsupported resource_id: {resource_id}")


def check_resource_health(db) -> dict[str, dict[str, Any]]:
    cfg = get_effective_model_config(db)
    out: dict[str, dict[str, Any]] = {}
    for rid in TESTABLE_RESOURCE_IDS:
        out[rid] = check_single_resource_health(rid, cfg, db)
    return out
