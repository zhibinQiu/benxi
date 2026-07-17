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

function looksLikeHtml(text) {
  return /<[a-z][\s\S]*>/i.test(String(text || ""));
}

/**
 * 如果 HTML 纯文本开头匹配 summary 文本，将其从 HTML DOM 中剥离，
 * 避免摘要卡片与正文内容之间出现文字重复。同时检查末尾。
 */
function stripLeadingSummaryFromHtml(html, summary) {
  if (!summary || !html) return html;
  const s = summary.trim();
  if (!s) return html;

  const div = document.createElement("div");
  div.innerHTML = html;
  const plainText = (div.textContent || "").trimStart();
  if (!plainText.startsWith(s)) {
    // 也尝试从末尾剥离（后端在薄内容时会把 summary 追加到 content_html 末尾）
    const plainTrimmed = (div.textContent || "").trimEnd();
    if (plainTrimmed.endsWith(s)) {
      let remaining = s;
      const walker = document.createTreeWalker(div, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (let i = nodes.length - 1; i >= 0 && remaining.length > 0; i--) {
        const node = nodes[i];
        const text = node.textContent || "";
        const trimmedText = text.trimEnd();

        if (trimmedText.endsWith(remaining)) {
          const trailingWs = text.length - trimmedText.length;
          node.textContent = text.slice(0, text.length - remaining.length - trailingWs);
          remaining = "";
        } else if (remaining.endsWith(trimmedText)) {
          remaining = remaining.slice(0, remaining.length - trimmedText.length);
          node.textContent = "";
        } else {
          let matchLen = 0;
          const maxLen = Math.min(text.length, remaining.length);
          while (matchLen < maxLen && text[text.length - 1 - matchLen] === remaining[remaining.length - 1 - matchLen]) matchLen++;
          if (matchLen > 0) {
            node.textContent = text.slice(0, text.length - matchLen);
            remaining = remaining.slice(0, remaining.length - matchLen);
          } else {
            break;
          }
        }
      }
    } else {
      return html;
    }
  } else {
    let remaining = s;
    const walker = document.createTreeWalker(div, NodeFilter.SHOW_TEXT);
    while (walker.nextNode() && remaining.length > 0) {
      const node = walker.currentNode;
      const text = node.textContent || "";
      const trimmedText = text.trimStart();

      if (trimmedText.startsWith(remaining)) {
        const leadingWs = text.length - trimmedText.length;
        node.textContent = text.slice(0, leadingWs) + trimmedText.slice(remaining.length);
        remaining = "";
      } else if (remaining.startsWith(trimmedText)) {
        remaining = remaining.slice(trimmedText.length);
        node.textContent = "";
      } else {
        let matchLen = 0;
        const maxLen = Math.min(text.length, remaining.length);
        while (matchLen < maxLen && text[matchLen] === remaining[matchLen]) matchLen++;
        if (matchLen > 0) {
          node.textContent = text.slice(matchLen);
          remaining = remaining.slice(matchLen);
        } else {
          break;
        }
      }
    }
  }

  let result = div.innerHTML;
  result = result.replace(/<(\w+)[^>]*>\s*<\/\1>/g, "");
  return result;
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
 * @param {{
 *   content_html?: string,
 *   content_markdown?: string
 * } | null | undefined} item
 * @param {string} [summary] 可选的摘要文本，用于从正文开头去重
 * @returns {{ mode: 'html' | 'empty', body: string }}
 */
export function resolveArticleBody(item, summary) {
  const html = sanitizeArticleHtml(item?.content_html);
  if (html && looksLikeHtml(html)) {
    const body = stripLeadingSummaryFromHtml(html, summary);
    return { mode: "html", body };
  }

  const md = String(item?.content_markdown || "").trim();
  if (md) {
    const body = stripLeadingSummaryFromHtml(renderMarkdown(md), summary);
    return { mode: "html", body };
  }

  const plain = String(item?.content_html || "").trim();
  if (plain) {
    const escaped = plain
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return { mode: "html", body: stripLeadingSummaryFromHtml(textToParagraphs(escaped), summary) };
  }

  return { mode: "empty", body: "" };
}
