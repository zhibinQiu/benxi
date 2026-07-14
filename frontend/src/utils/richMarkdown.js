import { ensureMarked, escapeHtml, marked, normalizeMarkdownInput, sanitizeRenderedHtml } from "./markdown.js";
import { loadEcharts } from "./echartsLoader.js";

let echartSeq = 0;
let mermaidSeq = 0;
const chartInstances = new WeakMap();
const chartPending = new WeakSet();
let rendererRegistered = false;
let chartObserver = null;

function getChartObserver() {
  if (chartObserver || typeof IntersectionObserver === "undefined") return chartObserver;
  chartObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        chartObserver?.unobserve(entry.target);
        chartPending.delete(entry.target);
        void mountOneEchart(entry.target);
      }
    },
    { rootMargin: "288px 0px", threshold: 0.01 }
  );
  return chartObserver;
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
        if (language === "mermaid") {
          const id = `md-mermaid-${mermaidSeq++}`;
          const body = String(text || "").trim();
          const encoded = encodeURIComponent(body);
          const safe = escapeHtml(body);
          return (
            `<div class="md-mermaid-wrap">` +
            `<pre class="md-mermaid" id="${id}" data-mermaid="${encoded}">${safe}</pre>` +
            `</div>`
          );
        }
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

export { normalizeMarkdownInput };

export function renderRichMarkdown(text) {
  ensureEchartsRenderer();
  const source = normalizeMarkdownInput(text);
  try {
    return sanitizeRenderedHtml(marked.parse(source));
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
  const observer = getChartObserver();
  root.querySelectorAll(".md-echart").forEach((el) => {
    if (chartInstances.get(el)) return;
    if (observer) {
      if (!chartPending.has(el)) {
        chartPending.add(el);
        observer.observe(el);
      }
      return;
    }
    void mountOneEchart(el);
  });
}

/** 挂载富文本中的 ECharts / Mermaid（均在进入视口后才加载对应 JS 包） */
export async function mountRichMediaInElement(root) {
  mountEchartsInElement(root);
  const { mountMermaidInElement } = await import("./mermaidRender.js");
  await mountMermaidInElement(root);
}

export function getEchartForElement(el) {
  return chartInstances.get(el) || null;
}

export function disposeEchartsInElement(root) {
  if (!root?.querySelectorAll) return;
  root.querySelectorAll(".md-echart").forEach((el) => {
    chartPending.delete(el);
    chartObserver?.unobserve(el);
    const chart = chartInstances.get(el);
    if (chart) {
      chart.dispose();
      chartInstances.delete(el);
    }
  });
}

let resizeBoundCount = 0;

function onWindowResize() {
  document.querySelectorAll(".md-echart").forEach((el) => {
    const chart = chartInstances.get(el);
    chart?.resize();
  });
}

export function bindEchartsResize() {
  if (typeof window === "undefined") return;
  resizeBoundCount += 1;
  if (resizeBoundCount === 1) {
    window.addEventListener("resize", onWindowResize);
  }
}

export function unbindEchartsResize() {
  if (typeof window === "undefined" || resizeBoundCount <= 0) return;
  resizeBoundCount -= 1;
  if (resizeBoundCount === 0) {
    window.removeEventListener("resize", onWindowResize);
  }
}
