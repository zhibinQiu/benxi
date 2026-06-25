/** 轻量 Markdown 渲染（不含 ECharts / Mermaid） */

import { marked } from "marked";
import DOMPurify from "dompurify";

let configured = false;

const SANITIZE_OPTS = {
  USE_PROFILES: { html: true },
  ADD_ATTR: [
    "data-mermaid",
    "data-option",
    "data-cite-index",
    "target",
    "rel",
    "style",
  ],
};

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

export function sanitizeRenderedHtml(html) {
  return DOMPurify.sanitize(String(html || ""), SANITIZE_OPTS);
}

/** 去掉模型外包的一层 ```markdown 围栏，避免整段被当作代码块。 */
const MERMAID_DIAGRAM_HEAD =
  /^(mindmap|flowchart(?:\s+[A-Za-z]{2,3})?|graph(?:\s+[A-Za-z]{2,3})?|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram|gantt|pie|journey|gitGraph|timeline|quadrantChart|C4Context)\b/i;

function isMermaidDiagramLine(line) {
  const trimmed = String(line || "").trim();
  if (!trimmed || trimmed.startsWith("%%")) return false;
  return MERMAID_DIAGRAM_HEAD.test(trimmed);
}

function diagramTypeFromLine(line) {
  const head = String(line || "").trim().split(/\s+/)[0] || "";
  return head.toLowerCase();
}

function isMermaidContinuationLine(line, diagramType) {
  const raw = String(line ?? "");
  const trimmed = raw.trim();
  if (!trimmed) return true;
  if (trimmed.startsWith("%%")) return true;
  if (/^\s+/.test(raw)) return true;

  const type = (diagramType || "").toLowerCase();
  if (type === "mindmap") return false;

  if (/^(subgraph\b|end\b|classDef\b|class\b|linkStyle\b|style\b)/i.test(trimmed)) return true;
  if (/^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-]*[\[\({<]/.test(trimmed)) return true;
  if (/^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-]*\s*(-->|----|---|-\.|==>|--x|-x)/.test(trimmed)) {
    return true;
  }
  if (/^(participant|actor|note|loop|alt|else|opt|par|rect)\b/i.test(trimmed)) return true;
  return false;
}

function upgradeUntaggedMermaidFences(text) {
  return String(text || "").replace(/```([^\n]*)\n([\s\S]*?)```/g, (full, info, body) => {
    const lang = String(info || "").trim().toLowerCase();
    if (lang === "mermaid") return full;
    if (lang && !["", "text", "txt", "plain"].includes(lang)) return full;
    const first = body
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line && !line.startsWith("%%"));
    if (first && isMermaidDiagramLine(first)) {
      return `\`\`\`mermaid\n${body.replace(/\s+$/, "")}\n\`\`\``;
    }
    return full;
  });
}

function fenceBareMermaidBlockLines(segment) {
  const lines = String(segment || "").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (isMermaidDiagramLine(line)) {
      const diagramType = diagramTypeFromLine(line);
      const block = [line];
      i += 1;
      while (i < lines.length) {
        const current = lines[i];
        if (current.trim() === "") {
          let j = i + 1;
          while (j < lines.length && lines[j].trim() === "") j += 1;
          if (j < lines.length && isMermaidContinuationLine(lines[j], diagramType)) {
            block.push(current);
            i += 1;
            continue;
          }
          break;
        }
        if (isMermaidContinuationLine(current, diagramType)) {
          block.push(current);
          i += 1;
          continue;
        }
        break;
      }
      out.push("```mermaid", ...block, "```");
      continue;
    }
    out.push(line);
    i += 1;
  }
  return out.join("\n");
}

function fenceBareMermaidInProse(text) {
  const source = String(text || "");
  const fenceRe = /```[\s\S]*?```/g;
  let lastIndex = 0;
  let result = "";
  let match;
  while ((match = fenceRe.exec(source)) !== null) {
    result += fenceBareMermaidBlockLines(source.slice(lastIndex, match.index));
    result += match[0];
    lastIndex = match.index + match[0].length;
  }
  result += fenceBareMermaidBlockLines(source.slice(lastIndex));
  return result;
}

export function normalizeMarkdownInput(text) {
  let raw = String(text || "").trim();
  const fenced = raw.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i);
  if (fenced) raw = fenced[1].trim();
  raw = upgradeUntaggedMermaidFences(raw);
  raw = fenceBareMermaidInProse(raw);
  return raw;
}

export function renderMarkdown(text) {
  const source = normalizeMarkdownInput(text);
  ensureMarked();
  try {
    return sanitizeRenderedHtml(marked.parse(source));
  } catch {
    return `<p>${escapeHtml(source)}</p>`;
  }
}

export { marked };
