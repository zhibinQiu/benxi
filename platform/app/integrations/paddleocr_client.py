"""PaddleOCR 服务客户端（文档切片解析与 OCR 功能共用）。"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def normalize_paddleocr_service_url(url: str) -> str:
    """KnowFlow settings.yaml 使用服务根地址（不含 /ocr 路径）。"""
    raw = (url or "").strip().rstrip("/")
    if raw.endswith("/ocr"):
        return raw[: -len("/ocr")]
    return raw


def paddleocr_request_url(url: str) -> str:
    """平台 OCR 请求地址：保留用户配置的 /ocr 或回退 layout-parsing。"""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.endswith("/ocr"):
        return raw
    return f"{raw}/layout-parsing"


def recognize_bytes(
    content: bytes,
    *,
    service_url: str,
    file_name: str = "upload.bin",
    mime_type: str = "application/octet-stream",
    timeout_sec: float = 120,
) -> dict[str, Any]:
    endpoint = paddleocr_request_url(service_url)
    if not endpoint:
        raise ValueError("未配置 PaddleOCR 服务地址")

    payload = {
        "file": base64.b64encode(content).decode("ascii"),
        "fileType": 0 if (mime_type or "").lower() == "application/pdf" else 1,
        "fileName": file_name,
    }
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            res = client.post(endpoint, json=payload)
    except httpx.RequestError as e:
        raise ConnectionError(f"无法连接 PaddleOCR 服务：{e}") from e

    if res.status_code >= 400:
        raise RuntimeError(
            f"PaddleOCR 请求失败 HTTP {res.status_code}: {res.text[:500]}"
        )

    data = res.json()
    if isinstance(data, dict) and data.get("errorCode") not in (None, 0, "0"):
        raise RuntimeError(str(data.get("errorMsg") or data.get("message") or data))

    return _extract_text_payload(data)


def _extract_text_payload(data: Any) -> dict[str, Any]:
    """兼容多种 PaddleOCR / layout-parsing 响应结构。"""
    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in ("text", "content", "markdown", "md"):
                val = node.get(key)
                if isinstance(val, str) and val.strip():
                    texts.append(val.strip())
            for key in ("result", "data", "layoutParsingResults", "blocks", "items"):
                child = node.get(key)
                if isinstance(child, list):
                    for item in child:
                        walk(item)
                elif child is not None:
                    walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    merged = "\n".join(dict.fromkeys(texts))
    return {"text": merged, "raw": data}
