/** Mermaid 按需加载与 SVG 渲染 */

let mermaidSeq = 0;
let mermaidLoader = null;

function normalizeMermaidSource(source) {
  return String(source || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .trim();
}

async function loadMermaid() {
  if (!mermaidLoader) {
    mermaidLoader = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: document.documentElement.dataset.theme === "dark" ? "dark" : "default",
        securityLevel: "antiscript",
        fontFamily: "var(--platform-font)",
      });
      return mod.default;
    });
  }
  return mermaidLoader;
}

export async function renderMermaidSvg(source) {
  const mermaid = await loadMermaid();
  const renderId = `md-mermaid-render-${mermaidSeq++}`;
  const { svg } = await mermaid.render(renderId, normalizeMermaidSource(source));
  return svg;
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
      source = normalizeMermaidSource(decodeURIComponent(encoded));
    } catch {
      continue;
    }
    const renderId = `md-mermaid-render-${mermaidSeq++}`;
    try {
      const { svg } = await mermaid.render(renderId, source);
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
