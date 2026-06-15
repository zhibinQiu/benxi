/** 将知识检索回答转为 Mermaid mindmap（对齐 KnowFlow 结果思维导图） */

function stripCitationMarks(text) {
  return String(text || "")
    .replace(/\[\d+\]/g, "")
    .replace(/\*\*/g, "")
    .trim();
}

function sanitizeMindmapLabel(text, maxLen = 48) {
  const cleaned = stripCitationMarks(text)
    .replace(/[()[\]{}<>#;:"'|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "要点";
  return cleaned.length > maxLen ? `${cleaned.slice(0, maxLen - 1)}…` : cleaned;
}

function indent(depth) {
  return "  ".repeat(depth);
}

/**
 * 从 Markdown 回答结构生成 mindmap 源码（无 LLM 时的本地回退）。
 */
export function buildMindmapFromAnswer(question, answer) {
  const root = sanitizeMindmapLabel(question, 36);
  const body = stripCitationMarks(answer);
  const lines = ["mindmap", `${indent(1)}root((${root}))`];

  let currentDepth = 2;
  let lastHeaderDepth = 2;

  for (const rawLine of body.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;

    const header = line.match(/^(#{1,4})\s+(.+)/);
    if (header) {
      const level = header[1].length;
      const label = sanitizeMindmapLabel(header[2]);
      currentDepth = Math.min(level + 1, 4);
      lastHeaderDepth = currentDepth;
      lines.push(`${indent(currentDepth)}${label}`);
      continue;
    }

    const bullet = line.match(/^[-*+]\s+(.+)/);
    if (bullet) {
      const label = sanitizeMindmapLabel(bullet[1]);
      const depth = Math.min(lastHeaderDepth + 1, 5);
      lines.push(`${indent(depth)}${label}`);
      continue;
    }

    const numbered = line.match(/^\d+[.)]\s+(.+)/);
    if (numbered) {
      lines.push(`${indent(Math.min(lastHeaderDepth + 1, 5))}${sanitizeMindmapLabel(numbered[1])}`);
    }
  }

  if (lines.length <= 2) {
    const sentences = body
      .split(/[。！？\n]+/)
      .map((s) => sanitizeMindmapLabel(s, 40))
      .filter((s) => s.length > 4)
      .slice(0, 6);
    for (const sentence of sentences) {
      lines.push(`${indent(2)}${sentence}`);
    }
  }

  return lines.join("\n");
}
