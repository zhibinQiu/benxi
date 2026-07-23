/** 双碳履约策略 API */

import { api } from "./http.js";

const BASE = "/api/v1/carbon-assistant";

export function fetchComplianceMeta() {
  return api(`${BASE}/meta`);
}

export function fetchCarbonSettings() {
  return api(`${BASE}/settings`);
}

export function updateCarbonSettings(payload) {
  return api(`${BASE}/settings`, {
    method: "PUT",
    body: JSON.stringify({ payload }),
  });
}

export function listEnterprises() {
  return api(`${BASE}/enterprises`);
}

export function createEnterprise(body) {
  return api(`${BASE}/enterprises`, { method: "POST", body: JSON.stringify(body) });
}

export function updateEnterprise(id, body) {
  return api(`${BASE}/enterprises/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteEnterprise(id) {
  return api(`${BASE}/enterprises/${id}`, { method: "DELETE" });
}

export function listEmissions(enterpriseId) {
  return api(`${BASE}/enterprises/${enterpriseId}/emissions`);
}

export function upsertEmission(enterpriseId, body) {
  return api(`${BASE}/enterprises/${enterpriseId}/emissions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteEmission(enterpriseId, year) {
  return api(`${BASE}/enterprises/${enterpriseId}/emissions/${year}`, {
    method: "DELETE",
  });
}

export function listForecasts(enterpriseId) {
  return api(`${BASE}/enterprises/${enterpriseId}/forecasts`);
}

export function upsertForecast(enterpriseId, body) {
  return api(`${BASE}/enterprises/${enterpriseId}/forecasts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listCea(enterpriseId) {
  return api(`${BASE}/enterprises/${enterpriseId}/cea`);
}

export function upsertCea(enterpriseId, body) {
  return api(`${BASE}/enterprises/${enterpriseId}/cea`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteCea(enterpriseId, vintageYear) {
  return api(`${BASE}/enterprises/${enterpriseId}/cea/${vintageYear}`, {
    method: "DELETE",
  });
}

export function listCcer(enterpriseId) {
  return api(`${BASE}/enterprises/${enterpriseId}/ccer`);
}

export function upsertCcer(enterpriseId, body) {
  return api(`${BASE}/enterprises/${enterpriseId}/ccer`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteCcer(enterpriseId, holdingId) {
  return api(`${BASE}/enterprises/${enterpriseId}/ccer/${holdingId}`, {
    method: "DELETE",
  });
}

export function listMarketCea() {
  return api(`${BASE}/market/cea`);
}

export function upsertMarketCea(body) {
  return api(`${BASE}/market/cea`, { method: "POST", body: JSON.stringify(body) });
}

export function listMarketCcer() {
  return api(`${BASE}/market/ccer`);
}

export function upsertMarketCcer(body) {
  return api(`${BASE}/market/ccer`, { method: "POST", body: JSON.stringify(body) });
}

export function listMarketEnergy() {
  return api(`${BASE}/market/energy`);
}

export function upsertMarketEnergy(body) {
  return api(`${BASE}/market/energy`, { method: "POST", body: JSON.stringify(body) });
}

/** 外站拉取 CEA/CCER 并写入月度库 */
export function syncMarketQuotes() {
  return api(`${BASE}/market/sync`, { method: "POST", timeoutMs: 45_000 });
}

/** CEA 日线 / 分时 / 至年底预测折线序列；forecast 可传 method=rule|ets|sarimax|prophet */
export function fetchCeaKline(kind = "daily", { method } = {}) {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (method && kind === "forecast") params.set("method", method);
  const q = params.toString() ? `?${params}` : "";
  return api(`${BASE}/market/cea/kline${q}`, { timeoutMs: 45_000 });
}

/** CCER 日线 / 至年底预测折线序列 */
export function fetchCcerKline(kind = "daily", { method } = {}) {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (method && kind === "forecast") params.set("method", method);
  const q = params.toString() ? `?${params}` : "";
  return api(`${BASE}/market/ccer/kline${q}`, { timeoutMs: 60_000 });
}

/** 仅预测摘要 + 日度点列 */
export function fetchCeaForecast() {
  return api(`${BASE}/market/cea/forecast`, { timeoutMs: 45_000 });
}

export function runStrategy(enterpriseId, complianceYear) {
  return api(`${BASE}/enterprises/${enterpriseId}/strategy/run`, {
    method: "POST",
    body: JSON.stringify({ compliance_year: complianceYear }),
  });
}

export function listStrategyRuns(enterpriseId) {
  return api(`${BASE}/enterprises/${enterpriseId}/strategy/runs`);
}

export function listCarbonAlerts({ enterpriseId = "", unackedOnly = false } = {}) {
  const params = new URLSearchParams();
  if (enterpriseId) params.set("enterprise_id", enterpriseId);
  if (unackedOnly) params.set("unacked_only", "true");
  const qs = params.toString();
  return api(`${BASE}/alerts${qs ? `?${qs}` : ""}`);
}

export function ackCarbonAlert(alertId) {
  return api(`${BASE}/alerts/${alertId}/ack`, { method: "POST" });
}

export async function downloadStrategyRun(enterpriseId, runId) {
  const { getApiBase, getToken } = await import("./http.js");
  const { downloadBlob } = await import("../utils/downloadBlob.js");
  const base = getApiBase();
  const token = getToken();
  const res = await fetch(
    `${base}${BASE}/enterprises/${enterpriseId}/strategy/runs/${runId}/download`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  );
  if (!res.ok) throw new Error("下载失败");
  const blob = await res.blob();
  downloadBlob(blob, `strategy_${String(runId).slice(0, 8)}.md`);
}

export async function downloadImportTemplate(enterpriseId) {
  const { getApiBase, getToken } = await import("./http.js");
  const { downloadBlob } = await import("../utils/downloadBlob.js");
  const base = getApiBase();
  const token = getToken();
  const res = await fetch(`${base}${BASE}/enterprises/${enterpriseId}/import/template`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("模板下载失败");
  const blob = await res.blob();
  downloadBlob(blob, "carbon_import_template.xlsx");
}

export async function importEnterpriseExcel(enterpriseId, file) {
  const { getApiBase, getToken } = await import("./http.js");
  const base = getApiBase();
  const token = getToken();
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${base}${BASE}/enterprises/${enterpriseId}/import`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json?.message || json?.detail || "导入失败");
  return json?.data ?? json;
}

/** 可选：外站行情摘要 */
export function fetchTradingSnapshot(keyword = "") {
  const q = keyword ? `?keyword=${encodeURIComponent(keyword)}` : "";
  return api(`${BASE}/trading/snapshot${q}`, { timeoutMs: 30_000 });
}
