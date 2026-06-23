/** Mermaid 按需加载与 SVG 渲染（进入视口才 import mermaid 包） */

let mermaidSeq = 0;
let mermaidLoader = null;
let mermaidObserver = null;
const mermaidPending = new WeakSet();

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

function getMermaidObserver() {
  if (mermaidObserver || typeof IntersectionObserver === "undefined") return mermaidObserver;
  mermaidObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        mermaidObserver?.unobserve(entry.target);
        mermaidPending.delete(entry.target);
        void renderOneMermaidNode(entry.target);
      }
    },
    { rootMargin: "160px 0px", threshold: 0.01 }
  );
  return mermaidObserver;
}

function unobserveMermaidNode(el) {
  if (!el) return;
  mermaidPending.delete(el);
  mermaidObserver?.unobserve(el);
}

async function renderOneMermaidNode(el) {
  if (!el?.getAttribute || el.closest(".md-mermaid-svg")) return;
  const encoded = el.getAttribute("data-mermaid");
  if (!encoded) return;
  let source = "";
  try {
    source = normalizeMermaidSource(decodeURIComponent(encoded));
  } catch {
    return;
  }
  const mermaid = await loadMermaid();
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
  const observer = getMermaidObserver();
  for (const el of nodes) {
    if (el.closest(".md-mermaid-svg")) continue;
    if (observer) {
      if (!mermaidPending.has(el)) {
        mermaidPending.add(el);
        observer.observe(el);
      }
      continue;
    }
    await renderOneMermaidNode(el);
  }
}

/** 移除已渲染 Mermaid SVG，释放 DOM 内存（需重新执行 mountMermaidInElement 才能再显示） */
export function unmountMermaidInElement(root) {
  if (!root?.querySelectorAll) return;
  root.querySelectorAll(".md-mermaid[data-mermaid]").forEach((el) => unobserveMermaidNode(el));
  root.querySelectorAll(".md-mermaid-svg").forEach((el) => el.remove());
}
