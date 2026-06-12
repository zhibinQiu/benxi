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


def is_openai_compatible_ocr_base(base_url: str) -> bool:
    """OpenAI 兼容推理根地址（硅基流动等）；非自建 layout-parsing /ocr。"""
    base = (base_url or "").strip().lower().rstrip("/")
    if not base:
        return False
    if base.endswith("/ocr") or "layout-parsing" in base:
        return False
    return base.endswith("/v1") or "/v1/" in base


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


def _chat_completions_url(base_url: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _recognize_openai_compatible(
    content: bytes,
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    file_name: str,
    mime_type: str,
    timeout_sec: float,
    language: str = "",
) -> dict[str, Any]:
    mime = (mime_type or "application/octet-stream").lower()
    if mime == "application/pdf":
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if text:
            block = {"text": text, "page": 1, "bbox": None, "block_type": "text"}
            return {
                "text": text,
                "blocks": [block],
                "raw": {"source": "pdf_text_layer"},
            }
        raise ValueError(
            "PDF 无文本层；在线 OCR 请上传图片，或配置本地 PaddleOCR layout-parsing 服务"
        )

    if not model_name.strip():
        raise ValueError("未配置 PaddleOCR 模型名")

    b64 = base64.b64encode(content).decode("ascii")
    data_url = f"data:{mime_type or 'application/octet-stream'};base64,{b64}"
    lang_hint = f"识别语言偏好：{language}。" if language else ""
    prompt = (
        f"请识别图像中的全部文字，按自然阅读顺序输出。{lang_hint}"
        "保留段落换行，不要添加解释或 Markdown 标题。"
    )
    payload: dict[str, Any] = {
        "model": model_name.strip(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0,
    }
    headers: dict[str, str] = {}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    url = _chat_completions_url(base_url)
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            res = client.post(url, json=payload, headers=headers)
    except httpx.RequestError as e:
        raise ConnectionError(f"无法连接 OCR 服务：{e}") from e

    if res.status_code >= 400:
        raise RuntimeError(f"OCR 请求失败 HTTP {res.status_code}: {res.text[:500]}")

    data = res.json()
    choices = data.get("choices") if isinstance(data, dict) else None
    text = ""
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            text = str(message.get("content") or "").strip()
    if not text:
        raise RuntimeError("OCR 服务未返回识别文本")

    block = {"text": text, "page": 1, "bbox": None, "block_type": "text"}
    return {"text": text, "blocks": [block], "raw": data}


def recognize_bytes(
    content: bytes,
    *,
    service_url: str,
    api_key: str = "",
    model_name: str = "",
    file_name: str = "upload.bin",
    mime_type: str = "application/octet-stream",
    timeout_sec: float = 120,
    language: str = "",
) -> dict[str, Any]:
    base = (service_url or "").strip()
    if not base:
        raise ValueError("未配置 PaddleOCR 服务地址")

    if is_openai_compatible_ocr_base(base):
        return _recognize_openai_compatible(
            content,
            base_url=base,
            api_key=api_key,
            model_name=model_name,
            file_name=file_name,
            mime_type=mime_type,
            timeout_sec=timeout_sec,
            language=language,
        )

    endpoint = paddleocr_request_url(base)
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
