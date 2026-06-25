/** Mermaid 11.x 源码清洗：修复 LLM 常见语法陷阱 */

function isQuoted(text) {
  const t = String(text || "").trim();
  return (
    (t.startsWith('"') && t.endsWith('"')) ||
    (t.startsWith("'") && t.endsWith("'"))
  );
}

function quoteMermaidText(text) {
  return `"${String(text || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function needsLabelQuotes(text) {
  const t = String(text || "").trim();
  if (!t || isQuoted(t)) return false;
  if (/[\(\)\[\]{}<>#@/\\&|]/.test(t)) return true;
  if (/\s[\+\-]\s/.test(t)) return true;
  if (/(-->>|->>|<<->>|<<-->>|--x|-x|==>)/.test(t)) return true;
  return false;
}

/** 时序图消息中含 + / - / 箭头等时，Mermaid 11 易误判为激活符 */
function needsSequenceMessageQuotes(message, aggressive = false) {
  const msg = String(message || "").trim();
  if (!msg || isQuoted(msg)) return false;
  if (aggressive) return true;
  if (/\s[\+\-]\s/.test(msg)) return true;
  if (/\s[\+\-]$/.test(msg)) return true;
  if (/^[\+\-]\s/.test(msg)) return true;
  if (/(-->>|->>|<<->>|<<-->>|--x|-x)/.test(msg)) return true;
  return false;
}

function sanitizeSequenceLine(line, aggressive = false) {
  if (/^\s*(participant|activate|deactivate|loop|alt|else|opt|par|rect|end|title|autonumber|%%)/i.test(line)) {
    const participantMatch = line.match(/^(\s*participant\s+\S+\s+as\s+)(.+)$/i);
    if (participantMatch && needsLabelQuotes(participantMatch[2])) {
      return `${participantMatch[1]}${quoteMermaidText(participantMatch[2].trim())}`;
    }
    return line;
  }
  const colonIdx = line.indexOf(":");
  if (colonIdx < 0) return line;

  const head = line.slice(0, colonIdx);
  const message = line.slice(colonIdx + 1).trim();
  if (!message || isQuoted(message)) return line;

  const isNote = /^\s*Note\b/i.test(line);
  const hasArrow = /(-[->x)]|-->>|<<->>|<<-->>|->>|->)/.test(head);
  if (!hasArrow && !isNote) return line;

  if (!needsSequenceMessageQuotes(message, aggressive)) return line;
  return `${line.slice(0, colonIdx + 1)} ${quoteMermaidText(message)}`;
}

function sanitizeFlowchartLine(line, aggressive = false) {
  let out = line;
  out = out.replace(
    /(-->|---->|---|-\.->|==>|--x|-x)\|([^"|][^|]*?)\|/g,
    (_match, arrow, label) => {
      const text = label.trim();
      if (!text || isQuoted(text)) return `${arrow}|${label}|`;
      if (aggressive || needsLabelQuotes(text)) {
        return `${arrow}|${quoteMermaidText(text)}|`;
      }
      return `${arrow}|${label}|`;
    }
  );
  out = out.replace(
    /\|\s*([^"|][^|]*[()+\/\\&#|][^|]*?)\s*\|/g,
    (_match, label) => `|${quoteMermaidText(label.trim())}|`
  );
  if (aggressive) {
    out = out.replace(
      /(\[[^\]"']+\])/g,
      (match, inner) => `[${quoteMermaidText(inner.slice(1, -1))}]`
    );
    out = out.replace(
      /(\([^\)"']+\))/g,
      (match, inner) => {
        if (/^\([^)]*\)$/.test(match) && !match.startsWith("([")) {
          return `(${quoteMermaidText(inner.slice(1, -1))})`;
        }
        return match;
      }
    );
    return out;
  }
  out = out.replace(
    /(\[[^\]"']+[^\]"']*\])/g,
    (match, inner) => {
      const text = inner.slice(1, -1);
      if (/[\(\)\[\]<>#@/\\&|]/.test(text)) {
        return `[${quoteMermaidText(text)}]`;
      }
      return match;
    }
  );
  return out;
}

function sanitizeStateLine(line, aggressive = false) {
  const transition = line.match(/^(\s*.+?-->\s*.+?:\s*)(.+)$/);
  if (transition) {
    const label = transition[2].trim();
    if (label && (aggressive || needsLabelQuotes(label)) && !isQuoted(label)) {
      return `${transition[1]}${quoteMermaidText(label)}`;
    }
  }
  return line;
}

function sanitizeMindmapLine(line, aggressive = false) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("%%") || /^mindmap\b/i.test(trimmed)) {
    return line;
  }
  const indent = line.match(/^(\s*)/)?.[1] || "";
  if (/^\w+\(\(.+\)\)/.test(trimmed)) {
    const rootMatch = trimmed.match(/^(\w+\(\()(.+)(\)\))$/);
    if (rootMatch && needsLabelQuotes(rootMatch[2])) {
      return `${indent}${rootMatch[1]}${quoteMermaidText(rootMatch[2])}${rootMatch[3]}`;
    }
    return line;
  }
  if (aggressive && needsLabelQuotes(trimmed)) {
    return `${indent}${quoteMermaidText(trimmed)}`;
  }
  return line;
}

function sanitizeGanttLine(line) {
  const task = line.match(/^(\s*.+?\s*:\s*\w+\s*,\s*)(.+)$/);
  if (!task) return line;
  const tail = task[2].trim();
  if (tail && needsLabelQuotes(tail) && !isQuoted(tail)) {
    return `${task[1]}${quoteMermaidText(tail)}`;
  }
  return line;
}

function detectMermaidDiagramType(source) {
  for (const raw of String(source || "").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("%%")) continue;
    const head = line.split(/\s+/)[0]?.toLowerCase() || "";
    if (head === "flowchart" || head === "graph") return "flowchart";
    if (head === "sequencediagram") return "sequence";
    if (head === "statediagram-v2" || head === "statediagram") return "state";
    if (head === "mindmap") return "mindmap";
    if (head === "gantt") return "gantt";
    if (head === "classdiagram") return "class";
    if (head === "erdiagram") return "er";
    return head;
  }
  return "";
}

export function normalizeMermaidTypography(source) {
  return String(source || "")
    .replace(/^\uFEFF/, "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\r\n/g, "\n")
    .replace(/[""]/g, '"')
    .replace(/['']/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .trim();
}

function normalizeDiagramHeader(source) {
  const lines = String(source || "").split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const trimmed = lines[i].trim();
    if (!trimmed || trimmed.startsWith("%%")) continue;
    if (/^graph\b/i.test(trimmed) && !/^graph\s+[a-z]{2}\b/i.test(trimmed)) {
      lines[i] = trimmed.replace(/^graph\b/i, "flowchart");
    }
    if (/^sequencediagram\b/i.test(trimmed) && trimmed !== "sequenceDiagram") {
      lines[i] = trimmed.replace(/^sequencediagram\b/i, "sequenceDiagram");
    }
    if (/^statediagram\b/i.test(trimmed) && !/^statediagram-v2\b/i.test(trimmed)) {
      lines[i] = trimmed.replace(/^statediagram\b/i, "stateDiagram-v2");
    }
    break;
  }
  return lines.join("\n");
}

/**
 * 清洗 Mermaid 源码，降低 Mermaid 11 解析失败率。
 * @param {string} source
 * @param {{ aggressive?: boolean }} [options]
 * @returns {string}
 */
export function sanitizeMermaidSource(source, options = {}) {
  const aggressive = Boolean(options.aggressive);
  let normalized = normalizeMermaidTypography(source);
  if (!normalized) return "";
  normalized = normalizeDiagramHeader(normalized);

  const type = detectMermaidDiagramType(normalized);
  const lines = normalized.split("\n");

  if (type === "sequence") {
    return lines.map((line) => sanitizeSequenceLine(line, aggressive)).join("\n");
  }
  if (type === "flowchart") {
    return lines.map((line) => sanitizeFlowchartLine(line, aggressive)).join("\n");
  }
  if (type === "state") {
    return lines.map((line) => sanitizeStateLine(line, aggressive)).join("\n");
  }
  if (type === "mindmap") {
    return lines.map((line) => sanitizeMindmapLine(line, aggressive)).join("\n");
  }
  if (type === "gantt") {
    return lines.map(sanitizeGanttLine).join("\n");
  }
  return normalized;
}

/** 多轮渲染失败时的备选源码（逐步放宽修复力度） */
export function buildMermaidRenderAttempts(source) {
  const base = normalizeMermaidTypography(source);
  const attempts = [
    sanitizeMermaidSource(base),
    sanitizeMermaidSource(base, { aggressive: true }),
    sanitizeMermaidSource(base.replace(/^graph\b/im, "flowchart"), { aggressive: true }),
  ];
  return [...new Set(attempts.filter(Boolean))];
}
