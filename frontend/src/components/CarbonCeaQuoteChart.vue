<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from "vue";
import { RefreshOutline } from "@vicons/ionicons5";
import { fetchCeaKline, fetchCcerKline, syncMarketQuotes } from "../api/carbonCompliance";
import { loadEcharts } from "../utils/echartsLoader.js";
import { isRouteAbortError } from "../api/http.js";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  sma,
  calcMacd,
  calcRsi,
  closesFromCandles,
  volumesFromPoints,
} from "../utils/carbonTechIndicators.js";

const sharedCeaCache = { daily: null };
const sharedCcerCache = { daily: null };
const sharedCeaForecastCache = Object.create(null);
const sharedCcerForecastCache = Object.create(null);

const ui = usePlatformUi();

const emit = defineEmits(["market-synced"]);

const chartKind = ref("daily");
const loading = ref(false);
/** 品种开关：可同时、可只选其一 */
const showCea = ref(true);
const showCcer = ref(true);
const ceaMeta = ref(null);
const ccerMeta = ref(null);
/** 至年底预测算法 */
const forecastMethod = ref("rule");
const forecastMethodOptions = [
  {
    value: "rule",
    label: "规则模型",
    description:
      "衰减趋势(均线差)+去均值同周季节+履约季冲高回落（约12月初见顶、年底回吐）；波动带=近60日收益标准差×√天数",
  },
  {
    value: "ets",
    label: "ETS（Holt-Winters）",
    description: "加法季节平滑，交易周 period=5；适合短期平滑外推",
  },
  {
    value: "sarimax",
    label: "SARIMAX（履约月外生）",
    description: "带履约月(10–12)外生变量的 SARIMAX/ARX；未装 statsmodels 时用最小二乘近似",
  },
  {
    value: "prophet",
    label: "Prophet",
    description: "周/年季节性 + 履约月回归器；未安装 prophet 时回退规则模型",
  },
];
/** 主图/副图指标：默认仅成交量；MA/MACD/RSI 点选后再显示 */
const showMa = ref(false);
const showVol = ref(true);
const showMacd = ref(false);
const showRsi = ref(false);
const chartHost = ref(null);
let chart = null;
let resizeObs = null;

const CEA_COLOR = "#0f766e";
const CCER_COLOR = "#0369a1";

const kindTabs = computed(() => [
  { value: "daily", label: "日K线", disabled: false },
  { value: "forecast", label: "至年底预测", disabled: false },
]);

const showIndicators = computed(
  () => chartKind.value === "daily" || chartKind.value === "forecast"
);

const forecastSummary = computed(() => {
  if (showCea.value && ceaMeta.value?.summary) return ceaMeta.value.summary;
  if (showCcer.value && ccerMeta.value?.summary) return ccerMeta.value.summary;
  return null;
});

const sourceLines = computed(() => {
  const lines = [];
  if (showCea.value && ceaMeta.value) {
    lines.push({
      name: ceaMeta.value.source_name || "上海环境能源交易所 · 全国碳市场",
      page: ceaMeta.value.source_page || "https://www.cneeex.com/zhhq/quotshown.html?area=0",
      label: "打开环交所行情页",
      latest:
        ceaMeta.value.latest?.price ??
        ceaMeta.value.latest?.close ??
        ceaMeta.value.latest?.avg_price,
      queried: ceaMeta.value.queried_at,
    });
  }
  if (showCcer.value && ccerMeta.value) {
    lines.push({
      name: ccerMeta.value.source_name || "全国温室气体自愿减排交易系统 · 北京绿色交易所",
      page:
        ccerMeta.value.source_page ||
        "https://www.ccer.com.cn/wcm/ccer/html/2502lshq/index.html",
      label: "打开自愿减排行情页",
      latest:
        ccerMeta.value.latest?.price ??
        ccerMeta.value.latest?.close ??
        ccerMeta.value.latest?.avg_price,
      queried: ccerMeta.value.queried_at,
    });
  }
  return lines;
});

const candleItemStyle = {
  color: "#ef4444",
  color0: "#16a34a",
  borderColor: "#ef4444",
  borderColor0: "#16a34a",
};

function dateKey(t) {
  return String(t || "").slice(0, 10);
}

function unionXs(...pointLists) {
  const set = new Set();
  for (const pts of pointLists) {
    for (const p of pts || []) {
      if (p?.t) set.add(String(p.t));
    }
  }
  return [...set].sort();
}

