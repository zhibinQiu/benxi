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
  return { width: Math.max(width, 384), height: Math.max(height, 288) };
}

function extractForeignObjectText(fo) {
  const root = fo.querySelector("div, span, p") || fo;
  const lines = [];
  root.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent?.trim();
      if (text) lines.push(text);
      return;
    }
    if (node.nodeName === "BR") {
      lines.push("\n");
      return;
    }
    const text = node.textContent?.trim();
    if (text) lines.push(text);
  });
  const merged = lines.join("").replace(/\n+/g, "\n").trim();
  return merged || (fo.textContent || "").replace(/\s+/g, " ").trim();
}

function readForeignObjectStyle(fo, sourceFo) {
  const live = sourceFo?.querySelector?.("div, span, p") || sourceFo;
  const fallback = fo.querySelector("div, span, p") || fo;
  const target = live?.isConnected ? live : fallback;
  let fill = "#333333";
  let fontSize = "14px";
  let fontFamily = "sans-serif";
  let fontWeight = "";
  if (target && typeof window !== "undefined" && window.getComputedStyle) {
    const cs = window.getComputedStyle(target);
    if (cs.fill && cs.fill !== "none") fill = cs.fill;
    if (cs.color && cs.color !== "rgba(0, 0, 0, 0)") fill = cs.color;
    if (cs.fontSize) fontSize = cs.fontSize;
    if (cs.fontFamily) fontFamily = cs.fontFamily;
    if (cs.fontWeight && cs.fontWeight !== "normal") fontWeight = cs.fontWeight;
  } else {
    const inline = fallback?.getAttribute?.("style") || "";
    const colorMatch = inline.match(/(?:^|;)\s*color:\s*([^;]+)/i);
    const sizeMatch = inline.match(/font-size:\s*([^;]+)/i);
    if (colorMatch) fill = colorMatch[1].trim();
    if (sizeMatch) fontSize = sizeMatch[1].trim();
  }
  return { fill, fontSize, fontFamily, fontWeight };
}

/** Mermaid 标签常用 foreignObject + HTML，Canvas 无法渲染；转为原生 SVG text。 */
function convertForeignObjectsToSvgText(svg, sourceSvg = svg) {
  const ns = "http://www.w3.org/2000/svg";
  const sourceObjects = [...sourceSvg.querySelectorAll("foreignObject")];
  [...svg.querySelectorAll("foreignObject")].forEach((fo, index) => {
    fo.setAttribute("overflow", "visible");
    const text = extractForeignObjectText(fo);
    if (!text) {
      fo.remove();
      return;
    }
    const { fill, fontSize, fontFamily, fontWeight } = readForeignObjectStyle(
      fo,
      sourceObjects[index]
    );
    const x = Number.parseFloat(fo.getAttribute("x") || "0");
    const y = Number.parseFloat(fo.getAttribute("y") || "0");
    const width = Number.parseFloat(fo.getAttribute("width") || "0");
    const height = Number.parseFloat(fo.getAttribute("height") || "0");
    const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
    const textEl = document.createElementNS(ns, "text");
    textEl.setAttribute("x", String(x + width / 2));
    textEl.setAttribute("y", String(y + height / 2));
    textEl.setAttribute("text-anchor", "middle");
    textEl.setAttribute("dominant-baseline", "middle");
    textEl.setAttribute("font-family", fontFamily);
    textEl.setAttribute("font-size", fontSize);
    textEl.setAttribute("fill", fill);
    if (fontWeight) textEl.setAttribute("font-weight", fontWeight);
    if (lines.length <= 1) {
      textEl.textContent = text;
    } else {
      const lineHeight = Number.parseFloat(fontSize) || 14;
      textEl.setAttribute("y", String(y + height / 2 - ((lines.length - 1) * lineHeight) / 2));
      lines.forEach((line, lineIndex) => {
        const tspan = document.createElementNS(ns, "tspan");
        tspan.setAttribute("x", String(x + width / 2));
        tspan.setAttribute("dy", lineIndex === 0 ? "0" : String(lineHeight));
        tspan.textContent = line;
        textEl.appendChild(tspan);
      });
    }
    fo.parentNode?.insertBefore(textEl, fo);
    fo.remove();
  });
}

