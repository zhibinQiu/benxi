/** 理财助手 API */

import { api } from "./http.js";

/** ── 市场指数 ── */

export function fetchMarketIndices() {
  return api("/api/v1/finance/market-indices");
}

/** ── A 股 ── */

export function searchStocks(query) {
  return api(`/api/v1/finance/stock/search?q=${encodeURIComponent(query)}`);
}

export function fetchStockQuotes(codes) {
  return api(
    `/api/v1/finance/stock/quote?codes=${encodeURIComponent(codes.join(","))}`
  );
}

export function fetchStockKline(code, ktype = "day") {
  return api(`/api/v1/finance/stock/kline?code=${code}&ktype=${ktype}`);
}

/** ── 基金 ── */

export function searchFunds(query) {
  return api(`/api/v1/finance/fund/search?q=${encodeURIComponent(query)}`);
}

export function fetchFundQuote(code) {
  return api(`/api/v1/finance/fund/quote?code=${code}`);
}

export function fetchFundHistory(code, period = "3m") {
  return api(
    `/api/v1/finance/fund/history?code=${code}&period=${period}`
  );
}

/** ── 虚拟币 ── */

export function fetchCryptoList(perPage = 50) {
  return api(`/api/v1/finance/crypto/list?per_page=${perPage}`);
}

export function fetchCryptoQuote(coinId) {
  return api(`/api/v1/finance/crypto/quote?coin_id=${encodeURIComponent(coinId)}`);
}

export function fetchCryptoHistory(coinId, days = 7) {
  return api(
    `/api/v1/finance/crypto/history?coin_id=${encodeURIComponent(coinId)}&days=${days}`
  );
}

/** ── 自选清单 ── */

export function fetchWatchlist() {
  return api("/api/v1/finance/watchlist");
}

export function addToWatchlist(assetType, assetCode, assetName) {
  return api("/api/v1/finance/watchlist", {
    method: "POST",
    body: JSON.stringify({ asset_type: assetType, asset_code: assetCode, asset_name: assetName }),
  });
}

export function removeFromWatchlist(itemId) {
  return api(`/api/v1/finance/watchlist/${itemId}`, { method: "DELETE" });
}

/** ── 报告任务 ── */

export function submitReport(payload) {
  return api("/api/v1/finance/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchReports(status = "", limit = 50, offset = 0) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", limit);
  params.set("offset", offset);
  return api(`/api/v1/finance/reports?${params.toString()}`);
}

export function cancelReport(reportId) {
  return api(`/api/v1/finance/report/${reportId}/cancel`, { method: "POST" });
}

export function fetchReportDetail(reportId) {
  return api(`/api/v1/finance/report/${reportId}`);
}

/** 公开分享链接（无需登录即可打开） */
export function getReportShareUrl(shareToken) {
  if (!shareToken) return "";
  // 与 http.js 默认一致：浏览器侧走同源 /ai 反代
  const base = "/ai";
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${base}/api/v1/share/finance/${shareToken}`;
}

/** 在线查看报告：打开可独立访问的公开分享 URL */
export async function viewReport(reportId, shareToken) {
  const { openExternal } = await import("../utils/openExternal.js");
  const { getApiBase, getToken } = await import("./http.js");

  let token = shareToken;
  if (!token) {
    try {
      const detail = await fetchReportDetail(reportId);
      token = detail?.share_token || detail?.data?.share_token;
    } catch {
      /* ignore */
    }
  }
  if (token) {
    openExternal(getReportShareUrl(token));
    return;
  }

  // 兜底：登录态跳转接口（会 302 到公开链接）
  const auth = getToken();
  const base = (getApiBase() || "/ai").replace(/\/$/, "");
  const url = `${window.location.origin}${base}/api/v1/finance/report/${reportId}/view`;
  if (auth) {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${auth}` },
      redirect: "manual",
    });
    const loc = res.headers.get("Location");
    if (loc) {
      openExternal(loc.startsWith("http") ? loc : `${window.location.origin}${loc}`);
      return;
    }
  }
  openExternal(url);
}

export async function deleteReport(reportId) {
  return api(`/api/v1/finance/report/${reportId}`, { method: "DELETE" });
}

/** 将已完成报告加入个人级文档库（未分类） */
export function importReportToLibrary(reportId) {
  return api(`/api/v1/finance/report/${reportId}/import-library`, {
    method: "POST",
  });
}

/** 生成/覆盖报告公开分享令牌 */
export function shareReport(reportId, { regenerate = true } = {}) {
  const q = regenerate ? "?regenerate=true" : "?regenerate=false";
  return api(`/api/v1/finance/report/${reportId}/share${q}`, { method: "POST" });
}

/** 撤销报告公开分享链接 */
export function unshareReport(reportId) {
  return api(`/api/v1/finance/report/${reportId}/share`, { method: "DELETE" });
}

export async function downloadReport(reportId, fmt = "md") {
  const { getApiBase, getToken } = await import("./http.js");
  const { default: downloadBlob } = await import("../utils/downloadBlob.js");
  const base = getApiBase();
  const token = getToken();
  const res = await fetch(
    `${base}/api/v1/finance/report/${reportId}/download?fmt=${fmt}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  );
  if (!res.ok) throw new Error("下载失败");
  const blob = await res.blob();
  const ext = fmt === "docx" ? ".docx" : fmt === "pdf" ? ".pdf" : ".md";
  downloadBlob(blob, `report_${reportId.slice(0, 8)}${ext}`);
}

/** 导出报告为 PDF（打开公开页后触发打印） */
export async function exportReportPdf(reportId, shareToken) {
  const { openExternal } = await import("../utils/openExternal.js");
  let token = shareToken;
  if (!token) {
    try {
      const detail = await fetchReportDetail(reportId);
      token = detail?.share_token || detail?.data?.share_token;
    } catch {
      /* ignore */
    }
  }
  if (!token) throw new Error("缺少分享链接");
  // 打开公开页，用户可在浏览器中打印为 PDF
  openExternal(getReportShareUrl(token));
}
