"""理财报告 HTML 渲染 — 维基百科风格阅读页。

布局：
  - 顶栏：本析品牌
  - 左侧：目录（维基 TOC 风格）
  - 中间：报告摘要卡片 + 正文
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone, timedelta

import markdown
from markdown.extensions import attr_list, fenced_code, tables, toc

# 中国常见 UTC+8 偏移：旧数据 completed_at 为 naive 本地时与 UTC created_at 相减会多出约 8 小时
_CN_OFFSET = timedelta(hours=8)

REPORT_HTML_TEMPLATE = """\
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
    --wiki-link-hover: #0645ad;
    --wiki-toc-bg: #f8f9fa;
    --wiki-accent: #0a6bff;
    --toc-w: 220px;
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
  .brand-mark svg {{ width: 18px; height: 18px; color: var(--wiki-accent); }}
  .brand-mark span {{ font-size: 13px; font-weight: 500; letter-spacing: 2px; }}
  .brand-sub {{ font-size: 11px; color: var(--wiki-muted); }}

  .page {{
    display: grid;
    grid-template-columns: var(--toc-w) minmax(0, 1fr);
    gap: 24px;
    max-width: calc(var(--toc-w) + var(--content-max) + 64px);
    margin: 0 auto;
    padding: 16px 16px 64px;
  }}

  /* ── 左侧目录（维基） ── */
  .toc-panel {{
    position: sticky; top: 60px; align-self: start;
    max-height: calc(100vh - 76px); overflow-y: auto;
  }}
  .toc-box {{
    background: var(--wiki-toc-bg);
    border: 1px solid var(--wiki-border-soft);
    border-radius: 2px;
    padding: 10px 10px 8px;
  }}
  .toc-title {{
    font-size: 12px; font-weight: 600; text-align: center;
    margin-bottom: 6px; color: var(--wiki-text);
  }}
  .toc-list {{ list-style: none; }}
  .toc-list a {{
    display: block; padding: 2px 0;
    color: var(--wiki-link); text-decoration: none;
    font-size: 11.5px; line-height: 1.4;
  }}
  .toc-list a:hover {{ text-decoration: underline; color: var(--wiki-link-hover); }}
  .toc-list a.level-3 {{ padding-left: 12px; font-size: 11px; }}
  .toc-list a.active {{ font-weight: 600; }}
  .toc-num {{
    color: var(--wiki-muted); margin-right: 4px;
    font-variant-numeric: tabular-nums; font-size: 10.5px;
  }}

  /* ── 主内容 ── */
  .main {{
    min-width: 0; max-width: var(--content-max);
    width: 100%;
    box-sizing: border-box;
    overflow-x: hidden;
    background: var(--wiki-surface);
    border: 1px solid var(--wiki-border-soft);
    border-radius: 2px;
    padding: 18px 22px 28px;
  }}
  .report-header {{
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--wiki-border);
  }}
  .report-header h1 {{
    font-size: 20px; font-weight: 500; line-height: 1.35;
    margin-bottom: 6px; letter-spacing: 0;
    overflow-wrap: anywhere;
  }}
  .report-meta {{
    font-size: 11.5px; color: var(--wiki-muted);
    display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  }}
  .report-meta .dot {{ opacity: .55; }}

  .report-body {{
    font-size: 13px; line-height: 1.65;
    max-width: 100%;
    overflow-x: auto;
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .report-body h2 {{
    font-size: 16px; font-weight: 500;
    margin: 1.25em 0 0.45em;
    padding-bottom: 0.12em;
    border-bottom: 1px solid var(--wiki-border);
    scroll-margin-top: 68px;
  }}
  .report-body h3 {{
    font-size: 14px; font-weight: 600;
    margin: 1em 0 0.35em;
    scroll-margin-top: 68px;
  }}
  .report-body h4 {{
    font-size: 13px; font-weight: 600; margin: 0.9em 0 0.3em;
  }}
  .report-body p {{ margin: 0.55em 0; }}
  .report-body ul, .report-body ol {{ margin: 0.45em 0; padding-left: 1.5em; }}
  .report-body li {{ margin: 0.15em 0; }}
  .report-body a {{
    color: var(--wiki-link); text-decoration: none;
    word-break: break-all;
  }}
  .report-body a:hover {{ text-decoration: underline; color: var(--wiki-link-hover); }}
  .report-body blockquote {{
    margin: 0.75em 0; padding: 0.15em 0 0.15em 0.9em;
    border-left: 3px solid var(--wiki-border-soft);
    color: var(--wiki-muted); font-size: 12.5px;
  }}
  .report-body code {{
    font-family: inherit;
    font-size: 12px; background: #eaecf0; padding: 1px 4px; border-radius: 2px;
    word-break: break-all;
  }}
  .report-body pre {{
    margin: 0.7em 0; padding: 10px 12px; overflow-x: auto;
    max-width: 100%; box-sizing: border-box;
    background: #f8f9fa; border: 1px solid var(--wiki-border-soft);
    font-size: 12px; font-family: inherit;
  }}
  .report-body pre code {{ background: none; padding: 0; }}
  .report-body table {{
    width: 100%; max-width: 100%;
    border-collapse: collapse; margin: 0.75em 0;
    font-size: 12px; table-layout: fixed;
  }}
  .report-body th, .report-body td {{
    border: 1px solid var(--wiki-border-soft);
    padding: 6px 8px; vertical-align: top;
    overflow-wrap: anywhere; word-break: break-word;
  }}
  .report-body th {{
    background: #eaecf0; font-weight: 600; text-align: left;
  }}
  .report-body tr:nth-child(even) td {{ background: #f8f9fa; }}
  .report-body img, .report-body svg, .report-body video {{
    max-width: 100%; height: auto;
  }}
  .report-body hr {{
    margin: 1.2em 0; border: none; border-top: 1px solid var(--wiki-border);
  }}
  .report-body strong {{ font-weight: 600; }}

  .report-footer {{
    margin-top: 1.8em; padding-top: 0.85em;
    border-top: 1px solid var(--wiki-border);
    font-size: 11.5px; color: var(--wiki-muted); line-height: 1.6;
  }}

  .summary-card {{
    margin: 0 0 16px;
    padding: 14px 16px;
    border: 1px solid var(--wiki-border-soft);
    border-radius: 8px;
    background: linear-gradient(180deg, #f4f8ff 0%, #ffffff 72%);
    max-width: 100%;
    box-sizing: border-box;
    overflow-wrap: anywhere;
  }}
  .summary-card-badge {{
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11px; font-weight: 600; color: var(--wiki-accent);
    margin-bottom: 8px;
  }}
  .summary-card-tags {{
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;
  }}
  .summary-card-tags span {{
    font-size: 11px; color: var(--wiki-muted);
    background: #eaecf0; border-radius: 4px; padding: 2px 8px;
  }}
  .summary-card-sentence {{
    font-size: 14px; font-weight: 600; line-height: 1.65; color: var(--wiki-text);
  }}

  @media (max-width: 820px) {{
    .page {{ grid-template-columns: 1fr; padding: 12px 10px 48px; }}
    .toc-panel {{ position: relative; top: 0; max-height: none; }}
    .main {{ padding: 14px 12px 22px; }}
    .report-header h1 {{ font-size: 18px; }}
  }}
</style>
</head>
<body>
  <header class="brand-bar">
    <a class="brand-mark" href="{cta_url}" title="本析">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none">
        <path transform="rotate(20 50 50)" d="M 79.91 50.00 L 79.90 50.31 L 79.85 50.63 L 79.76 50.94 L 79.65 51.24 L 79.50 51.55 L 79.32 51.84 L 79.11 52.14 L 78.87 52.42 L 78.60 52.70 L 78.29 52.97 L 77.96 53.23 L 77.59 53.49 L 77.20 53.73 L 76.77 53.95 L 76.32 54.17 L 75.84 54.37 L 75.34 54.56 L 74.81 54.73 L 74.25 54.89 L 73.67 55.03 L 73.07 55.16 L 72.44 55.26 L 71.79 55.35 L 71.12 55.42 L 70.43 55.47 L 69.72 55.51 L 69.00 55.52 L 68.25 55.51 L 67.49 55.48 L 66.72 55.43 L 65.93 55.36 L 65.14 55.27 L 64.33 55.16 L 63.51 55.02 L 62.68 54.87 L 61.84 54.69 L 61.00 54.49 L 60.15 54.27 L 59.30 54.02 L 58.44 53.76 L 57.59 53.47 L 56.73 53.17 L 55.87 52.84 L 55.02 52.49 L 54.17 52.12 L 53.32 51.74 L 52.48 51.33 L 51.65 50.90 L 50.82 50.46 L 50.00 50.00 L 49.19 49.52 L 48.39 49.03 L 47.61 48.52 L 46.83 47.99 L 46.08 47.45 L 45.33 46.90 L 44.60 46.33 L 43.89 45.75 L 43.20 45.17 L 42.52 44.57 L 41.87 43.96 L 41.23 43.34 L 40.61 42.72 L 40.02 42.09 L 39.45 41.45 L 38.90 40.81 L 38.37 40.17 L 37.87 39.53 L 37.39 38.88 L 36.93 38.24 L 36.51 37.59 L 36.10 36.95 L 35.72 36.31 L 35.37 35.67 L 35.04 35.04 L 34.74 34.42 L 34.47 33.81 L 34.22 33.20 L 34.00 32.60 L 33.81 32.02 L 33.64 31.44 L 33.50 30.88 L 33.38 30.34 L 33.29 29.80 L 33.23 29.29 L 33.19 28.79 L 33.17 28.31 L 33.19 27.85 L 33.22 27.41 L 33.28 26.99 L 33.36 26.59 L 33.47 26.21 L 33.59 25.86 L 33.74 25.53 L 33.91 25.22 L 34.10 24.94 L 34.31 24.69 L 34.54 24.47 L 34.78 24.27 L 35.04 24.10 L 35.32 23.95 L 35.62 23.84 L 35.93 23.76 L 36.25 23.70 L 36.59 23.68 L 36.94 23.68 L 37.30 23.72 L 37.66 23.79 L 38.04 23.88 L 38.43 24.01 L 38.82 24.17 L 39.22 24.36 L 39.63 24.58 L 40.04 24.84 L 40.45 25.12 L 40.86 25.43 L 41.28 25.78 L 41.69 26.15 L 42.11 26.55 L 42.52 26.99 L 42.93 27.45 L 43.34 27.94 L 43.74 28.45 L 44.14 29.00 L 44.53 29.57 L 44.91 30.17 L 45.28 30.79 L 45.65 31.44 L 46.00 32.11 L 46.34 32.80 L 46.68 33.52 L 47.00 34.26 L 47.30 35.01 L 47.60 35.79 L 47.88 36.59 L 48.14 37.40 L 48.39 38.23 L 48.62 39.08 L 48.84 39.94 L 49.03 40.81 L 49.21 41.69 L 49.38 42.59 L 49.52 43.49 L 49.65 44.41 L 49.76 45.33 L 49.84 46.25 L 49.91 47.19 L 49.96 48.12 L 49.99 49.06 L 50.00 50.00 Z" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>本析</span>
    </a>
    <span class="brand-sub">研究报告 · 维基阅读</span>
  </header>

  <div class="page">
    <aside class="toc-panel">
      <div class="toc-box">
        <div class="toc-title">目录</div>
        <ul class="toc-list" id="toc-list"></ul>
      </div>
    </aside>

    <main class="main">
      <header class="report-header">
        <h1>{title}</h1>
        <div class="report-meta">
          <span>生成完成</span><span class="dot">·</span>
          <span>{date_str}</span><span class="dot">·</span>
          <span>耗时 {duration_str}</span><span class="dot">·</span>
          <span>阅读 {view_count} 次</span>
        </div>
      </header>

      {summary_card_html}

      <article class="report-body" id="report-body">
{body_html}
      </article>

      <footer class="report-footer">
        <p><strong>免责声明</strong>：本报告为研究性质的分析，<strong>不构成任何投资建议</strong>。
        不提供买入/卖出/持有指令、目标价、止盈止损位或收益承诺。市场有风险，决策需谨慎。</p>
      </footer>
    </main>
  </div>

<script>
(function() {{
  document.body.id = 'top';
  var body = document.getElementById('report-body');
  var list = document.getElementById('toc-list');
  if (!body || !list) return;

  var headings = body.querySelectorAll('h2, h3');
  if (!headings.length) return;

  var counters = [0, 0];
  headings.forEach(function(h, idx) {{
    var isH2 = h.tagName === 'H2';
    if (isH2) {{ counters[0]++; counters[1] = 0; }}
    else {{ counters[1]++; }}
    var num = isH2 ? String(counters[0]) : (counters[0] + '.' + counters[1]);
    var id = h.id || ('sec-' + idx);
    h.id = id;
    var text = (h.textContent || '').trim()
      .replace(/^\\d+[\\.\\s]*/, '')
      .replace(/^第\\s*\\d+\\s*[轮步]\\s*[｜|]\\s*/, '');

    var li = document.createElement('li');
    var a = document.createElement('a');
    a.href = '#' + id;
    a.className = isH2 ? 'level-2' : 'level-3';
    a.innerHTML = '<span class="toc-num">' + num + '</span><span>' + text + '</span>';
    li.appendChild(a);
    list.appendChild(li);
  }});

  var links = list.querySelectorAll('a');
  function updateActive() {{
    var y = window.scrollY;
    var active = -1;
    headings.forEach(function(h, i) {{
      if (h.offsetTop <= y + 100) active = i;
    }});
    links.forEach(function(link, i) {{
      link.classList.toggle('active', i === active);
    }});
  }}
  updateActive();
  window.addEventListener('scroll', updateActive, {{ passive: true }});
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


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    mins, secs = divmod(total, 60)
    if mins >= 60:
        hours, mins = divmod(mins, 60)
        return f"{hours}小时{mins}分"
    if mins > 0:
        return f"{mins}分{secs}秒"
    return f"{secs}秒"


def _format_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    try:
        if dt.tzinfo is not None:
            local = dt.astimezone()
            return local.strftime("%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


def _duration_seconds(created_at: datetime | None, completed_at: datetime | None) -> float | None:
    """计算报告耗时，兼容旧数据 naive 本地时间与 UTC timestamptz 混用。"""
    if not created_at or not completed_at:
        return None
    try:
        start = created_at
        end = completed_at
        if start.tzinfo is None and end.tzinfo is not None:
            start = start.replace(tzinfo=timezone.utc)
        elif end.tzinfo is None and start.tzinfo is not None:
            end = end.replace(tzinfo=timezone.utc)
        elif start.tzinfo is None and end.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
            end = end.replace(tzinfo=timezone.utc)

        secs = (end - start).total_seconds()
        # 旧 bug：completed_at=naive 本地钟面、created_at=UTC → 常多出约 8 小时
        if secs > 5 * 3600:
            adjusted = secs - _CN_OFFSET.total_seconds()
            if 20 < adjusted < 3 * 3600:
                secs = adjusted
        if secs < 0:
            return None
        return secs
    except Exception:
        return None


def _shorten_sentence(text: str, max_len: int = 48) -> str:
    s = re.sub(r"\s+", " ", _strip_inline_markdown(text or "").strip())
    if not s:
        return ""
    clause = re.split(r"[。！？；\n]", s)[0].strip() or s
    cut = re.split(r"[，、：:]", clause)[0].strip() or clause
    base = cut if len(cut) >= 8 else clause
    if len(base) <= max_len:
        return base
    return base[:max_len].rstrip("，、：:. ") + "…"


def _strip_inline_markdown(text: str) -> str:
    """纯文本摘要去掉行内 Markdown，避免露出 **加粗** 等标记。"""
    s = str(text or "")
    s = re.sub(r"!\[[^\]]*]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"_([^_]+)_", r"\1", s)
    s = re.sub(r"~~([^~]+)~~", r"\1", s)
    s = re.sub(r"^\s{0,3}#{1,6}\s+", "", s, flags=re.M)
    return re.sub(r"\s+", " ", s).strip()


def _extract_conclusion_card(body_md: str) -> tuple[str, str]:
    """从正文抽出「先看结论」做摘要卡片，并去掉正文中重复的该节标题块。"""
    text = (body_md or "").strip()
    if not text:
        return "", text

    m = re.search(
        r"(?:^|\n)##\s*先看结论\s*\n+([\s\S]*?)(?=\n##\s+|\Z)",
        text,
    )
    if not m:
        return "", text

    block = m.group(1).strip()
    # 去掉块内再次出现的同名标题
    block = re.sub(r"^#{1,3}\s*先看结论\s*\n+", "", block, flags=re.IGNORECASE).strip()
    if re.search(r"最终研究报告结论将在|结论将在.*生成|正在生成 AI", block):
        return "", text

    sentence = ""
    tags: list[str] = []
    for line in block.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        bullet = re.match(r"^[-*•]\s*(.+)$", s)
        item_raw = bullet.group(1).strip() if bullet else re.sub(r"^>\s*", "", s).strip()
        item = _strip_inline_markdown(item_raw)
        if not item:
            continue
        for label in ("价值线索", "风险压力", "跟踪优先级", "履约缺口", "配额盈余", "结转风险"):
            if label in item and label not in tags:
                tags.append(label)
        if bullet and re.match(r"^三条要点", item):
            continue
        if not sentence and len(item) >= 10 and not item.startswith("|"):
            sentence = item

    if not sentence:
        return "", text

    carbonish = bool(
        re.search(
            r"履约|碳配额|碳市场|CEA|CCER|结转|控排|核查排放",
            f"{sentence}\n{text[:800]}",
        )
    )
    # 避免「履约无缺口」误打成「履约缺口」标签
    refined: list[str] = []
    for label in tags:
        if label == "履约缺口" and re.search(r"无缺口|无履约缺口|不存在缺口", sentence):
            continue
        if label not in refined:
            refined.append(label)
    if not refined:
        if re.search(r"配额盈余|无缺口|盈余企业", sentence):
            refined = ["配额盈余", "策略建议", "结转风险"] if carbonish else [
                "价值线索",
                "风险压力",
                "跟踪优先级",
            ]
        elif carbonish:
            refined = ["履约缺口", "策略建议", "分析预警"]
        else:
            refined = ["价值线索", "风险压力", "跟踪优先级"]
    tag_html = "".join(f"<span>{html_lib.escape(t)}</span>" for t in refined)
    # 只展示完整结论一次，不再用截断标题重复一遍
    card = (
        '<section class="summary-card">'
        '<div class="summary-card-badge">报告摘要</div>'
        f'<div class="summary-card-tags">{tag_html}</div>'
        f'<div class="summary-card-sentence">{html_lib.escape(sentence)}</div>'
        "</section>"
    )

    # 正文保留「先看结论」章节，但去掉块内重复的二级标题行
    cleaned_block = re.sub(
        r"(##\s*先看结论\s*\n+)(?:#{1,3}\s*先看结论\s*\n+)+",
        r"\1",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    return card, cleaned_block


def render_report_html(
    content: str,
    *,
    title: str | None = None,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
    view_count: int = 0,
    cta_url: str = "/ai/login",
) -> str:
    """将报告 Markdown 渲染为维基风格 HTML 页面。"""
    _MD.reset()

    resolved_title = title or "理财研究报告"
    lines = content.split("\n")
    for line in lines[:12]:
        stripped = line.strip()
        if stripped.startswith("# "):
            resolved_title = stripped.lstrip("#").strip()
            break

    body_md_lines: list[str] = []
    skip_header = True
    for line in lines:
        stripped = line.strip()
        if skip_header:
            if stripped.startswith("## "):
                skip_header = False
            elif stripped.startswith("---"):
                continue
            else:
                continue
        body_md_lines.append(line)

    body_md = "\n".join(body_md_lines).strip()
    body_md = re.sub(r"<!--.*?-->", "", body_md, flags=re.DOTALL).strip()
    summary_card_html, body_md = _extract_conclusion_card(body_md)
    body_html = _MD.convert(body_md)

    duration_secs = _duration_seconds(created_at, completed_at)
    login_url = (cta_url or "/ai/login").strip() or "/ai/login"

    return REPORT_HTML_TEMPLATE.format(
        title=html_lib.escape(resolved_title),
        date_str=html_lib.escape(_format_dt(completed_at or created_at)),
        duration_str=html_lib.escape(_format_duration(duration_secs)),
        view_count=max(0, int(view_count or 0)),
        summary_card_html=summary_card_html,
        body_html=body_html,
        cta_url=html_lib.escape(login_url, quote=True),
    )
