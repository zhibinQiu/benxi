/** 轻量 Markdown 渲染（不含 ECharts / Mermaid） */

import { marked } from "marked";

let configured = false;

export function ensureMarked() {
  if (configured) return;
  marked.setOptions({ gfm: true, breaks: true });
  configured = true;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** 去掉模型外包的一层 ```markdown 围栏，避免整段被当作代码块。 */
export function normalizeMarkdownInput(text) {
  const raw = String(text || "").trim();
  const fenced = raw.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i);
  if (fenced) return fenced[1].trim();
  return raw;
}

export function renderMarkdown(text) {
  const source = normalizeMarkdownInput(text);
  ensureMarked();
  try {
    return marked.parse(source);
  } catch {
    return `<p>${escapeHtml(source)}</p>`;
  }
}

export { marked };
