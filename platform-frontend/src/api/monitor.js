/** 系统监控 REST API */
import { api } from "./http.js";

export async function fetchAuditLogs(limit = 100) {
  const q = new URLSearchParams({ limit: String(limit) });
  return api(`/api/v1/monitor/audit-logs?${q}`);
}

export async function fetchSystemMetrics() {
  return api("/api/v1/monitor/metrics");
}
