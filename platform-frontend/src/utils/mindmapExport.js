/** 思维导图导出：Markdown 大纲与 OPML（XMind 可导入） */

import { buildMindmapFromAnswer } from "./knowledgeMindmap.js";

function stripCitationMarks(text) {
  return String(text || "")
    .replace(/\[\d+\]/g, "")
    .replace(/\*\*/g, "")
    .trim();
}

function sanitizeLabel(text, maxLen = 80) {
  const cleaned = stripCitationMarks(text)
    .replace(/[()[\]{}<>#;:"'|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "要点";
  return cleaned.length > maxLen ? `${cleaned.slice(0, maxLen - 1)}…` : cleaned;
}

function safeFilenameStem(title, fallback = "思维导图") {
  const stem = String(title || "")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .trim()
    .slice(0, 80);
  return stem || fallback;
}

function extractMermaidLabel(raw) {
  let label = String(raw || "").trim();
  const patterns = [
    /^root\(\((.+)\)\)$/i,
    /^\(\((.+)\)\)$/,
    /^\[(.+)\]$/,
    /^\((.+)\)$/,
    /^"(.+)"$/,
  ];
  for (const re of patterns) {
    const match = label.match(re);
    if (match) return sanitizeLabel(match[1]);
  }
  return sanitizeLabel(label.replace(/^root/i, "").trim() || label);
}

/**
 * 将 Mermaid mindmap 源码解析为树结构。
 * @returns {{ label: string, children: Array } | null}
 */
export function parseMermaidMindmapToTree(mermaidSource) {
  const lines = String(mermaidSource || "").split("\n");
  const contentLines = [];
  let started = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (!started) {
      if (/^mindmap\b/i.test(trimmed)) started = true;
      continue;
    }
    contentLines.push(line);
  }
  if (!contentLines.length) return null;

  const root = { label: "", children: [] };
  const stack = [{ depth: -1, node: root }];

  for (const line of contentLines) {
    const match = line.match(/^(\s*)(.+)$/);
    if (!match) continue;
    const depth = Math.floor(match[1].length / 2);
    const label = extractMermaidLabel(match[2]);
    if (!label) continue;

    while (stack.length > 1 && stack[stack.length - 1].depth >= depth) {
      stack.pop();
    }

    const parent = stack[stack.length - 1].node;
    if (!root.label && depth <= 1 && stack.length === 1) {
      root.label = label;
      stack.push({ depth, node: root });
      continue;
    }

    const node = { label, children: [] };
    parent.children.push(node);
    stack.push({ depth, node });
  }

  if (!root.label && root.children.length === 1) {
    return root.children[0];
  }
  if (!root.label && !root.children.length) return null;
  return root;
}

/**
 * 从报告/回答 Markdown 结构生成大纲树（与本地 mindmap 回退逻辑一致）。
 */
export function buildOutlineTreeFromAnswer(question, answer) {
  const root = { label: sanitizeLabel(question, 80) || "思维导图", children: [] };
  const body = stripCitationMarks(answer);
  let lastHeaderDepth = 0;
  const stack = [{ depth: 0, node: root }];

  function appendNode(depth, label) {
    while (stack.length > 1 && stack[stack.length - 1].depth >= depth) {
      stack.pop();
    }
    const node = { label, children: [] };
    stack[stack.length - 1].node.children.push(node);
    stack.push({ depth, node });
    return node;
  }

  for (const rawLine of body.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;

    const header = line.match(/^(#{1,4})\s+(.+)/);
    if (header) {
      const depth = header[1].length;
      lastHeaderDepth = depth;
      appendNode(depth, sanitizeLabel(header[2]));
      continue;
    }

    const bullet = line.match(/^[-*+]\s+(.+)/);
    if (bullet) {
      appendNode(lastHeaderDepth + 1, sanitizeLabel(bullet[1]));
      continue;
    }

    const numbered = line.match(/^\d+[.)]\s+(.+)/);
    if (numbered) {
      appendNode(lastHeaderDepth + 1, sanitizeLabel(numbered[1]));
    }
  }

  if (root.children.length === 0) {
    const sentences = body
      .split(/[。！？\n]+/)
      .map((s) => sanitizeLabel(s, 60))
      .filter((s) => s.length > 4)
      .slice(0, 8);
    for (const sentence of sentences) {
      root.children.push({ label: sentence, children: [] });
    }
  }

  return root;
}

function resolveOutlineTree({ mermaid, question, answer }) {
  const fromMermaid = parseMermaidMindmapToTree(mermaid);
  if (fromMermaid?.label || fromMermaid?.children?.length) {
    return fromMermaid;
  }
  const fromAnswer = buildOutlineTreeFromAnswer(question, answer);
  if (fromAnswer?.label || fromAnswer?.children?.length) {
    return fromAnswer;
  }
  const fallbackMermaid = buildMindmapFromAnswer(question, answer);
  return parseMermaidMindmapToTree(fallbackMermaid);
}

export function outlineTreeToMarkdown(tree, title) {
  const docTitle = sanitizeLabel(title || tree?.label || "思维导图", 80);
  const lines = [`# ${docTitle}`, ""];

  function walk(node, headingLevel, isRoot) {
    if (!isRoot) {
      const level = Math.min(Math.max(headingLevel, 2), 6);
      lines.push(`${"#".repeat(level)} ${node.label}`);
      lines.push("");
    }
    for (const child of node.children || []) {
      walk(child, isRoot ? 2 : headingLevel + 1, false);
    }
  }

  walk(tree, 1, true);
  return `${lines.join("\n").trim()}\n`;
}

function escapeXml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function outlineNodeToOpml(node, indent = 4) {
  const pad = " ".repeat(indent);
  const text = escapeXml(node.label);
  if (!node.children?.length) {
    return `${pad}<outline text="${text}"/>`;
  }
  const children = node.children.map((child) => outlineNodeToOpml(child, indent + 2)).join("\n");
  return `${pad}<outline text="${text}">\n${children}\n${pad}</outline>`;
}

export function outlineTreeToOpml(tree, title) {
  const docTitle = escapeXml(title || tree?.label || "思维导图");
  const body = outlineNodeToOpml(tree, 4);
  return `<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>${docTitle}</title>
  </head>
  <body>
${body}
  </body>
</opml>
`;
}

export function downloadTextFile(content, filename) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function exportMindmapMarkdown({ mermaid, question, answer, title }) {
  const tree = resolveOutlineTree({ mermaid, question, answer });
  if (!tree) throw new Error("暂无思维导图可导出");
  const markdown = outlineTreeToMarkdown(tree, title);
  const name = `${safeFilenameStem(title)}_思维导图.md`;
  downloadTextFile(markdown, name);
}

export function exportMindmapOpml({ mermaid, question, answer, title }) {
  const tree = resolveOutlineTree({ mermaid, question, answer });
  if (!tree) throw new Error("暂无思维导图可导出");
  const opml = outlineTreeToOpml(tree, title);
  const name = `${safeFilenameStem(title)}_思维导图.opml`;
  downloadTextFile(opml, name);
}
