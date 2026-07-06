/** 为 Markdown 富媒体块绑定放大查看交互 */

import { readMermaidSourceFromElement } from "./mermaidRender.js";

const boundHandlers = new WeakMap();

function readMermaidSourceFromWrap(wrap) {
  if (!wrap) return "";
  const fromWrap = wrap.getAttribute?.("data-mermaid-source");
  if (fromWrap) {
    try {
      return decodeURIComponent(fromWrap);
    } catch {
      /* ignore */
    }
  }
  const pre = wrap.querySelector?.(".md-mermaid");
  return readMermaidSourceFromElement(pre, wrap);
}

function readCodeBlock(pre) {
  const code = pre.querySelector("code");
  const language = [...(code?.classList || [])]
    .find((cls) => cls.startsWith("language-"))
    ?.slice("language-".length) || "";
  return {
    language,
    code: (code?.textContent || pre.textContent || "").trim(),
  };
}

function isInteractiveCodeBlock(pre) {
  if (!pre?.closest) return false;
  if (pre.classList.contains("md-mermaid")) return false;
  if (pre.closest(".md-mermaid-wrap")) return false;
  return Boolean(pre.querySelector("code"));
}

function buildPayloadFromTarget(target) {
  const img = target.closest("img");
  if (img && !img.closest("button, a")) {
    return {
      type: "image",
      title: img.alt || "图片",
      imageUrl: img.currentSrc || img.src,
    };
  }

  const mermaidWrap = target.closest(".md-mermaid-wrap");
  if (mermaidWrap) {
    const svg = mermaidWrap.querySelector("svg");
    const source = readMermaidSourceFromWrap(mermaidWrap);
    return {
      type: "mermaid",
      title: "Mermaid 图表",
      svgHtml: svg?.outerHTML || mermaidWrap.innerHTML,
      mermaidSource: source,
      isMindmap: /^\s*mindmap\b/im.test(source),
    };
  }

  const echartWrap = target.closest(".md-echart-wrap");
  if (echartWrap) {
    const chartEl = echartWrap.querySelector(".md-echart[data-option]");
    const encoded = chartEl?.getAttribute("data-option") || "";
    let option = null;
    try {
      option = JSON.parse(decodeURIComponent(encoded));
    } catch {
      option = null;
    }
    return {
      type: "echart",
      title: "图表",
      echartOption: option,
    };
  }

  const pre = target.closest("pre");
  if (pre && isInteractiveCodeBlock(pre)) {
    const { language, code } = readCodeBlock(pre);
    if (!code) return null;
    return {
      type: "code",
      title: language ? `${language} 代码` : "代码",
      language,
      code,
    };
  }

  return null;
}

function decorateBlock(block, hintText = "放大") {
  if (!block || block.dataset.richMediaDecorated === "1") return;
  block.dataset.richMediaDecorated = "1";
  block.classList.add("md-rich-media-block");
  if (!block.hasAttribute("tabindex")) {
    block.setAttribute("tabindex", "0");
  }
  if (!block.getAttribute("role")) {
    block.setAttribute("role", "button");
  }
  if (!block.querySelector(".md-rich-media-hint")) {
    const hint = document.createElement("span");
    hint.className = "md-rich-media-hint";
    hint.setAttribute("aria-hidden", "true");
    hint.textContent = hintText;
    block.appendChild(hint);
  }
}

export function decorateRichMediaBlocks(root, hintText) {
  if (!root?.querySelectorAll) return;
  const hint = hintText || root.dataset.richMediaHint || "放大";
  root.querySelectorAll("img").forEach((img) => {
    if (img.closest("button, a")) return;
    const host = img.closest("p") || img;
    decorateBlock(host, hint);
  });
  root.querySelectorAll(".md-mermaid-wrap, .md-echart-wrap").forEach((el) => decorateBlock(el, hint));
  root.querySelectorAll("pre").forEach((pre) => {
    if (isInteractiveCodeBlock(pre)) decorateBlock(pre, hint);
  });
}

export function bindRichMediaViewer(root, onOpen, options = {}) {
  if (!root || typeof onOpen !== "function") return;
  unbindRichMediaViewer(root);
  const expandHint = options.expandHint;

  function onClick(event) {
    if (event.target?.closest?.(".knowledge-cite-mark")) return;
    const payload = buildPayloadFromTarget(event.target);
    if (!payload) return;
    event.preventDefault();
    event.stopPropagation();
    onOpen(payload);
  }

  function onKeydown(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const block = event.target?.closest?.(".md-rich-media-block");
    if (!block) return;
    event.preventDefault();
    const payload = buildPayloadFromTarget(block);
    if (payload) onOpen(payload);
  }

  root.addEventListener("click", onClick);
  root.addEventListener("keydown", onKeydown);
  boundHandlers.set(root, { onClick, onKeydown });
  decorateRichMediaBlocks(root, expandHint);
}

export function unbindRichMediaViewer(root) {
  const handlers = boundHandlers.get(root);
  if (!handlers) return;
  root.removeEventListener("click", handlers.onClick);
  root.removeEventListener("keydown", handlers.onKeydown);
  boundHandlers.delete(root);
}
