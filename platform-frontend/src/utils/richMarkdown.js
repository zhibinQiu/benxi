import { ensureMarked, marked, normalizeMarkdownInput } from "./markdown.js";

let echartSeq = 0;
const chartInstances = new WeakMap();
let echartsLoader = null;
let rendererRegistered = false;

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function isEchartsOption(obj) {
  return (
    obj &&
    typeof obj === "object" &&
    (Array.isArray(obj.series) || obj.xAxis != null || obj.yAxis != null)
  );
}

function parseEchartsOption(raw) {
  const text = (raw || "").trim();
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    if (isEchartsOption(parsed)) return parsed;
    if (parsed?.option && isEchartsOption(parsed.option)) return parsed.option;
  } catch {
    /* ignore */
  }
  return null;
}

function ensureEchartsRenderer() {
  if (rendererRegistered) return;
  ensureMarked();
  marked.use({
    renderer: {
      code({ text, lang }) {
        const language = (lang || "").trim().toLowerCase();
        if (language === "echarts" || language === "chart") {
          const id = `md-echart-${echartSeq++}`;
          const encoded = encodeURIComponent(text || "");
          return (
            `<div class="md-echart-wrap">` +
            `<div id="${id}" class="md-echart" data-option="${encoded}" ` +
            `style="height:320px;width:100%;min-height:200px"></div></div>`
          );
        }
        if (language === "json") {
          const option = parseEchartsOption(text);
          if (option) {
            const id = `md-echart-${echartSeq++}`;
            const encoded = encodeURIComponent(JSON.stringify(option));
            return (
              `<div class="md-echart-wrap">` +
              `<div id="${id}" class="md-echart" data-option="${encoded}" ` +
              `style="height:320px;width:100%;min-height:200px"></div></div>`
            );
          }
        }
        const safe = escapeHtml(text || "");
        const langClass = language ? ` class="language-${language}"` : "";
        return `<pre><code${langClass}>${safe}</code></pre>`;
      },
    },
  });
  rendererRegistered = true;
}

async function loadEcharts() {
  if (!echartsLoader) {
    echartsLoader = import("echarts").then((mod) => mod.default ?? mod);
  }
  return echartsLoader;
}

export { normalizeMarkdownInput };

export function renderRichMarkdown(text) {
  ensureEchartsRenderer();
  const source = normalizeMarkdownInput(text);
  try {
    return marked.parse(source);
  } catch {
    return `<p>${escapeHtml(source)}</p>`;
  }
}

async function mountOneEchart(el) {
  const encoded = el.getAttribute("data-option");
  if (!encoded) return;
  let option;
  try {
    option = JSON.parse(decodeURIComponent(encoded));
  } catch {
    el.innerHTML = '<pre class="md-echart-error">图表配置解析失败</pre>';
    return;
  }
  if (!isEchartsOption(option)) {
    el.innerHTML = '<pre class="md-echart-error">无效的 ECharts 配置</pre>';
    return;
  }
  const prev = chartInstances.get(el);
  if (prev) {
    prev.dispose();
    chartInstances.delete(el);
  }
  const echarts = await loadEcharts();
  const chart = echarts.init(el, undefined, { renderer: "canvas" });
  chart.setOption(option, { notMerge: true });
  chartInstances.set(el, chart);
}

export function mountEchartsInElement(root) {
  if (!root?.querySelectorAll) return;
  root.querySelectorAll(".md-echart").forEach((el) => {
    void mountOneEchart(el);
  });
}

export function disposeEchartsInElement(root) {
  if (!root?.querySelectorAll) return;
  root.querySelectorAll(".md-echart").forEach((el) => {
    const chart = chartInstances.get(el);
    if (chart) {
      chart.dispose();
      chartInstances.delete(el);
    }
  });
}

let resizeBound = false;

function onWindowResize() {
  document.querySelectorAll(".md-echart").forEach((el) => {
    const chart = chartInstances.get(el);
    chart?.resize();
  });
}

export function bindEchartsResize() {
  if (resizeBound || typeof window === "undefined") return;
  window.addEventListener("resize", onWindowResize);
  resizeBound = true;
}

export function unbindEchartsResize() {
  if (!resizeBound || typeof window === "undefined") return;
  window.removeEventListener("resize", onWindowResize);
  resizeBound = false;
}
