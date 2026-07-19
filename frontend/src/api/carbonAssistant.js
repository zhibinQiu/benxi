/** 双碳助手 API */

import { api } from "./http.js";

/** ── 碳交易 ── */

export function fetchTradingSnapshot(keyword = "") {
  const q = keyword ? `?keyword=${encodeURIComponent(keyword)}` : "";
  return api(`/api/v1/carbon-assistant/trading/snapshot${q}`);
}

export function fetchCarbonPrice(keyword = "", url = "") {
  const params = new URLSearchParams();
  if (keyword) params.set("keyword", keyword);
  if (url) params.set("url", url);
  const qs = params.toString();
  return api(`/api/v1/carbon-assistant/trading/price${qs ? `?${qs}` : ""}`);
}

export function fetchCarbonPolicy(keyword = "", url = "") {
  const params = new URLSearchParams();
  if (keyword) params.set("keyword", keyword);
  if (url) params.set("url", url);
  const qs = params.toString();
  return api(`/api/v1/carbon-assistant/trading/policy${qs ? `?${qs}` : ""}`);
}

export function fetchCarbonData(topic, keyword = "", url = "") {
  const params = new URLSearchParams({ topic });
  if (keyword) params.set("keyword", keyword);
  if (url) params.set("url", url);
  return api(`/api/v1/carbon-assistant/trading/data?${params.toString()}`);
}

/** ── 报告 / 策略 ── */

export function submitCarbonReport(payload) {
  return api("/api/v1/carbon-assistant/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchCarbonReports({ reportType = "", status = "", limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (reportType) params.set("report_type", reportType);
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return api(`/api/v1/carbon-assistant/reports?${params.toString()}`);
}

export function cancelCarbonReport(reportId) {
  return api(`/api/v1/carbon-assistant/report/${reportId}/cancel`, { method: "POST" });
}

export function fetchCarbonReportDetail(reportId) {
  return api(`/api/v1/carbon-assistant/report/${reportId}`);
}

export function deleteCarbonReport(reportId) {
  return api(`/api/v1/carbon-assistant/report/${reportId}`, { method: "DELETE" });
}

export function getCarbonReportShareUrl(shareToken) {
  if (!shareToken) return "";
  const base = "/ai";
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${base}/api/v1/share/carbon/${shareToken}`;
}

export async function viewCarbonReport(reportId, shareToken) {
  const { openExternal } = await import("../utils/openExternal.js");
  let token = shareToken;
  if (!token) {
    try {
      const detail = await fetchCarbonReportDetail(reportId);
      token = detail?.share_token || detail?.data?.share_token;
    } catch {
      /* ignore */
    }
  }
  if (token) {
    openExternal(getCarbonReportShareUrl(token));
    return;
  }
  const { getApiBase, getToken } = await import("./http.js");
  const auth = getToken();
  const base = (getApiBase() || "/ai").replace(/\/$/, "");
  const url = `${window.location.origin}${base}/api/v1/carbon-assistant/report/${reportId}/view`;
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

export async function downloadCarbonReport(reportId) {
  const { getApiBase, getToken } = await import("./http.js");
  const { default: downloadBlob } = await import("../utils/downloadBlob.js");
  const base = getApiBase();
  const token = getToken();
  const res = await fetch(
    `${base}/api/v1/carbon-assistant/report/${reportId}/download`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  );
  if (!res.ok) throw new Error("下载失败");
  const blob = await res.blob();
  downloadBlob(blob, `carbon_report_${String(reportId).slice(0, 8)}.md`);
}