function mapByDate(points) {
  const m = new Map();
  for (const p of points || []) {
    if (!p?.t) continue;
    m.set(dateKey(p.t), p);
  }
  return m;
}

function toCandle(p, prevClose = null) {
  if (!p) return null;
  let c =
    p.close != null ? Number(p.close) : p.price != null ? Number(p.price) : null;
  if (c == null || Number.isNaN(c)) return null;
  let o = p.open != null ? Number(p.open) : null;
  let h = p.high != null ? Number(p.high) : null;
  let l = p.low != null ? Number(p.low) : null;
  if (o == null || Number.isNaN(o)) o = prevClose != null ? prevClose : c;
  if (h == null || Number.isNaN(h)) h = Math.max(o, c);
  if (l == null || Number.isNaN(l)) l = Math.min(o, c);
  h = Math.max(h, o, c);
  l = Math.min(l, o, c);
  return [o, c, l, h];
}

function buildCandleSeries(points) {
  const candles = [];
  let prev = null;
  for (const p of points || []) {
    const c = toCandle(p, prev);
    // ECharts candlestick 禁止 null，无数据用 '-'
    candles.push(c || "-");
    if (c) prev = c[1];
  }
  return candles;
}

/** 按 xs 对齐蜡烛；缺口用 '-'（ECharts 蜡烛图不能用 null，会崩） */
function alignCandlesToXs(xs, points) {
  const m = mapByDate(points);
  const out = [];
  let prev = null;
  for (const t of xs) {
    const p = m.get(dateKey(t));
    if (!p) {
      out.push("-");
      continue;
    }
    const c = toCandle(p, prev);
    if (!c) {
      out.push("-");
      continue;
    }
    out.push(c);
    prev = c[1];
  }
  return out;
}

function alignPricesToXs(xs, points) {
  const m = mapByDate(points);
  return xs.map((t) => {
    const p = m.get(dateKey(t));
    if (!p) return null;
    const v = p.close != null ? Number(p.close) : Number(p.price);
    return Number.isNaN(v) ? null : v;
  });
}

function alignRawPointsToXs(xs, points) {
  const m = mapByDate(points);
  return xs.map((t) => m.get(dateKey(t)) || { t, volume: null });
}

/** 格式化价量；空值显示 — */
function fmtNum(v, digits = 2) {
  if (v == null || v === "" || v === "-") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return digits <= 0 ? String(Math.round(n)) : n.toFixed(digits);
}

/**
 * 从 tooltip 参数与原始行情点解析 OHLC。
 * ECharts 蜡烛图 value 可能是 [open,close,low,high]，也可能前置了类目/下标。
 */
function resolveOhlc(param, row = {}) {
  const num = (v) => {
    if (v == null || v === "") return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  };
  // 优先用原始行情字段，避免把「昨收补全的开盘」或 ECharts 前置下标当成开盘价
  let o = num(row.open);
  let c = num(row.close) ?? num(row.price);
  let l = num(row.low);
  let h = num(row.high);

  const raw = Array.isArray(param?.data)
    ? param.data
    : Array.isArray(param?.value)
      ? param.value
      : null;
  if (raw?.length) {
    const nums = raw.map((x) => Number(x)).filter((n) => !Number.isNaN(n));
    // 5 个数时首项多为 dataIndex；取末 4 位为开/收/低/高
    const four =
      nums.length >= 5 ? nums.slice(-4) : nums.length >= 4 ? nums.slice(0, 4) : null;
    if (four) {
      // 不用蜡烛图补开盘（可能是昨收），避免悬浮显示错误开盘价
      if (c == null) c = four[1];
      if (l == null) l = four[2];
      if (h == null) h = four[3];
    }
  }
  return { o, c, l, h };
}

/**
 * 股票式多图：主图 K/线+MA，副图量能，再下 MACD / RSI
 * primary：指标与量能基准；secondary：另一品种收盘价折线
 */
