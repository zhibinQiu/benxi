/** Mermaid 按需加载与 SVG 渲染（进入视口才 import mermaid 包） */

import {
  buildMermaidRenderAttempts,
  sanitizeMermaidSource,
} from "./mermaidSanitize.js";

let mermaidSeq = 0;
let mermaidLoader = null;
let mermaidObserver = null;
const mermaidPending = new WeakSet();
const mermaidRendering = new WeakSet();

function decodeMermaidAttr(encoded) {
  if (!encoded) return "";
  try {
    return decodeURIComponent(encoded);
  } catch {
    return "";
  }
}

/** 从 DOM 节点读取 Mermaid 源码（优先 data 属性，避免错误文案污染 textContent） */
export function readMermaidSourceFromElement(el, wrap = null) {
  const pre = el?.classList?.contains("md-mermaid") ? el : wrap?.querySelector?.(".md-mermaid");
  const hostWrap = wrap || pre?.closest?.(".md-mermaid-wrap");
  const fromWrap = decodeMermaidAttr(hostWrap?.getAttribute?.("data-mermaid-source"));
  if (fromWrap) return fromWrap;
  const fromAttr = decodeMermaidAttr(pre?.getAttribute?.("data-mermaid"));
  if (fromAttr) return fromAttr;
  const text = pre?.textContent?.trim();
  if (text && !pre?.classList?.contains("md-mermaid--error")) return text;
  return "";
}

function normalizeMermaidSource(source) {
  return sanitizeMermaidSource(source);
}

function formatMermaidRenderError(err) {
  const msg = String(err?.message || err || "").trim();
  if (/syntax error/i.test(msg)) {
    return "Mermaid 语法错误：消息或标签中含 +、-、箭头等字符时请用英文双引号包裹，例如 A->>B: \"done + reply\"";
  }
  if (/parse error/i.test(msg)) {
    return "Mermaid 解析失败：请检查节点 ID、箭头语法与中文标签是否已加引号";
  }
  return msg || "Mermaid 渲染失败";
}

/**
 * Mermaid 圆形 mindmap 节点（root((…))）在 htmlLabels=false 时标签仅垂直居中、
 * 文字仍左对齐，导致根节点文字偏右溢出。对未水平居中的 .label 补 text-anchor。
 */
function fixMindmapLabelAlignment(svg) {
  if (!svg || typeof document === "undefined" || !/mindmap-node/.test(svg)) {
    return svg;
  }

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:-10000px;top:0;visibility:hidden;pointer-events:none;";
  host.innerHTML = svg;
  document.body.appendChild(host);

  try {
    const svgEl = host.querySelector("svg");
    if (!svgEl) return svg;

    svgEl.querySelectorAll(".mindmap-node .label").forEach((labelGroup) => {
      const transform = labelGroup.getAttribute("transform") || "";
      const match = transform.match(/translate\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)/);
      if (!match || Math.abs(Number.parseFloat(match[1])) > 0.5) return;

      const textEl = labelGroup.querySelector("text");
      if (!textEl) return;

      textEl.setAttribute("text-anchor", "middle");
      textEl.querySelectorAll("tspan").forEach((tspan) => {
        tspan.setAttribute("text-anchor", "middle");
      });
    });

    return svgEl.outerHTML;
  } finally {
    host.remove();
  }
}

async function loadMermaid() {
  if (!mermaidLoader) {
    mermaidLoader = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: document.documentElement.dataset.theme === "dark" ? "dark" : "default",
        securityLevel: "antiscript",
        fontFamily: "sans-serif",
        htmlLabels: false,
        flowchart: { htmlLabels: false, useMaxWidth: true },
        sequence: { useMaxWidth: true },
        mindmap: { useMaxWidth: true },
        er: { useMaxWidth: true },
        class: { useMaxWidth: true },
      });
      return mod.default;
    });
  }
  return mermaidLoader;
}

function isElementNearViewport(el) {
  if (!el?.getBoundingClientRect) return true;
  const rect = el.getBoundingClientRect();
  const margin = 200;
  return rect.bottom >= -margin && rect.top <= window.innerHeight + margin;
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
    { rootMargin: "200px 0px", threshold: 0.01 }
  );
  return mermaidObserver;
}

function unobserveMermaidNode(el) {
  if (!el) return;
  mermaidPending.delete(el);
  mermaidObserver?.unobserve(el);
}

function ensureMermaidPlaceholder(wrap, source) {
  let pre = wrap.querySelector(".md-mermaid");
  if (!pre) {
    pre = document.createElement("pre");
    pre.className = "md-mermaid";
    wrap.prepend(pre);
  }
  if (!readMermaidSourceFromElement(pre) && source) {
    pre.textContent = source;
    pre.setAttribute("data-mermaid", encodeURIComponent(source));
  }
  return pre;
}

