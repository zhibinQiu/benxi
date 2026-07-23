/**
 * 碳行情技术指标（日线），算法与常见股票终端一致。
 */

/** 简单移动平均；不足窗口返回 null */
export function sma(values, period) {
  const out = new Array(values.length).fill(null);
  if (!period || period < 1) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null || Number.isNaN(v)) {
      sum = 0;
      continue;
    }
    sum += v;
    if (i >= period) {
      const old = values[i - period];
      if (old != null && !Number.isNaN(old)) sum -= old;
    }
    if (i >= period - 1) {
      let ok = true;
      for (let j = i - period + 1; j <= i; j++) {
        if (values[j] == null || Number.isNaN(values[j])) {
          ok = false;
          break;
        }
      }
      out[i] = ok ? +(sum / period).toFixed(4) : null;
    }
  }
  return out;
}

/** EMA；跳过前导空值，首段用 SMA 启动 */
export function ema(values, period) {
  const out = new Array(values.length).fill(null);
  if (!period || period < 1) return out;
  const k = 2 / (period + 1);
  let prev = null;
  const buf = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null || Number.isNaN(v)) {
      out[i] = null;
      continue;
    }
    if (prev == null) {
      buf.push(v);
      if (buf.length === period) {
        prev = buf.reduce((a, b) => a + b, 0) / period;
        out[i] = +prev.toFixed(4);
      }
    } else {
      prev = v * k + prev * (1 - k);
      out[i] = +prev.toFixed(4);
    }
  }
  return out;
}

/**
 * MACD：DIF = EMA(fast)-EMA(slow)，DEA = EMA(DIF, signal)，柱 = 2*(DIF-DEA)
 * 返回 { dif, dea, hist }
 */
export function calcMacd(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = ema(closes, fast);
  const emaSlow = ema(closes, slow);
  const dif = closes.map((_, i) => {
    if (emaFast[i] == null || emaSlow[i] == null) return null;
    return +(emaFast[i] - emaSlow[i]).toFixed(4);
  });
  const dea = ema(dif, signal);
  const hist = dif.map((d, i) => {
    if (d == null || dea[i] == null) return null;
    return +((d - dea[i]) * 2).toFixed(4);
  });
  return { dif, dea, hist };
}

/** RSI(period) */
export function calcRsi(closes, period = 14) {
  const out = new Array(closes.length).fill(null);
  if (closes.length < period + 1) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gain += d;
    else loss -= d;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out[period] =
    avgLoss === 0 ? 100 : +(100 - 100 / (1 + avgGain / avgLoss)).toFixed(2);
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    const g = d > 0 ? d : 0;
    const l = d < 0 ? -d : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    out[i] =
      avgLoss === 0 ? 100 : +(100 - 100 / (1 + avgGain / avgLoss)).toFixed(2);
  }
  return out;
}

export function closesFromCandles(candles) {
  return (candles || []).map((c) => {
    if (!c || c === "-" || !Array.isArray(c) || c[1] == null) return null;
    return Number(c[1]);
  });
}

export function volumesFromPoints(points) {
  return (points || []).map((p) => {
    const v = p?.volume;
    if (v == null || Number.isNaN(Number(v))) return null;
    return Number(v);
  });
}
