"""工作笔记公开分享页 — 维基风格阅读 + 本析引流。"""

from __future__ import annotations

import html as html_lib
from datetime import datetime

import markdown
from markdown.extensions import attr_list, fenced_code, tables, toc

NOTE_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --wiki-bg: #f8f9fa;
    --wiki-surface: #ffffff;
    --wiki-text: #202122;
    --wiki-muted: #54595d;
    --wiki-border: #a2a9b1;
    --wiki-border-soft: #c8ccd1;
    --wiki-link: #3366cc;
    --wiki-accent: #0a6bff;
    --promo: #0a6bff;
    --promo-hover: #0058e0;
    --promo-soft: rgba(10, 107, 255, 0.07);
    --toc-w: 220px;
    --side-w: 260px;
    --content-max: 820px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; scroll-padding-top: 64px; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", "Helvetica Neue",
      Arial, sans-serif;
    background: var(--wiki-bg);
    color: var(--wiki-text);
    line-height: 1.6;
    font-size: 13px;
  }}
  .brand-bar {{
    position: sticky; top: 0; z-index: 100;
    display: flex; align-items: center; gap: 10px;
    height: 44px; padding: 0 16px;
    background: var(--wiki-surface);
    border-bottom: 1px solid var(--wiki-border-soft);
  }}
  .brand-mark {{
    display: inline-flex; align-items: center; gap: 6px;
    text-decoration: none; color: var(--wiki-text);
  }}
  .brand-mark svg {{ width: 18px; height: 18px; color: var(--promo); }}
  .brand-mark span {{ font-size: 13px; font-weight: 500; letter-spacing: 2px; }}
  .brand-sub {{ font-size: 11px; color: var(--wiki-muted); }}
  .page {{
    display: grid;
    grid-template-columns: var(--toc-w) minmax(0, 1fr) var(--side-w);
    gap: 24px;
    max-width: calc(var(--toc-w) + var(--content-max) + var(--side-w) + 96px);
    margin: 0 auto;
    padding: 16px 16px 64px;
  }}
  .toc-panel {{ position: sticky; top: 60px; align-self: start; max-height: calc(100vh - 80px); overflow: auto; }}
  .toc-box {{
    background: var(--wiki-surface);
    border: 1px solid var(--wiki-border-soft);
    border-radius: 8px;
    padding: 12px;
  }}
  .toc-title {{ font-size: 12px; font-weight: 600; color: var(--wiki-muted); margin-bottom: 8px; }}
  .toc-list {{ list-style: none; display: flex; flex-direction: column; gap: 4px; }}
  .toc-list a {{
    display: block; color: var(--wiki-link); text-decoration: none;
    font-size: 12px; line-height: 1.4; padding: 2px 0;
  }}
  .toc-list a:hover {{ text-decoration: underline; }}
  .toc-list .lv3 {{ padding-left: 12px; font-size: 11.5px; }}
  .toc-list a.active {{ font-weight: 600; color: var(--wiki-accent); }}
  .main {{
    background: var(--wiki-surface);
    border: 1px solid var(--wiki-border-soft);
    border-radius: 8px;
    padding: 22px 28px 32px;
    min-width: 0;
  }}
  .note-header h1 {{
    font-size: 22px; font-weight: 600; line-height: 1.35;
    margin-bottom: 8px; border-bottom: 1px solid var(--wiki-border-soft);
    padding-bottom: 10px;
  }}
  .note-meta {{ font-size: 12px; color: var(--wiki-muted); margin-bottom: 18px; }}
  .note-meta .dot {{ margin: 0 6px; }}
  .note-body {{ font-size: 13.5px; line-height: 1.75; }}
  .note-body h1, .note-body h2, .note-body h3 {{
    margin: 1.4em 0 0.55em; font-weight: 600; line-height: 1.35;
  }}
  .note-body h1 {{ font-size: 1.45em; }}
  .note-body h2 {{
    font-size: 1.25em; border-bottom: 1px solid var(--wiki-border-soft);
    padding-bottom: 4px;
  }}
  .note-body h3 {{ font-size: 1.1em; }}
  .note-body p {{ margin: 0.7em 0; }}
  .note-body a {{ color: var(--wiki-link); }}
  .note-body ul, .note-body ol {{ margin: 0.6em 0 0.6em 1.4em; }}
  .note-body li {{ margin: 0.25em 0; }}
  .note-body blockquote {{
    margin: 0.8em 0; padding: 6px 12px;
    border-left: 3px solid var(--wiki-border);
    color: var(--wiki-muted); background: var(--wiki-bg);
  }}
  .note-body pre {{
    margin: 0.8em 0; padding: 12px; overflow: auto;
    background: #f3f4f6; border-radius: 6px; font-size: 12.5px;
  }}
  .note-body code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.92em;
  }}
  .note-body :not(pre) > code {{
    background: #f3f4f6; padding: 1px 5px; border-radius: 4px;
  }}
  .note-body table {{
    border-collapse: collapse; width: 100%; margin: 0.9em 0; font-size: 12.5px;
  }}
  .note-body th, .note-body td {{
    border: 1px solid var(--wiki-border-soft); padding: 6px 8px; text-align: left;
  }}
  .note-body th {{ background: var(--wiki-bg); }}
  .note-body img {{ max-width: 100%; height: auto; border-radius: 4px; }}
  .side-panel {{ position: sticky; top: 60px; align-self: start; }}
  .promo-card {{
    background: var(--wiki-surface);
    border: 1px solid var(--wiki-border-soft);
    border-radius: 8px; padding: 14px 12px 12px;
  }}
  .promo-brand {{
    font-size: 14px; font-weight: 500; letter-spacing: 2px;
    color: var(--promo); margin-bottom: 6px;
  }}
  .promo-title {{
    font-size: 12.5px; font-weight: 500; line-height: 1.45;
    color: var(--wiki-text); margin-bottom: 6px;
  }}
  .promo-desc {{
    font-size: 12px; line-height: 1.5; color: var(--wiki-muted);
    margin-bottom: 10px;
  }}
  .promo-points {{
    list-style: none; display: flex; flex-direction: column; gap: 6px;
    margin-bottom: 12px;
  }}
  .promo-points li {{
    font-size: 12px; color: var(--wiki-text);
    padding: 6px 8px; border-radius: 6px; background: var(--promo-soft);
    border: 1px solid var(--wiki-border-soft);
  }}
  .promo-cta {{
    display: block; width: 100%; text-align: center;
    padding: 8px 10px; border-radius: 6px;
    background: var(--promo); color: #fff !important;
    font-size: 12.5px; font-weight: 500; text-decoration: none !important;
  }}
  .promo-cta:hover {{ background: var(--promo-hover); }}
  .promo-note {{
    margin-top: 8px; font-size: 11px; color: var(--wiki-muted);
    text-align: center; line-height: 1.45;
  }}
  @media (max-width: 1100px) {{
    .page {{ grid-template-columns: var(--toc-w) minmax(0, 1fr); }}
    .side-panel {{ display: none; }}
  }}
  @media (max-width: 820px) {{
    .page {{ grid-template-columns: 1fr; padding: 12px 10px 48px; }}
    .toc-panel {{ position: relative; top: 0; max-height: none; }}
    .main {{ padding: 14px 12px 22px; }}
    .side-panel {{ display: block; position: relative; top: 0; margin-top: 8px; }}
  }}
