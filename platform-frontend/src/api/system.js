/** 平台系统与功能 REST API */
import { api, fetchWithTimeout, getApiBase } from "./http.js";

export async function fetchShowcaseFeatures() {
  const res = await fetchWithTimeout(`${getApiBase()}/api/v1/system/showcase-features`);
  if (!res.ok) return [];
  const json = await res.json().catch(() => ({}));
  if (json.code !== undefined && json.code !== 0) return [];
  return Array.isArray(json.data) ? json.data : [];
}

export async function fetchSystemFeatures() {
  return api("/api/v1/system/features");
}

export async function fetchDashboardStats() {
  return api("/api/v1/system/dashboard-stats");
}

export async function fetchFeatureEmbedMeta(featureId) {
  return api(`/api/v1/system/features/${encodeURIComponent(featureId)}/embed-meta`);
}

export async function fetchReleaseHighlights() {
  return api("/api/v1/system/release-highlights");
}
