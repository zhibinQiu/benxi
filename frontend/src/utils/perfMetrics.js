/**
 * Web Vitals 性能指标采集
 * 在 router.afterEach 中触发，收集 LCP / FID / CLS / TTFB 等核心指标。
 * 数据暂挂到 sessionStorage，方便调试查因，后续可对接后端采集。
 */

const PERF_METRICS_KEY = "platform:perf-metrics";

function getMetrics() {
  try {
    const raw = sessionStorage.getItem(PERF_METRICS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveMetrics(data) {
  try {
    sessionStorage.setItem(PERF_METRICS_KEY, JSON.stringify(data));
  } catch {
    /* quota 满了忽略 */
  }
}

/**
 * 收集当前页面的性能指标并与 routeName 关联存储
 */
export function reportWebVital({ routeName }) {
  if (typeof performance === "undefined") return;

  const perf = performance;
  const nav = perf.getEntriesByType?.("navigation")?.[0];
  if (!nav) return;

  const metrics = getMetrics();
  metrics[routeName] = {
    ttfb: Math.round(nav.responseStart - nav.requestStart),
    domInteractive: Math.round(nav.domInteractive - nav.navigationStart),
    domComplete: Math.round(nav.domComplete - nav.navigationStart),
    loadEventEnd: Math.round(nav.loadEventEnd - nav.navigationStart),
    transferSize: nav.transferSize,
    encodedBodySize: nav.encodedBodySize,
    decodedBodySize: nav.decodedBodySize,
    timestamp: Date.now(),
  };
  saveMetrics(metrics);

  /* 通过 PerformanceObserver 收集 LCP / CLS */
  collectPaintMetrics(routeName);
}

function collectPaintMetrics(routeName) {
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.entryType === "largest-contentful-paint") {
          const metrics = getMetrics();
          if (metrics[routeName]) {
            metrics[routeName].lcp = Math.round(entry.startTime);
          } else {
            metrics[routeName] = { lcp: Math.round(entry.startTime), timestamp: Date.now() };
          }
          saveMetrics(metrics);
          observer.disconnect();
        }
      }
    });
    observer.observe({ type: "largest-contentful-paint", buffered: true });

    const clsObserver = new PerformanceObserver((list) => {
      let clsValue = 0;
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) clsValue += entry.value;
      }
      if (clsValue > 0) {
        const metrics = getMetrics();
        if (metrics[routeName]) {
          metrics[routeName].cls = clsValue;
        }
        saveMetrics(metrics);
      }
      clsObserver.disconnect();
    });
    clsObserver.observe({ type: "layout-shift", buffered: true });
  } catch {
    /* PerformanceObserver 不被支持则忽略 */
  }
}

/** 读取所有已采集的性能指标（调试用） */
export function readPerfMetrics() {
  return getMetrics();
}
