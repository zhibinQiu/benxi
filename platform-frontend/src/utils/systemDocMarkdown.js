import { ensureMarked, marked } from "./markdown.js";
import { unmountMermaidInElement } from "./mermaidRender.js";
import {
  bindEchartsResize,
  disposeEchartsInElement,
  mountRichMediaInElement,
  unbindEchartsResize,
} from "./richMarkdown.js";

let mermaidSeq = 0;
let mermaidRendererRegistered = false;

function ensureMermaidRenderer() {
  if (mermaidRendererRegistered) return;
  ensureMarked();
  marked.use({
    renderer: {
      code({ text, lang }) {
        const language = (lang || "").trim().toLowerCase();
        if (language === "mermaid") {
          const id = `md-mermaid-${mermaidSeq++}`;
          const encoded = encodeURIComponent(text || "");
          return (
            `<div class="md-mermaid-wrap">` +
            `<pre class="md-mermaid" id="${id}" data-mermaid="${encoded}"></pre>` +
            `</div>`
          );
        }
        return false;
      },
    },
  });
  mermaidRendererRegistered = true;
}

export function renderSystemDocMarkdown(text) {
  ensureMermaidRenderer();
  try {
    return marked.parse(String(text || ""));
  } catch {
    return `<p>${String(text || "")}</p>`;
  }
}

export { renderMermaidSvg } from "./mermaidRender.js";

export async function mountSystemDocContent(root) {
  if (!root) return;
  unmountMermaidInElement(root);
  await mountRichMediaInElement(root);
  bindEchartsResize();
}

export function disposeSystemDocContent(root) {
  if (!root) return;
  disposeEchartsInElement(root);
  unmountMermaidInElement(root);
}

export function unbindSystemDocContent() {
  unbindEchartsResize();
}

export function resolveDocLink(currentPath, href) {
  const raw = String(href || "").trim();
  if (!raw || raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("mailto:")) {
    return null;
  }
  if (raw.startsWith("/api/")) return null;
  const hashIdx = raw.indexOf("#");
  const filePart = hashIdx >= 0 ? raw.slice(0, hashIdx) : raw;
  const hash = hashIdx >= 0 ? raw.slice(hashIdx) : "";
  if (!filePart.endsWith(".md")) return null;

  if (filePart.startsWith("docs/") || filePart.startsWith("运维") || filePart.startsWith("RELEASE")) {
    return { path: filePart.replace(/^\.\//, ""), hash };
  }

  const baseParts = String(currentPath || "").split("/");
  baseParts.pop();
  const relParts = filePart.split("/");
  const out = [...baseParts];
  for (const part of relParts) {
    if (part === "..") out.pop();
    else if (part && part !== ".") out.push(part);
  }
  return { path: out.join("/"), hash };
}
