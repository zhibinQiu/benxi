import { renderMarkdown } from "./markdown";

/** 基础 HTML 消毒（订阅正文来自用户粘贴链接，仅剔除脚本与事件属性） */
export function sanitizeArticleHtml(html) {
  return String(html || "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
    .replace(/\son\w+\s*=\s*"[^"]*"/gi, "")
    .replace(/\son\w+\s*=\s*'[^']*'/gi, "")
    .trim();
}

/** 移除后端插入 content_html 的 AI 摘要块（摘要已由摘要卡片单独展示）。
 *  不用正则，直接用 DOM 定位 data-ai-summary="1" 的节点，最可靠。 */
function stripAiSummaryBlock(html) {
  if (!html || !html.includes("ai-summary")) return html;
  const div = document.createElement("div");
  div.innerHTML = html;
  const block = div.querySelector('[data-ai-summary="1"]');
  if (block) {
    // 移除紧随其后的 <hr class="subscription-ai-summary-divider" />
    let next = block.nextElementSibling;
    while (next) {
      const el = next;
      next = el.nextElementSibling;
      if (el.tagName === "HR" && el.classList.contains("subscription-ai-summary-divider")) {
        el.remove();
        break;
      }
    }
    block.remove();
  }
  return div.innerHTML;
}

function looksLikeHtml(text) {
  return /<[a-z][\s\S]*>/i.test(String(text || ""));
}

/**
 * 将纯文本按行拆分为 <p> 段落（支持单换行分段）。
 */
function textToParagraphs(text) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length > 1) {
    return lines.map((l) => `<p>${l}</p>`).join("");
  }
  return `<p>${text.replace(/\n/g, "<br>")}</p>`;
}

/**
 * 优先使用原始 HTML 排版（更接近网页）；无 HTML 时再回退 Markdown 渲染。
 * @param {{ content_html?: string, content_markdown?: string } | null | undefined} item
 * @returns {{ mode: 'html' | 'empty', body: string }}
 */
export function resolveArticleBody(item) {
  const sanitized = sanitizeArticleHtml(item?.content_html);
  const html = stripAiSummaryBlock(sanitized);
  if (html && looksLikeHtml(html)) {
    return { mode: "html", body: html };
  }

  const md = String(item?.content_markdown || "").trim();
  if (md) {
    const rendered = renderMarkdown(md);
    return { mode: "html", body: stripAiSummaryBlock(rendered) };
  }

  if (html) {
    const escaped = html
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return { mode: "html", body: textToParagraphs(escaped) };
  }

  return { mode: "empty", body: "" };
}
