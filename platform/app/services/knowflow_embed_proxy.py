"""KnowFlow Web UI 反代：注入平台白标脚本（远程 KnowFlow 未挂载 theme 时仍生效）。"""

from __future__ import annotations

import re
from pathlib import Path

# 容器内 /app/knowflow-theme（Dockerfile COPY）；本地开发可回退 deploy/knowflow/theme
_APP_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _APP_ROOT.parent
THEME_DIR = _APP_ROOT / "knowflow-theme"
_DEPLOY_THEME = _REPO_ROOT / "deploy" / "knowflow" / "theme"
BRANDING_MARKER = "platform-branding.js"
INJECT_TEMPLATE = (
    '<link rel="stylesheet" href="{prefix}/platform-branding.css">'
    '<script src="{prefix}/platform-branding.js"></script>'
)
# KnowFlow umi 路由在根 path（/knowledge）；反代挂在 /ragflow-ui 下时须先修正 pathname
_SPA_PATH_STRIP_TEMPLATE = (
    '<script>(function(){{var p="{prefix}";var l=location.pathname;'
    'if(l===p||l.indexOf(p+"/")===0){{var n=l.slice(p.length)||"/";'
    'history.replaceState(null,"",n+location.search+location.hash);'
    '}}}})();</script>'
)
# umi 构建 publicPath 为 /；子路径反代时须指向 /ragflow-ui/
_PUBLIC_PATH_BOOTSTRAP_TEMPLATE = (
    '<script>window.publicPath="{prefix}/";'
    'window.__webpack_public_path__="{prefix}/";</script>'
)


def branding_asset_path(name: str) -> Path:
    for base in (THEME_DIR, _DEPLOY_THEME):
        path = base / name
        if path.is_file():
            return path
    msg = f"KnowFlow theme asset missing: {name} (checked {THEME_DIR}, {_DEPLOY_THEME})"
    raise FileNotFoundError(msg)


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


def spa_path_prefix_strip_script(*, proxy_prefix: str) -> str:
    """生成内联脚本：将 /ragflow-ui/knowledge 等 URL 修正为 umi 可识别的 /knowledge。"""
    prefix = (proxy_prefix or "/ragflow-ui").rstrip("/")
    if not prefix or prefix == "/":
        return ""
    return _SPA_PATH_STRIP_TEMPLATE.format(prefix=prefix.replace("\\", "\\\\").replace('"', '\\"'))


def public_path_bootstrap_script(*, proxy_prefix: str) -> str:
    """生成内联脚本：在 umi 启动前设置 webpack publicPath。"""
    prefix = (proxy_prefix or "/ragflow-ui").rstrip("/")
    if not prefix or prefix == "/":
        return ""
    escaped = prefix.replace("\\", "\\\\").replace('"', '\\"')
    return _PUBLIC_PATH_BOOTSTRAP_TEMPLATE.format(prefix=escaped)


def rewrite_umi_runtime_public_path(body: str, *, proxy_prefix: str) -> str:
    """改写 umi 主包内 publicPath，使 lazy chunk 从 /ragflow-ui/ 加载。"""
    prefix = (proxy_prefix or "/ragflow-ui").rstrip("/") + "/"
    if prefix == "/":
        return body
    if 'publicPath:"/"' in body:
        body = body.replace('publicPath:"/"', f'publicPath:"{prefix}"', 1)
    if "publicPath:'/'" in body:
        body = body.replace("publicPath:'/'", f"publicPath:'{prefix}'", 1)
    if "runtimePublicPath:false" in body:
        body = body.replace("runtimePublicPath:false", "runtimePublicPath:true", 1)
    return body


def should_rewrite_umi_public_path(content_type: str | None, subpath: str) -> bool:
    rel = (subpath or "").strip().lower()
    if not rel.endswith(".js"):
        return False
    leaf = rel.rsplit("/", 1)[-1]
    if not (leaf.startswith("umi.") or leaf.startswith("p__") or ".async." in leaf):
        return False
    ct = (content_type or "").lower()
    return "javascript" in ct or not ct


def inject_spa_path_prefix_strip(body: str, *, proxy_prefix: str) -> str:
    """在 <head> 最前注入 pathname / publicPath 修正（须早于 platform-branding / umi）。"""
    prefix = (proxy_prefix or "/ragflow-ui").rstrip("/")
    if not prefix or prefix == "/":
        return body
    strip = spa_path_prefix_strip_script(proxy_prefix=prefix)
    boot = public_path_bootstrap_script(proxy_prefix=prefix)
    inject = strip + boot
    if not inject or "window.publicPath=" in body:
        return body
    if "<head>" in body:
        return body.replace("<head>", f"<head>{inject}", 1)
    return re.sub(r"(<head[^>]*>)", rf"\1{inject}", body, count=1)


def inject_branding_html(body: str, *, proxy_prefix: str) -> str:
    """向 KnowFlow index.html 注入 platform-branding；子路径部署时再改写静态资源前缀。"""
    prefix = (proxy_prefix or "").strip().rstrip("/")
    if prefix and prefix != "/":
        body = rewrite_knowflow_root_assets(body, proxy_prefix=prefix)
        body = inject_spa_path_prefix_strip(body, proxy_prefix=prefix)
        branding_prefix = prefix
    else:
        branding_prefix = ""
    if branding_prefix:
        body = body.replace('href="/platform-branding.css"', f'href="/{branding_prefix.lstrip("/")}/platform-branding.css"')
        body = body.replace("href='/platform-branding.css'", f"href='/{branding_prefix.lstrip('/')}/platform-branding.css'")
        body = body.replace('src="/platform-branding.js"', f'src="/{branding_prefix.lstrip("/")}/platform-branding.js"')
        body = body.replace("src='/platform-branding.js'", f"src='/{branding_prefix.lstrip('/')}/platform-branding.js'")
    if BRANDING_MARKER in body:
        return body
    if branding_prefix:
        inject = INJECT_TEMPLATE.format(prefix=f"/{branding_prefix.lstrip('/')}")
    else:
        inject = (
            '<link rel="stylesheet" href="/platform-branding.css">'
            '<script src="/platform-branding.js"></script>'
        )
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
