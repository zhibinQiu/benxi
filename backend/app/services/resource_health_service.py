"""资源配置项连通性探测（管理页卡片状态指示）。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import get_settings
from app.integrations.paddleocr_client import paddleocr_request_url
from app.integrations.ragflow_client import RagflowClient
from app.integrations.mysql_conn import check_mysql_healthy
from app.services.model_settings_service import (
    _endpoint_fields,
    _legacy_paddleocr_base_url,
    get_effective_model_config,
    get_searxng_timeout_seconds,
    mask_secret,
    resolve_ragflow_api_base,
)

PROBE_TIMEOUT = 5.0

RESOURCE_ID_ALIASES = {"vision": "vl"}

TESTABLE_RESOURCE_IDS = frozenset(
    {
        "platform_api",
        "llm",
        "multimodal",
        "embedding",
        "vl",
        "vision",
        "rerank",
        "paddleocr",
        "tts",
        "speech",
        "pdf2zh",
        "searxng",
        "firecrawl",
        "neo4j",
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
        if key.endswith("_providers"):
            # 将 providers 列表序列化为 JSON 字符串存储
            import json
            try:
                merged[key] = json.dumps(val, ensure_ascii=False)
            except (TypeError, ValueError):
                pass
            continue
        if key.endswith("_active_provider"):
            merged[key] = str(val).strip()
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

    # 根据 providers 计算 flat 字段值
    _apply_providers_to_merged(merged)
    return merged


def _apply_providers_to_merged(merged: dict[str, str]) -> None:
    """从 providers + active_provider 计算 flat base_url/api_key/model 字段。"""
    for prefix in ("llm", "multimodal", "embedding", "vl", "rerank", "paddleocr", "tts"):
        providers_key = f"{prefix}_providers"
        active_key = f"{prefix}_active_provider"
        raw = merged.get(providers_key, "")
        if not raw:
            continue
        try:
            import json
            providers = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(providers, list) or len(providers) == 0:
            continue
        active_id = merged.get(active_key, "") or providers[0].get("id", "")
        active_prov = None
        for p in providers:
            if p.get("id", "") == active_id:
                active_prov = p
                break
        if active_prov is None:
            active_prov = providers[0]
        if active_prov.get("base_url"):
            merged[f"{prefix}_base_url"] = active_prov["base_url"]
        if active_prov.get("api_key"):
            merged[f"{prefix}_api_key"] = active_prov["api_key"]
        if active_prov.get("model_name"):
            merged[f"{prefix}_model"] = active_prov["model_name"]


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


def _normalize_resource_id(resource_id: str) -> str:
    rid = (resource_id or "").strip().lower()
    return RESOURCE_ID_ALIASES.get(rid, rid)


def _probe_vl(base_url: str, api_key: str, model_name: str) -> tuple[bool, str]:
    """VL 走 POST /chat/completions，验证指定模型可用（非仅 GET /models）。"""
    root = _normalize_openai_base(base_url)
    if not root:
        return False, "未填写 API 地址"
    model = (model_name or "").strip()
    if not model:
        return False, "未填写模型名称"
    url = f"{root}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "health-check"}],
        "max_tokens": 5,
    }
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT) as client:
            r = client.post(url, headers=_auth_headers(api_key), json=payload)
            if r.status_code == 200:
                return True, "连接正常"
            if r.status_code in (401, 403):
                detail = ""
                try:
                    body = r.json()
                    err = body.get("error")
                    if isinstance(err, dict):
                        detail = str(err.get("message") or "")
                    detail = detail or str(body.get("message") or "")
                except ValueError:
                    detail = r.text[:160]
                lowered = detail.lower()
                if "disabled" in lowered or "30003" in detail:
                    return False, "模型已停用或未开通（Model disabled）"
                return False, f"Key 无效或无权 (HTTP {r.status_code})"
            if r.status_code == 404:
                return False, "模型不存在或服务路径错误 (HTTP 404)"
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


def _is_openai_compatible_inference_base(base_url: str) -> bool:
    """OpenAI 兼容推理根地址（在线 API / 本地 vLLM 等）；非自建 layout-parsing OCR。"""
    base = (base_url or "").strip().lower().rstrip("/")
    if not base:
        return False
    if base.endswith("/ocr") or "layout-parsing" in base:
        return False
    return base.endswith("/v1") or "/v1/" in base


def _probe_paddleocr(service_url: str, *, api_key: str = "") -> tuple[bool, str]:
    base = (service_url or "").strip().rstrip("/")
    if not base:
        return False, "未填写服务地址"
    if _is_openai_compatible_inference_base(base):
        return _probe_openai_compatible(base, api_key)
    endpoint = paddleocr_request_url(base)
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


def _probe_neo4j(uri: str, user: str, password: str, database: str) -> tuple[bool, str]:
    """探测 Neo4j 连通性。"""
    url = (uri or "").strip()
    if not url:
        return False, "未填写连接地址"
    try:
        from neo4j import AsyncGraphDatabase
        import asyncio

        async def _probe():
            try:
                driver = AsyncGraphDatabase.driver(url, auth=(user, password) if password else None)
                async with driver.session(database=database or None) as session:
                    r = await session.run("RETURN 1 AS ok")
                    rec = await r.single()
                    ok = bool(rec and rec.get("ok") == 1)
                await driver.close()
                return ok, "连接正常" if ok else "查询无返回"
            except Exception as exc:
                msg = str(exc)
                if "Authentication" in msg or "Unauthorized" in msg:
                    return False, "认证失败，请检查用户名/密码"
                if "Connection" in msg or "connect" in msg.lower():
                    return False, f"无法连接：{msg[:120]}"
                return False, msg[:200]

        return asyncio.run(_probe())
    except ImportError:
        return False, "neo4j Python 驱动未安装"


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


def _probe_knowflow_backend_url(api_base: str) -> tuple[bool, str]:
    """探测 KnowFlow 扩展 API（平台不依赖 RAGFlow Web UI）。"""
    api_base = (api_base or "").rstrip("/")
    if not api_base:
        return False, "未填写知识库扩展 API 地址"

    for path in ("/health", "/api/health", "/api/v1/health"):
        api_ok, api_msg = _probe_http_get(f"{api_base}{path}", accept_405=True)
        if api_ok:
            return True, api_msg
    return _probe_http_get(api_base, accept_405=True)


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
    return check_mysql_healthy(
        host=host,
        port=port,
        password=password,
        database=db_name or "rag_flow",
        connect_timeout=10,
        read_timeout=10,
        write_timeout=10,
    )


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


def _probe_tts(base_url: str, api_key: str, model_name: str) -> tuple[bool, str]:
    from app.integrations.siliconflow_tts_client import (
        DEFAULT_TTS_MODEL,
        build_speech_api_url,
        voice_param,
    )

    url = build_speech_api_url(base_url)
    if not url:
        return False, "API 地址无效"
    model = (model_name or "").strip() or DEFAULT_TTS_MODEL
    payload = {
        "model": model,
        "voice": voice_param("alex", model=model),
        "input": "测试",
        "response_format": "mp3",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code == 200:
            return True, "连接正常"
        if r.status_code in (401, 403):
            return False, f"认证失败 HTTP {r.status_code}"
        detail = (r.text or "")[:120]
        return False, f"HTTP {r.status_code}{(': ' + detail) if detail else ''}"
    except httpx.TimeoutException:
        return False, "连接超时（>30s）"
    except httpx.HTTPError as exc:
        return False, f"无法连接：{exc}"


def _searxng_timeout_from_cfg(cfg: dict[str, str], db) -> float:
    """与联网搜索使用同一超时配置，避免探测 5s 过短而业务请求仍成功。"""
    raw = (cfg.get("searxng_timeout_seconds") or "").strip()
    if raw:
        try:
            return max(3.0, float(raw))
        except (TypeError, ValueError):
            pass
    return get_searxng_timeout_seconds(db)


def _probe_searxng_url(searxng_url: str, *, timeout: float | None = None) -> tuple[bool, str]:
    base = (searxng_url or "").strip().rstrip("/")
    if not base:
        return False, "未填写服务地址"
    probe_timeout = max(3.0, float(timeout or get_settings().searxng_timeout_seconds or 15.0))
    url = urljoin(f"{base}/", "search")
    try:
        with httpx.Client(timeout=probe_timeout, follow_redirects=True) as client:
            r = client.get(
                url,
                params={"q": "ping", "format": "json", "pageno": 1},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "pdf-trans-platform/1.0",
                },
            )
            if r.status_code >= 400:
                return False, f"HTTP {r.status_code}"
            payload = r.json()
            if isinstance(payload, dict) and "results" in payload:
                return True, "连接正常"
            return False, "返回格式异常"
    except httpx.TimeoutException:
        return False, f"连接超时（>{probe_timeout:g}s）"
    except httpx.HTTPError as exc:
        return False, f"无法连接：{exc}"
    except ValueError:
        return False, "返回非 JSON"


def _probe_firecrawl_url(api_url: str, api_key: str, *, timeout: float | None = None) -> tuple[bool, str]:
    base = (api_url or "").strip().rstrip("/")
    if not base:
        return False, "未填写 API 地址"
    probe_timeout = max(3.0, float(timeout or 10.0))
    try:
        with httpx.Client(timeout=probe_timeout, follow_redirects=True) as client:
            if api_key:
                r = client.get(
                    f"{base}/v1/health",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            else:
                r = client.get(f"{base}/v1/health")
            if r.status_code == 200:
                return True, "FireCrawl 服务正常"
            detail = (r.text or "")[:120]
            return False, f"HTTP {r.status_code}{(': ' + detail) if detail else ''}"
    except httpx.TimeoutException:
        return False, f"连接超时（>{probe_timeout:g}s）"
    except httpx.HTTPError as exc:
        return False, f"无法连接：{exc}"


def check_resource_providers(resource_id: str, cfg: dict[str, str]) -> list[dict[str, Any]]:
    """遍历一个资源的所有服务源（provider），逐个测试连通性。

    只对支持多 provider 的资源类型生效（llm、multimodal、embedding、vl、rerank、paddleocr、tts）。
    返回列表，每个元素包含 provider_id、provider_label、configured、healthy、message。
    """
    import json

    rid = _normalize_resource_id(resource_id)
    PROVIDER_PREFIXES = {"llm", "multimodal", "embedding", "vl", "rerank", "paddleocr", "tts"}
    prefix = rid if rid in PROVIDER_PREFIXES else None
    if prefix is None:
        return []

    providers_key = f"{prefix}_providers"
    raw = cfg.get(providers_key, "")
    if not raw:
        return []

    try:
        providers = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(providers, list) or len(providers) == 0:
        return []

    results: list[dict[str, Any]] = []
    for idx, prov in enumerate(providers):
        prov_id = prov.get("id", "")
        prov_label = (
            prov.get("label", "")
            or prov.get("model_name", "")
            or f"服务源 {idx + 1}"
        )
        base_url = (prov.get("base_url") or "").strip()
        api_key = (prov.get("api_key") or "").strip()
        model_name = (prov.get("model_name") or "").strip()

        if not (base_url and api_key and model_name):
            results.append(
                {
                    "provider_id": prov_id,
                    "provider_label": prov_label,
                    "configured": bool(base_url and api_key and model_name),
                    "healthy": None,
                    "message": "配置不完整",
                }
            )
            continue

        if rid in ("llm", "multimodal"):
            healthy, msg = _probe_openai_compatible(base_url, api_key)
        elif rid == "embedding":
            healthy, msg = _probe_embedding(base_url, api_key, model_name)
        elif rid == "vl":
            healthy, msg = _probe_vl(base_url, api_key, model_name)
        elif rid == "rerank":
            healthy, msg = _probe_rerank(base_url, api_key, model_name)
        elif rid == "paddleocr":
            healthy, msg = _probe_paddleocr(base_url, api_key=api_key)
        elif rid == "tts":
            healthy, msg = _probe_tts(base_url, api_key, model_name)
        else:
            continue

        results.append(
            {
                "provider_id": prov_id,
                "provider_label": prov_label,
                "configured": True,
                "healthy": healthy,
                "message": msg,
            }
        )

    return results


def check_single_resource_health(resource_id: str, cfg: dict[str, str], db) -> dict[str, Any]:
    """按给定配置探测单项资源（用于保存前测试）。"""
    _ = db
    rid = _normalize_resource_id(resource_id)
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

    if rid == "multimodal":
        mm_ok_cfg = _endpoint_configured(
            base_url=cfg.get("multimodal_base_url", ""),
            api_key=cfg.get("multimodal_api_key", ""),
            model_name=cfg.get("multimodal_model", ""),
        )
        if not mm_ok_cfg:
            return _item(configured=False, healthy=False, message="请填写 API 地址、模型与 Key")
        healthy, msg = _probe_openai_compatible(cfg["multimodal_base_url"], cfg["multimodal_api_key"])
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

    if rid == "vl":
        vl_base, vl_key, vl_model = _endpoint_fields(cfg, "vl")
        if not _endpoint_configured(
            base_url=vl_base, api_key=vl_key, model_name=vl_model
        ):
            return _item(
                configured=False,
                healthy=False,
                message="请填写 VL 模型 API 地址、模型名与 Key",
            )
        healthy, msg = _probe_vl(vl_base, vl_key, vl_model)
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
        paddle_base, paddle_key, paddle_model = _endpoint_fields(cfg, "paddleocr")
        if not paddle_base:
            paddle_base = _legacy_paddleocr_base_url(cfg)
        if not paddle_base:
            return _item(configured=False, healthy=False, message="未填写 API 地址")
        if not paddle_model and not _is_openai_compatible_inference_base(paddle_base):
            return _item(configured=False, healthy=False, message="请填写模型名称")
        healthy, msg = _probe_paddleocr(paddle_base, api_key=paddle_key)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "tts":
        tts_base, tts_key, tts_model = _endpoint_fields(cfg, "tts")
        if not _endpoint_configured(
            base_url=tts_base, api_key=tts_key, model_name=tts_model
        ):
            return _item(
                configured=False,
                healthy=False,
                message="请填写 API 地址、模型名与 Key",
            )
        healthy, msg = _probe_tts(tts_base, tts_key, tts_model)
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

    if rid == "searxng":
        searxng_url = (cfg.get("searxng_url") or "").strip()
        if not searxng_url:
            return _item(configured=False, healthy=False, message="未填写 SearXNG 地址")
        timeout = _searxng_timeout_from_cfg(cfg, db)
        healthy, msg = _probe_searxng_url(searxng_url, timeout=timeout)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "firecrawl":
        firecrawl_api_url = (cfg.get("firecrawl_api_url") or "https://api.firecrawl.dev").strip()
        firecrawl_api_key = (cfg.get("firecrawl_api_key") or "").strip()
        if not firecrawl_api_url:
            return _item(configured=False, healthy=False, message="未填写 API 地址")
        healthy, msg = _probe_firecrawl_url(firecrawl_api_url, firecrawl_api_key)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "neo4j":
        neo4j_uri = (cfg.get("neo4j_uri") or "").strip()
        neo4j_user = (cfg.get("neo4j_user") or "").strip()
        neo4j_password = (cfg.get("neo4j_password") or "").strip()
        neo4j_database = (cfg.get("neo4j_database") or "").strip()
        if not neo4j_uri:
            return _item(configured=False, healthy=False, message="未填写连接地址")
        configured = bool(neo4j_uri and neo4j_user)
        healthy, msg = _probe_neo4j(neo4j_uri, neo4j_user, neo4j_password, neo4j_database)
        return _item(configured=configured, healthy=healthy, message=msg)

    if rid == "ragflow_api":
        ragflow_url = (cfg.get("ragflow_api_url") or "").strip()
        if not ragflow_url:
            return _item(configured=False, healthy=False, message="未填写知识库 API 地址")
        healthy, msg = _probe_ragflow_api_url(ragflow_url, cfg.get("ragflow_api_key", ""))
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "knowflow_backend":
        knowflow_url = (cfg.get("knowflow_backend_url") or "").strip()
        if not knowflow_url:
            return _item(
                configured=False,
                healthy=False,
                message="未填写知识库扩展 API 地址",
            )
        healthy, msg = _probe_knowflow_backend_url(knowflow_url)
        return _item(configured=True, healthy=healthy, message=msg)

    if rid == "ragflow_mysql":
        mysql_host = (cfg.get("ragflow_mysql_host") or "").strip()
        mysql_pwd = (cfg.get("ragflow_mysql_password") or "").strip()
        if not mysql_pwd and not mysql_host:
            return _item(
                configured=False,
                healthy=None,
                message="可选；留空时使用 .env 默认（Docker 内置 MySQL）",
            )
        if not mysql_pwd:
            return _item(configured=False, healthy=False, message="未填写 MySQL 密码")
        healthy, msg = _probe_ragflow_mysql_cfg(cfg)
        return _item(configured=True, healthy=healthy, message=msg)

    raise ValueError(f"unsupported resource_id: {resource_id}")


def _check_one(rid: str, cfg: dict[str, str]) -> dict[str, Any]:
    """包装 check_single_resource_health，用 None db 避免跨线程共享 session。"""
    return check_single_resource_health(rid, cfg, None)


def check_resource_health(db) -> dict[str, dict[str, Any]]:
    cfg = get_effective_model_config(db)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    seen: set[str] = set()
    tasks: list[tuple[str, str]] = []
    for rid in TESTABLE_RESOURCE_IDS:
        canonical = _normalize_resource_id(rid)
        if canonical in seen:
            continue
        seen.add(canonical)
        tasks.append((canonical, rid))

    out: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        fut_map = {
            pool.submit(_check_one, rid, cfg): canonical
            for canonical, rid in tasks
        }
        for fut in as_completed(fut_map):
            try:
                out[fut_map[fut]] = fut.result()
            except Exception as exc:
                out[fut_map[fut]] = _item(configured=False, healthy=None, message=str(exc))
    return out