function buildPanelsOption({
  title,
  xs,
  primaryName,
  primaryCandles,
  primaryPoints,
  secondaryName = null,
  secondaryYs = null,
  forecastSeries = null,
  startPct = 70,
}) {
  const closes = closesFromCandles(primaryCandles);
  const vols = volumesFromPoints(primaryPoints);

  const panels = ["main"];
  if (showVol.value) panels.push("vol");
  if (showMacd.value) panels.push("macd");
  if (showRsi.value) panels.push("rsi");

  const gap = 2.2;
  const grids = [];
  let cursor = 8;
  const totalH = 78;
  const weights = panels.map((p) => (p === "main" ? 2.4 : 1));
  const wSum = weights.reduce((a, b) => a + b, 0);
  for (let i = 0; i < panels.length; i++) {
    const h = (weights[i] / wSum) * totalH;
    grids.push({
      left: 48,
      right: 24,
      top: `${cursor}%`,
      height: `${Math.max(h - gap, 8)}%`,
    });
    cursor += h;
  }

  const xAxes = panels.map((_, i) => ({
    type: "category",
    data: xs,
    boundaryGap: true,
    gridIndex: i,
    axisLabel: {
      show: i === panels.length - 1,
      color: "#64748b",
      hideOverlap: true,
      fontSize: 9,
    },
    axisLine: { lineStyle: { color: "#cbd5e1" } },
    axisTick: { show: i === panels.length - 1 },
  }));

  const yAxes = panels.map((p, i) => ({
    type: "value",
    scale: true,
    gridIndex: i,
    splitNumber: p === "main" ? 4 : 2,
    name: p === "main" ? "元/吨" : p === "vol" ? "量" : p === "macd" ? "MACD" : "RSI",
    nameTextStyle: { color: "#64748b", fontSize: 9 },
    nameGap: 6,
    axisLabel: { color: "#64748b", fontSize: 9 },
    splitLine: { lineStyle: { color: "#e2e8f0", type: "dashed" } },
    min: p === "rsi" ? 0 : undefined,
    max: p === "rsi" ? 100 : undefined,
  }));

  const legendData = [`${primaryName} K线`];
  const series = [
    {
      name: `${primaryName} K线`,
      type: "candlestick",
      data: primaryCandles,
      xAxisIndex: 0,
      yAxisIndex: 0,
      itemStyle: candleItemStyle,
    },
  ];

  if (showMa.value) {
    const ma5 = sma(closes, 5);
    const ma10 = sma(closes, 10);
    const ma20 = sma(closes, 20);
    for (const [name, data, color] of [
      ["MA5", ma5, "#f59e0b"],
      ["MA10", ma10, "#8b5cf6"],
      ["MA20", ma20, "#0ea5e9"],
    ]) {
      legendData.push(name);
      series.push({
        name,
        type: "line",
        data,
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        lineStyle: { width: 1.2, color },
        itemStyle: { color },
      });
    }
  }

  if (secondaryName && secondaryYs) {
    legendData.push(secondaryName);
    series.push({
      name: secondaryName,
      type: "line",
      data: secondaryYs,
      xAxisIndex: 0,
      yAxisIndex: 0,
      showSymbol: false,
      lineStyle: { width: 1.2, color: secondaryName === "CCER" ? CCER_COLOR : CEA_COLOR },
      itemStyle: { color: secondaryName === "CCER" ? CCER_COLOR : CEA_COLOR },
      connectNulls: false,
    });
  }

  if (forecastSeries) {
    for (const s of forecastSeries) {
      legendData.push(s.name);
      series.push({ ...s, xAxisIndex: 0, yAxisIndex: 0 });
    }
  }

  const volIdx = panels.indexOf("vol");
  if (volIdx >= 0) {
    legendData.push("成交量");
    series.push({
      name: "成交量",
      type: "bar",
      data: vols,
      xAxisIndex: volIdx,
      yAxisIndex: volIdx,
      barMaxWidth: 8,
      itemStyle: {
        color: (params) => {
          // 与 K 线一致：红=收涨，绿=收跌（看开收，非昨收）
          const c = primaryCandles[params.dataIndex];
          if (!c || c === "-" || !Array.isArray(c)) return "#94a3b8";
          return c[1] >= c[0] ? "rgba(239,68,68,0.55)" : "rgba(22,163,74,0.55)";
        },
      },
    });
  }

  const macdIdx = panels.indexOf("macd");
  if (macdIdx >= 0) {
    const { dif, dea, hist } = calcMacd(closes);
    legendData.push("DIF", "DEA", "MACD");
    series.push({
      name: "MACD",
      type: "bar",
      data: hist,
      xAxisIndex: macdIdx,
      yAxisIndex: macdIdx,
      barMaxWidth: 6,
      itemStyle: {
        color: (params) =>
          params.data >= 0 ? "rgba(239,68,68,0.7)" : "rgba(22,163,74,0.7)",
      },
    });
    series.push({
      name: "DIF",
      type: "line",
      data: dif,
      xAxisIndex: macdIdx,
      yAxisIndex: macdIdx,
      showSymbol: false,
      lineStyle: { width: 1.2, color: "#334155" },
    });
    series.push({
      name: "DEA",
      type: "line",
      data: dea,
      xAxisIndex: macdIdx,
      yAxisIndex: macdIdx,
      showSymbol: false,
      lineStyle: { width: 1.2, color: "#f59e0b" },
    });
  }

  const rsiIdx = panels.indexOf("rsi");
  if (rsiIdx >= 0) {
    const rsi = calcRsi(closes, 14);
    legendData.push("RSI14");
    series.push({
      name: "RSI14",
      type: "line",
      data: rsi,
      xAxisIndex: rsiIdx,
      yAxisIndex: rsiIdx,
      showSymbol: false,
      lineStyle: { width: 1.4, color: "#8b5cf6" },
      markLine: {
        silent: true,
        symbol: "none",
        lineStyle: { type: "dashed", color: "#cbd5e1" },
        data: [{ yAxis: 70 }, { yAxis: 30 }],
        label: { show: false },
      },
    });
  }

  return {
    animation: true,
    animationDuration: 350,
    legend: {
      top: 2,
      right: 8,
      type: "scroll",
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { color: "#64748b", fontSize: 10 },
      data: legendData,
    },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      textStyle: { fontSize: 11, color: "#334155" },
      formatter(params) {
        if (!params?.length) return "";
        const axis = params[0].axisValue;
        const lines = [`<span style="font-size:11px;color:#64748b">${axis}</span>`];
        let volumeShown = false;
        for (const p of params) {
          if (p.seriesType === "candlestick") {
            const row = primaryPoints[p.dataIndex] || {};
            const { o, c, l, h } = resolveOhlc(p, row);
            if (o == null && c == null) continue;
            lines.push(
              `<span style="font-size:11px">${p.marker}${p.seriesName}</span><br/>` +
                `<span style="font-size:11px;padding-left:14px">开 ${fmtNum(o)}  收 ${fmtNum(c)}</span><br/>` +
                `<span style="font-size:11px;padding-left:14px">低 ${fmtNum(l)}  高 ${fmtNum(h)}</span>`
            );
            if (row.volume != null) {
              lines.push(
                `<span style="font-size:11px;padding-left:14px">量 ${fmtNum(row.volume, 0)}</span>`
              );
              volumeShown = true;
            }
          } else if (p.seriesName === "成交量") {
            if (volumeShown) continue;
            if (p.data != null && p.data !== "-" && !Number.isNaN(Number(p.data))) {
              lines.push(
                `<span style="font-size:11px">${p.marker}成交量：${fmtNum(p.data, 0)}</span>`
              );
              volumeShown = true;
            }
          } else if (p.data != null && p.data !== "-" && !Number.isNaN(Number(p.data))) {
            lines.push(
              `<span style="font-size:11px">${p.marker}${p.seriesName}：${fmtNum(p.data, 2)}</span>`
            );
          }
        }
        return lines.join("<br/>");
      },
    },
    title: {
      text: title,
      left: 0,
      top: 0,
      textStyle: { fontSize: 11, fontWeight: 600, color: "#334155" },
    },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: panels.map((_, i) => i),
        start: startPct,
        end: 100,
      },
      {
        type: "slider",
        xAxisIndex: panels.map((_, i) => i),
        height: 16,
        bottom: 4,
        start: startPct,
        end: 100,
        borderColor: "#cbd5e1",
        fillerColor: "rgba(15, 118, 110, 0.18)",
        handleStyle: { color: "#0f766e" },
        textStyle: { color: "#64748b", fontSize: 9 },
      },
    ],
    series,
  };
}

