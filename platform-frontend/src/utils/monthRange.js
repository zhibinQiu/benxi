/** 月份区间工具：供网站收藏时间筛选滑块使用 */

export const SUBSCRIPTION_MONTH_LOOKBACK = 36;

export function startOfMonthTs(year, monthIndex) {
  return new Date(year, monthIndex, 1).getTime();
}

export function endOfMonthTs(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0, 23, 59, 59, 999).getTime();
}

/** @returns {{ year: number, month: number }} */
export function monthAtOffset(baseYear, baseMonth, offset) {
  const d = new Date(baseYear, baseMonth + offset, 1);
  return { year: d.getFullYear(), month: d.getMonth() };
}

export function buildSubscriptionMonthSpan(now = new Date()) {
  const endYear = now.getFullYear();
  const endMonth = now.getMonth();
  const start = monthAtOffset(endYear, endMonth, -(SUBSCRIPTION_MONTH_LOOKBACK - 1));
  return {
    baseYear: start.year,
    baseMonth: start.month,
    totalMonths: SUBSCRIPTION_MONTH_LOOKBACK,
    maxIndex: SUBSCRIPTION_MONTH_LOOKBACK - 1,
  };
}

export function monthIndexFromTs(baseYear, baseMonth, ts) {
  const d = new Date(ts);
  return (d.getFullYear() - baseYear) * 12 + (d.getMonth() - baseMonth);
}

export function tsRangeFromMonthIndices(baseYear, baseMonth, fromIdx, toIdx) {
  const from = monthAtOffset(baseYear, baseMonth, fromIdx);
  const to = monthAtOffset(baseYear, baseMonth, toIdx);
  return [startOfMonthTs(from.year, from.month), endOfMonthTs(to.year, to.month)];
}

export function formatMonthLabel(ts, locale = "zh-CN") {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleDateString(locale, { year: "numeric", month: "short" });
  } catch {
    return "";
  }
}
