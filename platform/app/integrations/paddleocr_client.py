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


def knowflow_paddleocr_settings_url(url: str) -> str:
    """写入 KnowFlow settings.yaml 的 paddleocr.url（保持用户原样）。"""
    return (url or "").strip().rstrip("/")


def _normalize_bbox(raw: Any) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        for key in ("bbox", "box", "coordinate"):
            if key in raw:
                return _normalize_bbox(raw[key])
        if all(k in raw for k in ("x0", "y0", "x1", "y1")):
            return [
                float(raw["x0"]),
                float(raw["y0"]),
                float(raw["x1"]),
                float(raw["y1"]),
            ]
        return None
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        if isinstance(raw[0], (list, tuple)):
            xs = [float(p[0]) for p in raw]
            ys = [float(p[1]) for p in raw]
            return [min(xs), min(ys), max(xs), max(ys)]
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    return None


def _block_from_node(node: dict, *, page: int = 1) -> dict | None:
    text = ""
    for key in ("text", "content", "markdown", "md", "block_content"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            text = val.strip()
            break
    if not text:
        return None
    bbox = _normalize_bbox(
        node.get("bbox")
        or node.get("box")
        or node.get("coordinate")
        or node.get("block_bbox")
    )
    block_type = str(node.get("type") or node.get("label") or node.get("block_type") or "text")
    page_no = node.get("page") or node.get("page_num") or node.get("pageNumber") or page
    try:
        page_int = int(page_no)
    except (TypeError, ValueError):
        page_int = page
    return {
        "text": text,
        "page": page_int,
        "bbox": bbox,
        "block_type": block_type[:32],
    }


def extract_layout_blocks(data: Any) -> list[dict]:
    """从 PaddleOCR / layout-parsing 响应提取结构化块（text + page + bbox）。"""
    blocks: list[dict] = []
    seen: set[tuple[int, str]] = set()

    def add_block(b: dict | None) -> None:
        if not b or not b.get("text"):
            return
        key = (int(b.get("page") or 1), b["text"])
        if key in seen:
            return
        seen.add(key)
        blocks.append(b)

    root = data
    if isinstance(root, list) and root:
        root = root[0]

    if isinstance(root, dict):
        rec_texts = root.get("rec_texts") or root.get("texts")
        rec_boxes = root.get("rec_boxes") or root.get("boxes")
        if isinstance(rec_texts, list):
            for i, txt in enumerate(rec_texts):
                t = str(txt or "").strip()
                if not t:
                    continue
                box = rec_boxes[i] if isinstance(rec_boxes, list) and i < len(rec_boxes) else None
                add_block(
                    {
                        "text": t,
                        "page": 1,
                        "bbox": _normalize_bbox(box),
                        "block_type": "ocr_line",
                    }
                )

    def walk(node: Any, page: int = 1) -> None:
        if isinstance(node, dict):
            p = node.get("page") or node.get("page_num") or page
            try:
                p = int(p)
            except (TypeError, ValueError):
                p = page
            parsed = _block_from_node(node, page=p)
            if parsed:
                add_block(parsed)
            for key in (
                "layoutParsingResults",
                "parsing_res_list",
                "blocks",
                "items",
                "regions",
                "paragraphs",
                "lines",
                "result",
                "data",
            ):
                child = node.get(key)
                if isinstance(child, list):
                    for item in child:
                        walk(item, p)
                elif isinstance(child, dict):
                    walk(child, p)
        elif isinstance(node, list):
            for item in node:
                walk(item, page)

    walk(root if isinstance(root, (dict, list)) else data)
    return blocks


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

    if endpoint.endswith("/ocr"):
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                res = client.post(
                    endpoint,
                    files={"file": (file_name, content, mime_type or "application/octet-stream")},
                )
        except httpx.RequestError as e:
            raise ConnectionError(f"无法连接 PaddleOCR 服务：{e}") from e
    else:
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
    blocks = extract_layout_blocks(data)
    texts = [b["text"] for b in blocks]
    if not texts:
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
    return {"text": merged, "blocks": blocks, "raw": data}