function trimHist(points, n = 120) {
  return points.length > n ? points.slice(-n) : points;
}

function buildForecastSeries(name, histTrim, fc, lastClose, color) {
  return [
    {
      name: `${name} 预测中枢`,
      type: "line",
      data: [
        ...histTrim.map((_, i) => (i === histTrim.length - 1 ? lastClose : null)),
        ...fc.map((p) => Number(p.price)),
      ],
      showSymbol: false,
      lineStyle: { width: 2, type: "dashed", color },
      connectNulls: false,
    },
    {
      name: `${name} 预测带`,
      type: "line",
      data: [...histTrim.map(() => null), ...fc.map((p) => Number(p.high))],
      showSymbol: false,
      lineStyle: { width: 1, type: "dotted", color: "#94a3b8" },
      connectNulls: false,
    },
    {
      name: `${name} 预测下沿`,
      type: "line",
      data: [...histTrim.map(() => null), ...fc.map((p) => Number(p.low))],
      showSymbol: false,
      lineStyle: { width: 1, type: "dotted", color: "#94a3b8" },
      connectNulls: false,
    },
  ];
}

function buildOption(ceaPayload, ccerPayload) {
  const wantCea = showCea.value && ceaPayload;
  const wantCcer = showCcer.value && ccerPayload;
  const isForecast = chartKind.value === "forecast";

  if (isForecast) {
    const ceaHist = wantCea ? trimHist(ceaPayload.points || []) : [];
    const ceaFc = wantCea ? ceaPayload.forecast_points || [] : [];
    const ccerHist = wantCcer ? trimHist(ccerPayload.points || []) : [];
    const ccerFc = wantCcer ? ccerPayload.forecast_points || [] : [];

    // 主时间轴：优先 CEA，否则 CCER
    const primaryIsCea = wantCea;
    const histTrim = primaryIsCea ? ceaHist : ccerHist;
    const fc = primaryIsCea ? ceaFc : ccerFc;
    const xs = [...histTrim.map((p) => p.t), ...fc.map((p) => p.t)];
    const candleHist = buildCandleSeries(histTrim);
    const candles = [...candleHist, ...fc.map(() => "-")];
    const points = [...histTrim, ...fc.map(() => ({ volume: null }))];
    const lastHistClose =
      candleHist.length && Array.isArray(candleHist[candleHist.length - 1])
        ? candleHist[candleHist.length - 1][1]
        : Number(histTrim[histTrim.length - 1]?.price);

    const primaryName = primaryIsCea ? "CEA" : "CCER";
    const forecastSeries = buildForecastSeries(
      primaryName,
      histTrim,
      fc,
      lastHistClose,
      "#c2410c"
    );

    let secondaryName = null;
    let secondaryYs = null;
    if (wantCea && wantCcer) {
      secondaryName = primaryIsCea ? "CCER" : "CEA";
      const otherPts = primaryIsCea
        ? [...ccerHist, ...ccerFc]
        : [...ceaHist, ...ceaFc];
      secondaryYs = alignPricesToXs(xs, otherPts);
    }

    const title =
      wantCea && wantCcer
        ? "CEA / CCER 同期预测"
        : wantCea
          ? ceaPayload?.title || "CEA 日度预测"
          : ccerPayload?.title || "CCER 日度预测";

    const startPct = Math.max(0, 100 - (100 * (fc.length + 40)) / Math.max(xs.length, 1));
    return buildPanelsOption({
      title,
      xs,
      primaryName,
      primaryCandles: candles,
      primaryPoints: points,
      secondaryName,
      secondaryYs,
      forecastSeries,
      startPct,
    });
  }

  // 日K：按日期并集对齐
  const ceaPts = wantCea ? ceaPayload.points || [] : [];
  const ccerPts = wantCcer ? ccerPayload.points || [] : [];
  const xs = unionXs(ceaPts, ccerPts);
  if (!xs.length) {
    return {
      title: { text: "暂无行情数据", left: 0, top: 0, textStyle: { fontSize: 11, color: "#64748b" } },
      series: [],
    };
  }
  const primaryIsCea = wantCea;
  const primaryPts = primaryIsCea ? ceaPts : ccerPts;
  const primaryName = primaryIsCea ? "CEA" : "CCER";
  const primaryCandles = alignCandlesToXs(xs, primaryPts);
  const primaryPoints = alignRawPointsToXs(xs, primaryPts);

  let secondaryName = null;
  let secondaryYs = null;
  if (wantCea && wantCcer) {
    secondaryName = "CCER";
    secondaryYs = alignPricesToXs(xs, ccerPts);
  }

  const title =
    wantCea && wantCcer
      ? "CEA 蜡烛图 / CCER 同期折线"
      : wantCea
        ? ceaPayload?.title || "CEA 日K线（蜡烛图）"
        : ccerPayload?.title || "CCER 日K线（蜡烛图）";

  const startPct = Math.max(0, 100 - (90 / Math.max(xs.length, 1)) * 100);
  return buildPanelsOption({
    title,
    xs,
    primaryName,
    primaryCandles,
    primaryPoints,
    secondaryName,
    secondaryYs,
    startPct,
  });
}

