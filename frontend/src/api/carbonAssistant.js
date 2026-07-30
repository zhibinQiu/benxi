/** 碳资产报告 — 资讯报告 API（履约策略见 carbonCompliance.js） */

import { api } from "./http.js";

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

/** 公开分享链接（维基风 HTML，与理财助手同款渲染） */
export function getCarbonReportShareUrl(shareToken) {
  if (!shareToken) return "";
  const base = "/ai";
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${base}/api/v1/share/carbon/${shareToken}`;
}

export async function viewCarbonReport(reportId, shareToken) {
  const { openExternal } = await import("../utils/openExternal.js");
  let token = shareToken;
  if (!token && reportId) {
    try {
      const detail = await fetchCarbonReportDetail(reportId);
      token = detail?.share_token;
    } catch {
      /* ignore */
    }
  }
  if (!token) throw new Error("无法获取报告分享链接");
  openExternal(getCarbonReportShareUrl(token));
}

export async function downloadCarbonReport(reportId) {
  const { getApiBase, getToken } = await import("./http.js");
  const { downloadBlob } = await import("../utils/downloadBlob.js");
  const base = getApiBase();
  const token = getToken();
  const res = await fetch(`${base}/api/v1/carbon-assistant/report/${reportId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("下载失败");
  const blob = await res.blob();
  downloadBlob(blob, `carbon_report_${String(reportId).slice(0, 8)}.md`);
}