</style>
</head>
<body>
  <header class="brand-bar">
    <a class="brand-mark" href="{cta_url}" title="本析">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none">
        <path transform="rotate(20 50 50)" d="M 79.91 50.00 L 50.00 50.00 Z" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"/>
        <circle cx="50" cy="50" r="28" fill="none" stroke="currentColor" stroke-width="3.5"/>
      </svg>
      <span>本析</span>
    </a>
    <span class="brand-sub">工作笔记 · 公开阅读</span>
  </header>
  <div class="page">
    <aside class="toc-panel">
      <div class="toc-box">
        <div class="toc-title">目录</div>
        <ul class="toc-list" id="toc-list"></ul>
      </div>
    </aside>
    <main class="main">
      <header class="note-header">
        <h1>{title}</h1>
        <div class="note-meta">
          <span>更新于 {date_str}</span><span class="dot">·</span>
          <span>阅读 {view_count} 次</span>
        </div>
      </header>
      <article class="note-body" id="note-body">
{body_html}
      </article>
    </main>
    <aside class="side-panel">
      <div class="promo-card">
        <div class="promo-brand">本析</div>
        <div class="promo-title">用工作笔记把想法沉淀成可分享文档</div>
        <p class="promo-desc">Markdown 编辑、文件夹整理、AI 润色与一键分享，适合个人知识沉淀与团队同步。</p>
        <ul class="promo-points">
          <li>文件夹与笔记管理</li>
          <li>AI 润色 Markdown</li>
          <li>免登录公开分享</li>
        </ul>
        <a class="promo-cta" href="{cta_url}">打开本析工作台</a>
        <p class="promo-note">登录后即可创建并管理你的笔记。</p>
      </div>
    </aside>
  </div>
<script>
(function() {{
  var body = document.getElementById('note-body');
  var list = document.getElementById('toc-list');
  if (!body || !list) return;
  var headings = body.querySelectorAll('h2, h3');
  if (!headings.length) {{
    list.parentElement.style.display = 'none';
    return;
  }}
  headings.forEach(function(h, idx) {{
    var id = h.id || ('sec-' + idx);
    h.id = id;
    var li = document.createElement('li');
    if (h.tagName === 'H3') li.className = 'lv3';
    var a = document.createElement('a');
    a.href = '#' + id;
    a.textContent = (h.textContent || '').trim();
    li.appendChild(a);
    list.appendChild(li);
  }});
}})();
</script>
</body>
</html>
"""

_MD = markdown.Markdown(
    extensions=[
        fenced_code.FencedCodeExtension(),
        tables.TableExtension(),
        toc.TocExtension(permalink=False),
        attr_list.AttrListExtension(),
    ],
    output_format="html5",
)


def _format_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt)


def render_note_html(
    content: str,
    *,
    title: str | None = None,
    updated_at: datetime | None = None,
    view_count: int = 0,
    cta_url: str = "/ai/login",
) -> str:
    """将笔记 Markdown 渲染为公开阅读 HTML。"""
    _MD.reset()
    resolved_title = (title or "").strip() or "无标题笔记"
    body_html = _MD.convert((content or "").strip() or "_（空笔记）_")
    login_url = (cta_url or "/ai/login").strip() or "/ai/login"
    return NOTE_HTML_TEMPLATE.format(
        title=html_lib.escape(resolved_title),
        date_str=html_lib.escape(_format_dt(updated_at)),
        view_count=max(0, int(view_count or 0)),
        body_html=body_html,
        cta_url=html_lib.escape(login_url, quote=True),
    )