async function ensureChart() {
  if (!chartHost.value) return null;
  const echarts = await loadEcharts();
  if (!chart) {
    chart = echarts.init(chartHost.value, undefined, { renderer: "canvas" });
  }
  return chart;
}

function payloadOk(data) {
  return (
    data?.ok &&
    ((data.points || []).length > 0 || (data.forecast_points || []).length > 0)
  );
}

async function fetchCea(kind, { force = false } = {}) {
  if (kind === "forecast") {
    const m = forecastMethod.value || "rule";
    if (!force && sharedCeaForecastCache[m]) return sharedCeaForecastCache[m];
    const data = await fetchCeaKline("forecast", { method: m });
    if (payloadOk(data)) sharedCeaForecastCache[m] = data;
    return data;
  }
  if (!force && sharedCeaCache[kind]) return sharedCeaCache[kind];
  const data = await fetchCeaKline(kind);
  if (payloadOk(data)) sharedCeaCache[kind] = data;
  return data;
}

async function fetchCcer(kind, { force = false } = {}) {
  if (kind === "forecast") {
    const m = forecastMethod.value || "rule";
    if (!force && sharedCcerForecastCache[m]) return sharedCcerForecastCache[m];
    const data = await fetchCcerKline("forecast", { method: m });
    if (payloadOk(data)) sharedCcerForecastCache[m] = data;
    return data;
  }
  const k = "daily";
  if (!force && sharedCcerCache[k]) return sharedCcerCache[k];
  const data = await fetchCcerKline(k);
  if (payloadOk(data)) sharedCcerCache[k] = data;
  return data;
}

