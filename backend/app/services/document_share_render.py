"""文档公开分享页 — 在线预览最新版本。"""

from __future__ import annotations

import html as html_lib
from datetime import datetime


DOC_SHARE_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #f4f6f8;
    --surface: #ffffff;
    --text: #1e293b;
    --muted: #64748b;
    --border: #e2e8f0;
    --accent: #0a6bff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    flex-direction: column;
  }}
  .brand-bar {{
    flex-shrink: 0;
    display: flex; align-items: center; gap: 10px;
    height: 44px; padding: 0 16px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }}
  .brand-mark {{
    display: inline-flex; align-items: center; gap: 6px;
    text-decoration: none; color: var(--text);
  }}
  .brand-mark svg {{ width: 18px; height: 18px; color: var(--accent); }}
  .brand-mark span {{ font-size: 13px; font-weight: 500; letter-spacing: 2px; }}
  .brand-sub {{ font-size: 11px; color: var(--muted); margin-left: auto; }}
  .header {{
    flex-shrink: 0;
    padding: 12px 16px 8px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }}
  .header h1 {{
    font-size: 16px; font-weight: 600; line-height: 1.35;
    word-break: break-word;
  }}
  .meta {{
    margin-top: 4px;
    font-size: 12px; color: var(--muted);
  }}
  .meta .sep {{ margin: 0 6px; opacity: 0.5; }}
  .viewer {{
    flex: 1; min-height: 0;
    display: flex; flex-direction: column;
    padding: 12px 16px 16px;
  }}
  .viewer iframe, .viewer img {{
    flex: 1; min-height: 0;
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
  }}
  .viewer img {{
    object-fit: contain;
    padding: 12px;
  }}
  .fallback {{
    flex: 1;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 12px;
    border: 1px dashed var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--muted);
    font-size: 13px;
    text-align: center;
    padding: 24px;
  }}
  .fallback a {{
    display: inline-flex; align-items: center;
    padding: 8px 16px;
    border-radius: 6px;
    background: var(--accent);
    color: #fff;
    text-decoration: none;
    font-size: 13px;
  }}
  .fallback a:hover {{ opacity: 0.92; }}
</style>
</head>
<body>
  <div class="brand-bar">
    <a class="brand-mark" href="{cta_url}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      </svg>
      <span>本析</span>
    </a>
    <span class="brand-sub">文档分享预览</span>
  </div>
  <header class="header">
    <h1>{title}</h1>
    <div class="meta">
      <span>{file_name}</span>
      <span class="sep">·</span>
      <span>{size_label}</span>
      <span class="sep">·</span>
      <span>更新于 {date_str}</span>
    </div>
  </header>
  <div class="viewer">
{viewer_html}
  </div>
</body>
</html>
"""


def _format_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt)


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _preview_kind(file_name: str, mime: str) -> str:
    name = (file_name or "").lower()
    m = (mime or "").lower()
    if "pdf" in m or name.endswith(".pdf"):
        return "pdf"
    if m.startswith("image/") or name.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
    ):
        return "image"
    if m.startswith("text/") or name.endswith(
        (".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm")
    ):
        return "text"
    return "other"


def render_document_share_html(
    *,
    title: str,
    file_name: str,
    mime_type: str,
    file_size: int,
    updated_at: datetime | None,
    file_url: str,
    cta_url: str = "/ai/",
) -> str:
    """渲染文档公开分享预览页 HTML。"""
    kind = _preview_kind(file_name, mime_type)
    safe_file_url = html_lib.escape(file_url, quote=True)
    if kind in ("pdf", "text"):
        viewer = (
            f'<iframe src="{safe_file_url}" title="document preview" '
            'allow="fullscreen"></iframe>'
        )
    elif kind == "image":
        viewer = f'<img src="{safe_file_url}" alt="{html_lib.escape(file_name)}" />'
    else:
        viewer = (
            '<div class="fallback">'
            "<p>该格式暂不支持内嵌预览，请下载后查看</p>"
            f'<a href="{safe_file_url}" download>下载文件</a>'
            "</div>"
        )
    return DOC_SHARE_HTML.format(
        title=html_lib.escape(title or "文档"),
        file_name=html_lib.escape(file_name or "—"),
        size_label=_format_size(int(file_size or 0)),
        date_str=_format_dt(updated_at),
        cta_url=html_lib.escape(cta_url, quote=True),
        viewer_html=viewer,
    )