function inlineComputedTextStyles(svg, sourceSvg) {
  const srcTexts = sourceSvg.querySelectorAll("text");
  const cloneTexts = svg.querySelectorAll("text");
  cloneTexts.forEach((el, index) => {
    const src = srcTexts[index];
    if (!src?.isConnected || typeof window === "undefined") return;
    const cs = window.getComputedStyle(src);
    if (cs.fill && cs.fill !== "none") el.setAttribute("fill", cs.fill);
    if (cs.fontSize) el.setAttribute("font-size", cs.fontSize);
    if (cs.fontFamily) el.setAttribute("font-family", cs.fontFamily);
    if (cs.fontWeight && cs.fontWeight !== "normal") {
      el.setAttribute("font-weight", cs.fontWeight);
    }
  });
}

function sanitizeSvgForExport(svg, sourceSvg = svg) {
  convertForeignObjectsToSvgText(svg, sourceSvg);
  inlineComputedTextStyles(svg, sourceSvg);
  svg.querySelectorAll("image").forEach((el) => {
    const href = el.getAttribute("href") || el.getAttribute("xlink:href");
    if (href && !href.startsWith("data:")) el.remove();
  });
  svg.querySelectorAll("style").forEach((styleEl) => {
    styleEl.textContent = (styleEl.textContent || "")
      .replace(/@import[\s\S]*?;/g, "")
      .replace(/@font-face[\s\S]*?}/g, "")
      .replace(/var\(--[^)]+\)/g, "sans-serif");
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
  sanitizeSvgForExport(clone, svgEl);
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
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:-10000px;top:0;pointer-events:none;opacity:0;";
  host.innerHTML = svgString;
  const svgNode = host.querySelector("svg");
  document.body.appendChild(host);
  try {
    if (svgNode) {
      return await rasterizeSvgNodeToPngBlob(svgNode, width, height);
    }
  } finally {
    host.remove();
  }
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

async function rasterizeSvgNodeToPngBlob(svgNode, width, height) {
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(width * scale);
  canvas.height = Math.ceil(height * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(scale, scale);
  const xml = new XMLSerializer().serializeToString(svgNode);
  const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.decoding = "sync";
    await new Promise((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("SVG 渲染失败"));
      img.src = url;
    });
    ctx.drawImage(img, 0, 0, width, height);
    return canvasToPngBlob(canvas);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function downloadSvgElement(svgEl, filename = "diagram.svg") {
  const { clone } = prepareSvgClone(svgEl);
  const xml = new XMLSerializer().serializeToString(clone);
  downloadBlob(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }), filename);
}

/** 将 Mermaid 渲染得到的 SVG 字符串转为 PNG base64（供 Word 导出嵌入）。 */
export async function svgStringToPngBase64(svgString) {
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:-10000px;top:0;pointer-events:none;opacity:0;";
  host.innerHTML = svgString;
  const svgNode = host.querySelector("svg");
  document.body.appendChild(host);
  try {
    if (!svgNode) throw new Error("无效 SVG");
    const { clone, width, height } = prepareSvgClone(svgNode);
    const pngBlob = await rasterizeSvgNodeToPngBlob(clone, width, height);
    const buffer = await pngBlob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  } finally {
    host.remove();
  }
}

export async function downloadSvgAsPng(svgEl, filename = "diagram.png") {
  const { clone, width, height } = prepareSvgClone(svgEl);
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:-10000px;top:0;opacity:0;pointer-events:none;";
  host.appendChild(clone);
  document.body.appendChild(host);
  try {
    const pngBlob = await rasterizeSvgNodeToPngBlob(clone, width, height);
    downloadBlob(pngBlob, filename);
    return { ok: true, format: "png" };
  } catch (err) {
    if (!isCanvasSecurityError(err)) throw err;
    const svgName = filename.replace(/\.png$/i, ".svg");
    downloadSvgElement(svgEl, svgName);
    return { ok: true, format: "svg", fallback: true };
  } finally {
    host.remove();
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