async function renderSeries(ceaPayload, ccerPayload) {
  await nextTick();
  const inst = await ensureChart();
  if (!inst) return;
  if (!ceaPayload && !ccerPayload) return;
  try {
    inst.setOption(buildOption(ceaPayload, ccerPayload), true);
    inst.resize();
    requestAnimationFrame(() => inst.resize());
    setTimeout(() => inst.resize(), 120);
  } catch (e) {
    console.error("[CarbonCeaQuoteChart] setOption failed", e);
    throw e;
  }
}

async function loadKind(kind, { force = false, syncMarket = force } = {}) {
  if (!showCea.value && !showCcer.value) {
    ui.warning("请至少选择 CEA 或 CCER");
    return;
  }

  loading.value = true;
  try {
    if (syncMarket) {
      try {
        await syncMarketQuotes();
        emit("market-synced");
      } catch (e) {
        if (!isRouteAbortError(e)) {
          ui.warning(e?.message || "行情同步失败，将使用已有本地数据");
        }
      }
      sharedCeaCache.daily = null;
      sharedCcerCache.daily = null;
      for (const k of Object.keys(sharedCeaForecastCache)) delete sharedCeaForecastCache[k];
      for (const k of Object.keys(sharedCcerForecastCache)) delete sharedCcerForecastCache[k];
    } else if (force) {
      sharedCeaCache.daily = null;
      sharedCcerCache.daily = null;
      for (const k of Object.keys(sharedCeaForecastCache)) delete sharedCeaForecastCache[k];
      for (const k of Object.keys(sharedCcerForecastCache)) delete sharedCcerForecastCache[k];
    }

    let ceaData = null;
    let ccerData = null;
    const tasks = [];

    if (showCea.value) {
      tasks.push(
        fetchCea(kind, { force }).then((d) => {
          ceaData = d;
        })
      );
    } else {
      ceaMeta.value = null;
    }

    if (showCcer.value) {
      tasks.push(
        fetchCcer(kind, { force }).then((d) => {
          ccerData = d;
        })
      );
    } else {
      ccerMeta.value = null;
    }

    await Promise.all(tasks);

    const ceaOk = showCea.value && payloadOk(ceaData);
    const ccerOk = showCcer.value && payloadOk(ccerData);

    if (showCea.value) ceaMeta.value = ceaData;
    if (showCcer.value) ccerMeta.value = ccerData;

    if (!ceaOk && !ccerOk) {
      ui.warning(kind === "forecast" ? "暂无法生成至年底预测" : "暂无日线数据");
      return;
    }
    if (showCea.value && !ceaOk && showCcer.value && ccerOk) {
      ui.warning("CEA 行情暂不可用，仅显示 CCER");
    }
    if (showCcer.value && !ccerOk && ceaOk) {
      ui.warning("CCER 行情暂不可用，仅显示 CEA");
    }

    await renderSeries(ceaOk ? ceaData : null, ccerOk ? ccerData : null);
  } catch (e) {
    if (!isRouteAbortError(e)) ui.error(e?.message || "行情加载失败");
  } finally {
    loading.value = false;
  }
}