function showMermaidError(pre, source, message) {
  pre.setAttribute("data-mermaid", encodeURIComponent(source));
  pre.style.display = "";
  pre.textContent = `${message}\n\n${source}`;
  pre.classList.add("md-mermaid--error");
  pre.classList.remove("md-mermaid--loading");
}

async function renderMermaidAttempts(mermaid, source) {
  const attempts = buildMermaidRenderAttempts(source);
  let lastErr = null;
  for (const candidate of attempts) {
    const renderId = `md-mermaid-render-${mermaidSeq++}`;
    try {
      const { svg } = await mermaid.render(renderId, candidate);
      return { svg: fixMindmapLabelAlignment(svg), source: candidate };
    } catch (err) {
      lastErr = err;
      document.getElementById(renderId)?.remove();
      document.querySelector(`[data-mermaid-id="${renderId}"]`)?.remove();
    }
  }
  throw lastErr || new Error("Mermaid 渲染失败");
}

function applyMermaidSvg(wrap, pre, source, svg) {
  wrap.setAttribute("data-mermaid-source", encodeURIComponent(source));
  pre.setAttribute("data-mermaid", encodeURIComponent(source));
  pre.textContent = source;
  pre.classList.remove("md-mermaid--error", "md-mermaid--loading");
  pre.style.display = "none";

  let svgWrap = wrap.querySelector(".md-mermaid-svg");
  if (!svgWrap) {
    svgWrap = document.createElement("div");
    svgWrap.className = "md-mermaid-svg";
    svgWrap.setAttribute("aria-hidden", "true");
    wrap.appendChild(svgWrap);
  }
  svgWrap.innerHTML = svg;
}

async function renderOneMermaidNode(el) {
  if (!el?.getAttribute) return;
  const wrap = el.closest(".md-mermaid-wrap") || el.parentElement;
  if (!wrap) return;
  if (wrap.querySelector(".md-mermaid-svg")) return;
  if (mermaidRendering.has(wrap)) return;

  const source = readMermaidSourceFromElement(el, wrap);
  if (!source) return;

  mermaidRendering.add(wrap);
  el.classList.add("md-mermaid--loading");
  el.classList.remove("md-mermaid--error");
  el.style.display = "";

  try {
    const mermaid = await loadMermaid();
    const { svg, source: renderedSource } = await renderMermaidAttempts(mermaid, source);
    if (!wrap.isConnected) return;
    applyMermaidSvg(wrap, ensureMermaidPlaceholder(wrap, renderedSource), renderedSource, svg);
  } catch (err) {
    if (!wrap.isConnected) return;
    showMermaidError(ensureMermaidPlaceholder(wrap, source), source, formatMermaidRenderError(err));
    wrap.querySelector(".md-mermaid-svg")?.remove();
  } finally {
    mermaidRendering.delete(wrap);
  }
}

export async function renderMermaidSvg(source) {
  const mermaid = await loadMermaid();
  const normalized = normalizeMermaidSource(source);
  try {
    const { svg } = await renderMermaidAttempts(mermaid, normalized || source);
    return svg;
  } catch (err) {
    throw new Error(formatMermaidRenderError(err));
  }
}

export async function mountMermaidInElement(root) {
  if (!root?.querySelectorAll) return;
  const nodes = root.querySelectorAll(".md-mermaid-wrap .md-mermaid, .md-mermaid[data-mermaid]");
  if (!nodes.length) return;
  const observer = getMermaidObserver();
  for (const el of nodes) {
    const wrap = el.closest(".md-mermaid-wrap");
    if (wrap?.querySelector(".md-mermaid-svg")) continue;
    if (observer && !isElementNearViewport(el)) {
      if (!mermaidPending.has(el)) {
        mermaidPending.add(el);
        observer.observe(el);
      }
      continue;
    }
    await renderOneMermaidNode(el);
  }
}

/** 移除已渲染 Mermaid SVG，保留源码占位以便重新挂载 */
export function unmountMermaidInElement(root) {
  if (!root?.querySelectorAll) return;
  root.querySelectorAll(".md-mermaid-wrap .md-mermaid, .md-mermaid[data-mermaid]").forEach((el) => {
    unobserveMermaidNode(el);
    el.style.display = "";
    el.classList.remove("md-mermaid--loading");
  });
  root.querySelectorAll(".md-mermaid-svg").forEach((el) => el.remove());
}
