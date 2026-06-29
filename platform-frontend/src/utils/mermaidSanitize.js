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

function containsCjk(text) {
  return /[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(String(text || ""));
}

function needsLabelQuotes(text) {
  const t = String(text || "").trim();
  if (!t || isQuoted(t)) return false;
  if (containsCjk(t)) return true;
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
    const participantMatch = line.match(/^(\s*participant\s+)(\S+)(?:\s+as\s+)(.+)$/i);
    if (participantMatch && needsLabelQuotes(participantMatch[3])) {
      return `${participantMatch[1]}${participantMatch[2]} as ${quoteMermaidText(participantMatch[3].trim())}`;
    }
    const participantOnly = line.match(/^(\s*participant\s+)(.+)$/i);
    if (participantOnly && needsLabelQuotes(participantOnly[2].trim())) {
      const name = participantOnly[2].trim();
      return `${participantOnly[1]}${quoteMermaidText(name)} as ${quoteMermaidText(name)}`;
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

/** 流程图箭头（长匹配优先，避免把 C1 <--> C2 误拆成 C1 < + -->） */
const FLOWCHART_ARROW_RE =
  /<--->|<-->|---->|---|-\.->|==>|--x|-x|-->/;

const FLOWCHART_EDGE_LINE_RE = new RegExp(
  `^(\\s*)(.+?)\\s*(${FLOWCHART_ARROW_RE.source})\\s*(?:\\|([^|]*?)\\|)?\\s*(.+?)\\s*$`
);

function unwrapQuotedFlowchartNode(line) {
  const indent = line.match(/^(\s*)/)?.[1] || "";
  const trimmed = line.trim();
  if (!isQuoted(trimmed)) return line;

  const inner = trimmed.slice(1, -1).replace(/\\"/g, '"').trim();
  const nodeMatch = inner.match(/^(\w+)\s*\[((?:[^\]\\]|\\.)*)\]\s*$/);
  if (!nodeMatch) return line;

  const id = nodeMatch[1];
  let label = nodeMatch[2].trim();
  if (!isQuoted(label) && needsLabelQuotes(label)) {
    label = quoteMermaidText(label);
  }
  return `${indent}${id}[${label}]`;
}

function looksLikeFlowchartNodeDef(text) {
  const t = String(text || "").trim();
  return /^\w+\s*[\[\(\{<]/.test(t) || /^"[^"]+"\s*[\[\(\{<]/.test(t);
}

function replaceMermaidLineBreaks(source) {
  let depth = 0;
  let result = "";
  const s = String(source || "");
  for (let i = 0; i < s.length; i += 1) {
    const brMatch = s.slice(i).match(/^<br\s*\/?>/i);
    if (brMatch) {
      result += depth > 0 ? " " : "\n";
      i += brMatch[0].length - 1;
      continue;
    }
    const ch = s[i];
    if (ch === "[" || ch === "(" || ch === "{") depth += 1;
    else if (ch === "]" || ch === ")" || ch === "}") depth = Math.max(0, depth - 1);
    result += ch;
  }
  return result;
}

function preprocessMermaidSource(source) {
  const raw = String(source || "");
  const withMindmapCatalog = /^\s*mindmap\b/im.test(raw)
    ? expandMindmapPseudoCatalogSource(raw)
    : raw;
  return withMindmapCatalog
    .split("\n")
    .map((line) => unwrapQuotedFlowchartNode(line))
    .join("\n");
}

function sanitizeSubgraphLine(line) {
  const match = line.match(/^(\s*subgraph\s+)(.+?)\s*$/i);
  if (!match) return line;
  const prefix = match[1];
  const title = match[2].trim();
  if (!title || /\[/.test(title)) return line;
  if (isQuoted(title)) return line;
  if (/[^\w-]/.test(title)) {
    return `${prefix}${quoteMermaidText(title)}`;
  }
  return line;
}

function aggressiveNeedsQuotes(text) {
  const t = String(text || "").trim();
  if (!t || isQuoted(t)) return false;
  // Mermaid 11：非 ASCII 节点 ID 须用双引号，如 "虚拟电厂" --> "云平台"
  if (containsCjk(t)) return true;
  if (/[\(\)\[\]{}<>#@/\\&|\s]/.test(t)) return true;
  if (/(-->>|->>|<<->>|<<-->>|--x|-x|==>)/.test(t)) return true;
  return false;
}

/** 流程图节点 ID / 标签含中文或特殊字符时，Mermaid 11 常需引号 */
function quoteFlowchartNodeToken(token) {
  const raw = String(token || "").trim();
  if (!raw || isQuoted(raw)) return raw;
  const shapeMatch = raw.match(/^([^[\({<]+)([\[\({<]+)(.+)([\]\)}>]+)$/);
  if (shapeMatch) {
    const [, id, open, label, close] = shapeMatch;
    const inner = label.trim();
    const safeId = id.trim();
    const quotedInner = needsLabelQuotes(inner) ? quoteMermaidText(inner) : inner;
    if (aggressiveNeedsQuotes(safeId)) {
      return `${quoteMermaidText(safeId)}${open}${quotedInner}${close}`;
    }
    return `${safeId}${open}${quotedInner}${close}`;
  }
  if (aggressiveNeedsQuotes(raw)) {
    return quoteMermaidText(raw);
  }
  return raw;
}

function sanitizeFlowchartEdgeLine(line, aggressive = false) {
  const arrowMatch = line.match(FLOWCHART_EDGE_LINE_RE);
  if (!arrowMatch) return line;
  const [, indent, leftRaw, arrow, edgeLabel, rightRaw] = arrowMatch;
  const quoteEdge = (label) => {
    const text = String(label || "").trim();
    if (!text || isQuoted(text)) return text;
    if (aggressive || needsLabelQuotes(text)) return quoteMermaidText(text);
    return text;
  };
  const left = quoteFlowchartNodeToken(leftRaw.trim());
  const right = quoteFlowchartNodeToken(rightRaw.trim());
  const edge = edgeLabel != null ? `${arrow}|${quoteEdge(edgeLabel)}|` : arrow;
  return `${indent}${left} ${edge} ${right}`;
}

function sanitizeFlowchartLine(line, aggressive = false) {
  let out = unwrapQuotedFlowchartNode(line);
  out = sanitizeSubgraphLine(out);
  if (FLOWCHART_ARROW_RE.test(out)) {
    out = sanitizeFlowchartEdgeLine(out, aggressive);
  } else {
    const trimmed = out.trim();
    if (
      trimmed
      && !/^(flowchart|graph|subgraph|end|style|class|click|direction)\b/i.test(trimmed)
      && !looksLikeFlowchartNodeDef(trimmed)
      && (aggressive || containsCjk(trimmed))
      && needsLabelQuotes(trimmed)
    ) {
      const indent = out.match(/^(\s*)/)?.[1] || "";
      out = `${indent}${quoteMermaidText(trimmed)}`;
    }
  }
  out = out.replace(
    new RegExp(`(${FLOWCHART_ARROW_RE.source})\\|([^"|][^|]*?)\\|`, "g"),
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
      (match, inner) => {
        const text = inner.slice(1, -1);
        if (needsLabelQuotes(text)) return `[${quoteMermaidText(text)}]`;
        return match;
      }
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
      if (needsLabelQuotes(text)) {
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

function parseMindmapBracketList(inner) {
  const items = [];
  let current = "";
  let inQuote = false;
  const s = String(inner || "");
  for (let i = 0; i < s.length; i += 1) {
    const ch = s[i];
    if (ch === '"' && s[i - 1] !== "\\") {
      inQuote = !inQuote;
      continue;
    }
    if (ch === "," && !inQuote) {
      const item = current.trim().replace(/^["']|["']$/g, "");
      if (item) items.push(item);
      current = "";
      continue;
    }
    current += ch;
  }
  const last = current.trim().replace(/^["']|["']$/g, "");
  if (last) items.push(last);
  return items;
}

/** LLM 常把 mindmap 子节点写成 "分类"：["项1", "项2"]，须展开为层级缩进 */
function expandMindmapPseudoCatalogLine(line) {
  const indent = line.match(/^(\s*)/)?.[1] || "";
  const trimmed = line.trim();
  if (!trimmed || /^mindmap\b/i.test(trimmed)) return [line];

  let content = trimmed;
  if (isQuoted(content)) {
    content = content.slice(1, -1).replace(/\\"/g, '"');
  }

  const catalogMatch = content.match(
    /^(?:"([^"]+)"|([^\s：:\[]+?))\s*[：:]\s*\[(.+)\]\s*$/
  );
  if (!catalogMatch) return [line];

  const label = (catalogMatch[1] || catalogMatch[2] || "").trim();
  const items = parseMindmapBracketList(catalogMatch[3]);
  if (!label || items.length === 0) return [line];

  const childIndent = `${indent}  `;
  const labelOut = needsLabelQuotes(label) ? quoteMermaidText(label) : label;
  const result = [`${indent}${labelOut}`];
  for (const item of items) {
    const text = item.trim();
    if (!text) continue;
    result.push(`${childIndent}${needsLabelQuotes(text) ? quoteMermaidText(text) : text}`);
  }
  return result;
}

function expandMindmapPseudoCatalogSource(source) {
  return String(source || "")
    .split("\n")
    .flatMap((line) => expandMindmapPseudoCatalogLine(line))
    .join("\n");
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
  if ((aggressive || containsCjk(trimmed)) && needsLabelQuotes(trimmed)) {
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
  return replaceMermaidLineBreaks(String(source || ""))
    .replace(/^\uFEFF/, "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/\r\n/g, "\n")
    .replace(/[\u201C\u201D\u201E\u201F\u2033\u2036\uFF02]/g, '"')
    .replace(/[\u2018\u2019\u201A\u201B\u2032\uFF07]/g, "'")
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
  let normalized = normalizeMermaidTypography(preprocessMermaidSource(source));
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
  const flowchart = base.replace(/^graph\b/im, "flowchart");
  const attempts = [
    sanitizeMermaidSource(base),
    sanitizeMermaidSource(base, { aggressive: true }),
    sanitizeMermaidSource(flowchart),
    sanitizeMermaidSource(flowchart, { aggressive: true }),
  ];
  return [...new Set(attempts.filter(Boolean))];
}