function redrawFromCache() {
  const kind = chartKind.value;
  let cea = null;
  let ccer = null;
  if (kind === "forecast") {
    const m = forecastMethod.value || "rule";
    cea = showCea.value && payloadOk(sharedCeaForecastCache[m]) ? sharedCeaForecastCache[m] : null;
    ccer =
      showCcer.value && payloadOk(sharedCcerForecastCache[m]) ? sharedCcerForecastCache[m] : null;
  } else {
    cea = showCea.value && payloadOk(sharedCeaCache[kind]) ? sharedCeaCache[kind] : null;
    ccer = showCcer.value && payloadOk(sharedCcerCache.daily) ? sharedCcerCache.daily : null;
  }
  if (cea || ccer) renderSeries(cea, ccer);
  else loadKind(kind);
}

function onToggleCea(checked) {
  if (!checked && !showCcer.value) {
    ui.warning("请至少保留一个品种");
    return;
  }
  showCea.value = !!checked;
  loadKind(chartKind.value);
}

function onToggleCcer(checked) {
  if (!checked && !showCea.value) {
    ui.warning("请至少保留一个品种");
    return;
  }
  showCcer.value = !!checked;
  loadKind(chartKind.value);
}

watch(chartKind, (k) => {
  loadKind(k);
});

watch(forecastMethod, () => {
  if (chartKind.value === "forecast") {
    loadKind("forecast", { force: true, syncMarket: false });
  }
});

watch([showMa, showVol, showMacd, showRsi], () => {
  redrawFromCache();
});

onMounted(async () => {
  await loadKind(chartKind.value);
  if (typeof ResizeObserver !== "undefined" && chartHost.value) {
    resizeObs = new ResizeObserver(() => chart?.resize());
    resizeObs.observe(chartHost.value);
  }
});

onUnmounted(() => {
  resizeObs?.disconnect();
  resizeObs = null;
  chart?.dispose();
  chart = null;
});

defineExpose({
  refresh: () => loadKind(chartKind.value, { force: true, syncMarket: true }),
  reloadLocal: () => loadKind(chartKind.value, { force: true, syncMarket: false }),
  resize: () => {
    chart?.resize();
  },
  getSourceLines: () => sourceLines.value,
});
</script>

