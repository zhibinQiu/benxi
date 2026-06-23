"""浏览器 RPA 用 URL 安全校验（与 skill_script_runtime 策略一致）。"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def host_blocked(host: str) -> bool:
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
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return True
    return False


def validate_browser_url(url: str, *, allowed_domains: str = "") -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持 http/https URL")
    hostname = (parsed.hostname or "").strip().lower()
    if host_blocked(hostname):
        raise ValueError("不允许访问内网或本机地址")
    allowlist = [
        d.strip().lower().lstrip(".")
        for d in (allowed_domains or "").split(",")
        if d.strip()
    ]
    if allowlist:
        matched = any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in allowlist
        )
        if not matched:
            raise ValueError(f"域名不在白名单内: {hostname}")
    return parsed.geturl()
