"""KnowFlow Web UI 反代：注入平台白标脚本（远程 KnowFlow 未挂载 theme 时仍生效）。"""

from __future__ import annotations

import re
from pathlib import Path

THEME_DIR = Path(__file__).resolve().parents[2] / "knowflow-theme"
BRANDING_MARKER = "platform-branding.js"
INJECT_TEMPLATE = (
    '<link rel="stylesheet" href="{prefix}/platform-branding.css">'
    '<script src="{prefix}/platform-branding.js"></script>'
)


def branding_asset_path(name: str) -> Path:
    path = THEME_DIR / name
    if not path.is_file():
        msg = f"KnowFlow theme asset missing: {path}"
        raise FileNotFoundError(msg)
    return path


def rewrite_knowflow_root_assets(body: str, *, proxy_prefix: str) -> str:
    """将 HTML 内根路径静态引用改为 /ragflow-ui/...，供同源反代使用。"""
    prefix = (proxy_prefix or "/ragflow-ui").rstrip("/")
    if f'="{prefix}/' in body or f"='{prefix}/" in body:
        return body

    def _repl(match: re.Match[str]) -> str:
        attr, quote, path = match.group(1), match.group(2), match.group(3)
        if path.startswith(("http://", "https://", "//", "data:", "blob:", prefix + "/")):
            return match.group(0)
        return f'{attr}={quote}{prefix}{path}{quote}'

    return re.sub(
        r"""(href|src)=(['"])(/(?!/)[^'"]*)\2""",
        _repl,
        body,
    )


def inject_branding_html(body: str, *, proxy_prefix: str) -> str:
    """向 KnowFlow index.html 注入 platform-branding，并改写静态资源为同源前缀。"""
    prefix = (proxy_prefix or "/ragflow-ui").rstrip("/")
    body = rewrite_knowflow_root_assets(body, proxy_prefix=prefix)
    body = body.replace('href="/platform-branding.css"', f'href="{prefix}/platform-branding.css"')
    body = body.replace("href='/platform-branding.css'", f"href='{prefix}/platform-branding.css'")
    body = body.replace('src="/platform-branding.js"', f'src="{prefix}/platform-branding.js"')
    body = body.replace("src='/platform-branding.js'", f"src='{prefix}/platform-branding.js'")
    if f"{prefix}/{BRANDING_MARKER}" in body or f'"{prefix}/platform-branding.js"' in body:
        return body
    if BRANDING_MARKER in body and 'src="/' not in body and "src='/" not in body:
        return body
    inject = INJECT_TEMPLATE.format(prefix=prefix)
    if "</head>" in body:
        return body.replace("</head>", f"{inject}</head>", 1)
    if "<body>" in body:
        return body.replace("<body>", f"<body>{inject}", 1)
    return inject + body


_STATIC_EXT = frozenset(
    {
        "js",
        "css",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "svg",
        "woff",
        "woff2",
        "map",
        "ico",
        "json",
        "txt",
        "wasm",
    }
)


def should_inject_branding(content_type: str | None, subpath: str) -> bool:
    """SPA 路由（如 /search）也返回 index.html，需注入白标脚本。"""
    rel = (subpath or "").strip().lower()
    if rel:
        leaf = rel.rsplit("/", 1)[-1]
        if "." in leaf:
            ext = leaf.rsplit(".", 1)[-1]
            if ext in _STATIC_EXT:
                return False
    ct = (content_type or "").lower()
    return "html" in ct or not ct
