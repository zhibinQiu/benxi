"""KnowFlow embed proxy inject tests."""

from __future__ import annotations

from app.services.knowflow_embed_proxy import (
    inject_branding_html,
    rewrite_knowflow_root_assets,
    should_inject_branding,
)


def test_inject_branding_html_inserts_before_head_close():
    html = "<html><head><title>x</title></head><body></body></html>"
    out = inject_branding_html(html, proxy_prefix="/ragflow-ui")
    assert "/ragflow-ui/platform-branding.js" in out
    assert out.index("platform-branding.js") < out.index("</head>")


def test_inject_branding_html_rewrites_assets_when_branding_present():
    html = (
        '<html><head><link rel="stylesheet" href="/umi.abc.css">'
        '<script src="/platform-branding.js"></script></head>'
        '<body><script src="/umi.abc.js"></script></body></html>'
    )
    out = inject_branding_html(html, proxy_prefix="/ragflow-ui")
    assert 'src="/ragflow-ui/umi.abc.js"' in out
    assert 'src="/ragflow-ui/platform-branding.js"' in out


def test_should_inject_for_spa_search_path():
    assert should_inject_branding("text/html", "search") is True


def test_should_not_inject_for_static_assets():
    assert should_inject_branding("application/javascript", "umi.abc.js") is False


def test_rewrite_knowflow_root_assets():
    html = '<script src="/umi.abc.js"></script><link href="/umi.css" rel="stylesheet">'
    out = rewrite_knowflow_root_assets(html, proxy_prefix="/ragflow-ui")
    assert 'src="/ragflow-ui/umi.abc.js"' in out
    assert 'href="/ragflow-ui/umi.css"' in out
