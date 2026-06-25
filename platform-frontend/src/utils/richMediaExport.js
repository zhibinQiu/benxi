/** 对话富媒体：保存图片与导出 Markdown / OPML */

import {
  downloadTextFile,
  exportMindmapMarkdown,
  exportMindmapOpml,
} from "./mindmapExport.js";
import { downloadBlob } from "./downloadBlob.js";

function safeFilenameStem(title, fallback = "diagram") {
  const stem = String(title || "")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .trim()
    .slice(0, 80);
  return stem || fallback;
}

export function isMermaidMindmap(source) {
  return /^\s*mindmap\b/im.test(String(source || "").trim());
}

export function exportMermaidSourceMarkdown(source, title = "图表") {
  const body = `# ${title}\n\n\`\`\`mermaid\n${String(source || "").trim()}\n\`\`\`\n`;
  downloadTextFile(body, `${safeFilenameStem(title)}.md`);
}

export function exportCodeBlockMarkdown(code, lang = "", title = "代码") {
  const fence = lang ? lang.trim() : "";
  const body = `# ${title}\n\n\`\`\`${fence}\n${String(code || "").trim()}\n\`\`\`\n`;
  downloadTextFile(body, `${safeFilenameStem(title, "code")}.md`);
}

export function exportInlineMindmapMarkdown(mermaidSource, title = "思维导图") {
  exportMindmapMarkdown({ mermaid: mermaidSource, title });
}

export function exportInlineMindmapOpml(mermaidSource, title = "思维导图") {
  exportMindmapOpml({ mermaid: mermaidSource, title });
}

function readSvgSize(svgEl) {
  const viewBox = svgEl.getAttribute("viewBox");
  if (viewBox) {
    const parts = viewBox.split(/\s+/).map(Number);
    if (parts.length === 4 && parts[2] > 0 && parts[3] > 0) {
      return { width: parts[2], height: parts[3] };
    }
  }
  const width = Number.parseFloat(svgEl.getAttribute("width")) || svgEl.clientWidth || 960;
  const height = Number.parseFloat(svgEl.getAttribute("height")) || svgEl.clientHeight || 640;
  return { width: Math.max(width, 320), height: Math.max(height, 240) };
}

function sanitizeSvgForExport(svg) {
  svg.querySelectorAll("foreignObject").forEach((el) => el.remove());
  svg.querySelectorAll("image").forEach((el) => {
    const href = el.getAttribute("href") || el.getAttribute("xlink:href");
    if (href && !href.startsWith("data:")) el.remove();
  });
  svg.querySelectorAll("style").forEach((styleEl) => {
    styleEl.textContent = (styleEl.textContent || "")
      .replace(/@import[\s\S]*?;/g, "")
      .replace(/@font-face[\s\S]*?}/g, "");
  });
  const html = svg.innerHTML || "";
  if (/var\(--/.test(html)) {
    svg.innerHTML = html.replace(/var\(--[^)]+\)/g, "sans-serif");
  }
  if (!svg.querySelector("[data-export-bg]")) {
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("data-export-bg", "1");
    bg.setAttribute("x", "0");
    bg.setAttribute("y", "0");
    bg.setAttribute("width", "100%");
    bg.setAttribute("height", "100%");
    bg.setAttribute("fill", "#ffffff");
    svg.insertBefore(bg, svg.firstChild);
  }
}

function prepareSvgClone(svgEl) {
  const { width, height } = readSvgSize(svgEl);
  const clone = svgEl.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  sanitizeSvgForExport(clone);
  return { clone, width, height };
}

function svgStringToDataUrl(svgString) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgString)}`;
}

function canvasToPngBlob(canvas) {
  return new Promise((resolve, reject) => {
    try {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("PNG 生成失败"));
      }, "image/png");
    } catch (err) {
      reject(err);
    }
  });
}

function isCanvasSecurityError(err) {
  const msg = String(err?.message || err || "");
  return (
    err?.name === "SecurityError"
    || msg.includes("Tainted")
    || msg.includes("tainted")
  );
}

async function rasterizeSvgStringToPngBlob(svgString, width, height) {
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.decoding = "sync";
  await new Promise((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("SVG 渲染失败"));
    img.src = svgStringToDataUrl(svgString);
  });
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(width * scale);
  canvas.height = Math.ceil(height * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(scale, scale);
  ctx.drawImage(img, 0, 0, width, height);
  return canvasToPngBlob(canvas);
}

export function downloadSvgElement(svgEl, filename = "diagram.svg") {
  const { clone } = prepareSvgClone(svgEl);
  const xml = new XMLSerializer().serializeToString(clone);
  downloadBlob(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }), filename);
}

export async function downloadSvgAsPng(svgEl, filename = "diagram.png") {
  const { clone, width, height } = prepareSvgClone(svgEl);
  const xml = new XMLSerializer().serializeToString(clone);
  try {
    const pngBlob = await rasterizeSvgStringToPngBlob(xml, width, height);
    downloadBlob(pngBlob, filename);
    return { ok: true, format: "png" };
  } catch (err) {
    if (!isCanvasSecurityError(err)) throw err;
    const svgName = filename.replace(/\.png$/i, ".svg");
    downloadSvgElement(svgEl, svgName);
    return { ok: true, format: "svg", fallback: true };
  }
}

async function rasterizeImageElementToPngBlob(imgEl) {
  const width = imgEl.naturalWidth || imgEl.width;
  const height = imgEl.naturalHeight || imgEl.height;
  if (!width || !height) throw new Error("图片尺寸无效");
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.decoding = "sync";
  const src = imgEl.currentSrc || imgEl.src;
  await new Promise((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("图片渲染失败"));
    img.src = src;
  });
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, width, height);
  return canvasToPngBlob(canvas);
}

export async function downloadImageElement(imgEl, filename = "image.png") {
  const src = imgEl.currentSrc || imgEl.src;
  if (!src) throw new Error("缺少图片地址");
  if (src.startsWith("blob:") || src.startsWith("data:")) {
    const res = await fetch(src);
    downloadBlob(await res.blob(), filename);
    return { ok: true, format: "original" };
  }
  try {
    const res = await fetch(src, { credentials: "include" });
    if (!res.ok) throw new Error("图片下载失败");
    downloadBlob(await res.blob(), filename);
    return { ok: true, format: "original" };
  } catch {
    try {
      const pngBlob = await rasterizeImageElementToPngBlob(imgEl);
      downloadBlob(pngBlob, filename);
      return { ok: true, format: "png" };
    } catch (err) {
      if (isCanvasSecurityError(err)) {
        throw new Error("图片跨域限制，无法导出 PNG");
      }
      throw err;
    }
  }
}

export function downloadEchartPng(chart, filename = "chart.png") {
  if (!chart?.getDataURL) throw new Error("图表不可用");
  const dataUrl = chart.getDataURL({
    type: "png",
    pixelRatio: 2,
    backgroundColor: "#ffffff",
  });
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  a.click();
}