<template>
  <div class="cea-quote">
    <div class="cea-quote__head">
      <n-space align="center" :wrap="true" :size="8">
        <n-button-group size="tiny">
          <n-button
            v-for="t in kindTabs"
            :key="t.value"
            :type="chartKind === t.value ? 'primary' : 'default'"
            :disabled="t.disabled"
            :secondary="chartKind !== t.value"
            @click="chartKind = t.value"
          >
            {{ t.label }}
          </n-button>
        </n-button-group>
        <n-select
          v-if="chartKind === 'forecast'"
          v-model:value="forecastMethod"
          size="tiny"
          :options="forecastMethodOptions"
          style="width: 280px"
          :consistent-menu-width="false"
        >
          <template #option="{ option }">
            <div class="cea-quote__opt">
              <div class="cea-quote__opt-title">{{ option.label }}</div>
              <div class="cea-quote__opt-desc">{{ option.description }}</div>
            </div>
          </template>
        </n-select>
      </n-space>
      <n-button size="tiny" quaternary :loading="loading" @click="loadKind(chartKind, { force: true })">
        <template #icon><n-icon :component="RefreshOutline" /></template>
        刷新
      </n-button>
    </div>

    <div class="cea-quote__toolbar">
      <span class="cea-quote__tb-label">品种</span>
      <n-checkbox :checked="showCea" size="small" @update:checked="onToggleCea">CEA</n-checkbox>
      <n-checkbox :checked="showCcer" size="small" @update:checked="onToggleCcer">CCER</n-checkbox>
      <template v-if="showIndicators">
        <span class="cea-quote__tb-sep" aria-hidden="true">|</span>
        <span class="cea-quote__tb-label">更多指标</span>
        <n-checkbox v-model:checked="showMa" size="small">MA5/10/20</n-checkbox>
        <n-checkbox v-model:checked="showVol" size="small">成交量</n-checkbox>
        <n-checkbox v-model:checked="showMacd" size="small">MACD</n-checkbox>
        <n-checkbox v-model:checked="showRsi" size="small">RSI14</n-checkbox>
      </template>
    </div>

    <div v-if="forecastSummary && chartKind === 'forecast'" class="cea-quote__fc-kpis">
      <div class="cea-kpi">
        <div class="cea-kpi__l">现价锚点</div>
        <div class="cea-kpi__v">{{ forecastSummary.last_close }}</div>
      </div>
      <div class="cea-kpi">
        <div class="cea-kpi__l">预测年底</div>
        <div class="cea-kpi__v">{{ forecastSummary.year_end_price }}</div>
        <div class="cea-kpi__s">
          {{ forecastSummary.year_end_low }} – {{ forecastSummary.year_end_high }}
        </div>
      </div>
      <div class="cea-kpi">
        <div class="cea-kpi__l">预测高点</div>
        <div class="cea-kpi__v">{{ forecastSummary.peak_price }}</div>
        <div class="cea-kpi__s">{{ forecastSummary.peak_date }}</div>
      </div>
      <div class="cea-kpi">
        <div class="cea-kpi__l">预测低点</div>
        <div class="cea-kpi__v">{{ forecastSummary.trough_price }}</div>
        <div class="cea-kpi__s">{{ forecastSummary.trough_date }}</div>
      </div>
      <div class="cea-kpi">
        <div class="cea-kpi__l">预测交易日</div>
        <div class="cea-kpi__v">{{ forecastSummary.trading_days }}</div>
        <div class="cea-kpi__s">至 {{ forecastSummary.end_date }}</div>
      </div>
    </div>

    <n-spin :show="loading">
      <div
        ref="chartHost"
        class="cea-quote__chart"
        :class="{ 'cea-quote__chart--tall': showIndicators }"
      />
    </n-spin>
  </div>
</template>

<style scoped>
.cea-quote {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cea-quote__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.cea-quote__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  font-size: 12px;
  line-height: 1.3;
}
.cea-quote__toolbar :deep(.n-checkbox) {
  font-size: 12px;
}
.cea-quote__toolbar :deep(.n-checkbox .n-checkbox__label) {
  font-size: 12px;
  padding-left: 6px;
}
.cea-quote__tb-label {
  color: var(--n-text-color-3);
  font-size: 12px;
  flex-shrink: 0;
}
.cea-quote__tb-sep {
  color: var(--n-border-color);
  font-size: 12px;
  margin: 0 2px;
  user-select: none;
}
.cea-quote__opt {
  padding: 4px 0;
  max-width: 300px;
}
.cea-quote__opt-title {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.35;
}
.cea-quote__opt-desc {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--n-text-color-3);
  white-space: normal;
}
.cea-quote__source :deep(.n-alert-body) {
  padding-top: 4px;
}
.cea-quote__source-block + .cea-quote__source-block {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--n-border-color);
}
.cea-quote__source-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.cea-quote__source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--n-text-color-3);
}
.cea-quote__fc-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
}
.cea-kpi {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--n-color-embedded);
}
.cea-kpi__l {
  font-size: 12px;
  color: var(--n-text-color-3);
}
.cea-kpi__v {
  font-size: 18px;
  font-weight: 600;
  margin-top: 2px;
}
.cea-kpi__s {
  font-size: 11px;
  color: var(--n-text-color-3);
  margin-top: 2px;
}
.cea-quote__chart {
  width: 100%;
  height: 400px;
  min-height: 280px;
}
.cea-quote__chart--tall {
  height: 560px;
}
</style>
