"""Skill 沙箱运行时 — 注入到临时工作区，供上传的 Python 入口使用。

提供：
  - ``fetch_text(url)``: 可控 HTTP GET（SSRF 防护）
  - ``finish(conclusion)``: 输出 JSON 结论
"""

from __future__ import annotations

import ipaddress
import json
import socket
from typing import Final
from urllib.parse import urlparse

import httpx

_DEFAULT_TIMEOUT: Final[float] = 15.0
_DEFAULT_MAX_BYTES: Final[int] = 512_000

__all__ = [
    "fetch_text",
    "finish",
]


# ── SSRF 防护 ────────────────────────────────────────────────────────────────


def _host_blocked(host: str) -> bool:
    if not host:
        return True
    host = host.strip().lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"}:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def _validate_http_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are supported")
    if _host_blocked(parsed.hostname or ""):
        raise ValueError("This URL points to an internal or private address and is not allowed")
    return parsed.geturl()


# ── 公共 API ─────────────────────────────────────────────────────────────────


def fetch_text(url: str, *, timeout: float = _DEFAULT_TIMEOUT, max_bytes: int = _DEFAULT_MAX_BYTES) -> str:
    """拉取网页/接口文本（仅内存，不落盘）。"""
    safe_url = _validate_http_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(safe_url)
        resp.raise_for_status()
        data = resp.content[:max(1, int(max_bytes))]
    return data.decode(resp.encoding or "utf-8", errors="replace")


def finish(conclusion: str, *, hint: str = "") -> None:
    """输出分析结论（JSON 单行）。"""
    body = {"conclusion": (conclusion or "").strip()}
    hint_text = (hint or "").strip()
    if hint_text:
        body["hint"] = hint_text
    print(json.dumps(body, ensure_ascii=False))
