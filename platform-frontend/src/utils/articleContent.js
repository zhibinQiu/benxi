import { renderRichMarkdown } from "./richMarkdown";

/** 基础 HTML 消毒（订阅正文来自用户粘贴链接，仅剔除脚本与事件属性） */
export function sanitizeArticleHtml(html) {
  return String(html || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
    .replace(/\son\w+\s*=\s*"[^"]*"/gi, "")
    .replace(/\son\w+\s*=\s*'[^']*'/gi, "")
    .trim();
}

function looksLikeHtml(text) {
  return /<[a-z][\s\S]*>/i.test(String(text || ""));
}

/**
 * 优先使用原始 HTML 排版（更接近网页）；无 HTML 时再回退 Markdown 渲染。
 * @param {{ content_html?: string, content_markdown?: string } | null | undefined} item
 * @returns {{ mode: 'html' | 'empty', body: string }}
 */
export function resolveArticleBody(item) {
  const html = sanitizeArticleHtml(item?.content_html);
  if (html && looksLikeHtml(html)) {
    return { mode: "html", body: html };
  }

  const md = String(item?.content_markdown || "").trim();
  if (md) {
    return { mode: "html", body: renderRichMarkdown(md) };
  }

  const plain = String(item?.content_html || "").trim();
  if (plain) {
    const escaped = plain
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const paras = escaped.split(/\n\s*\n+/).filter(Boolean);
    const body =
      paras.length > 1
        ? paras.map((p) => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("")
        : `<p>${escaped.replace(/\n/g, "<br>")}</p>`;
    return { mode: "html", body };
  }

  return { mode: "empty", body: "" };
}
