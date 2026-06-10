import { marked } from "marked";
import {
  bindEchartsResize,
  mountEchartsInElement,
  disposeEchartsInElement,
  unbindEchartsResize,
} from "./richMarkdown";

marked.setOptions({ gfm: true, breaks: true });

let mermaidSeq = 0;
let mermaidLoader = null;

async function loadMermaid() {
  if (!mermaidLoader) {
    mermaidLoader = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: document.documentElement.dataset.theme === "dark" ? "dark" : "default",
        securityLevel: "strict",
        fontFamily: "var(--platform-font)",
      });
      return mod.default;
    });
  }
  return mermaidLoader;
}

const renderer = {
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
};

marked.use({ renderer });

export function renderSystemDocMarkdown(text) {
  try {
    return marked.parse(String(text || ""));
  } catch {
    return `<p>${String(text || "")}</p>`;
  }
}

export async function mountMermaidInElement(root) {
  if (!root?.querySelectorAll) return;
  const nodes = root.querySelectorAll(".md-mermaid[data-mermaid]");
  if (!nodes.length) return;
  const mermaid = await loadMermaid();
  for (const el of nodes) {
    const encoded = el.getAttribute("data-mermaid");
    if (!encoded) continue;
    let source = "";
    try {
      source = decodeURIComponent(encoded);
    } catch {
      continue;
    }
    const id = el.id || `md-mermaid-${mermaidSeq++}`;
    try {
      const { svg } = await mermaid.render(id, source);
      const wrap = el.closest(".md-mermaid-wrap") || el.parentElement;
      if (wrap) {
        wrap.innerHTML = `<div class="md-mermaid-svg" aria-hidden="true">${svg}</div>`;
      }
    } catch {
      el.textContent = source;
      el.classList.add("md-mermaid--error");
    }
  }
}

export async function mountSystemDocContent(root) {
  if (!root) return;
  mountEchartsInElement(root);
  bindEchartsResize();
  await mountMermaidInElement(root);
}

export function disposeSystemDocContent(root) {
  if (!root) return;
  disposeEchartsInElement(root);
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
