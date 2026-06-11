/** 平台系统与功能 REST API */
import { api } from "./http.js";

export async function fetchSystemFeatures() {
  return api("/api/v1/system/features");
}

export async function fetchDashboardStats() {
  return api("/api/v1/system/dashboard-stats");
}

export async function fetchFeatureEmbedMeta(featureId) {
  return api(`/api/v1/system/features/${encodeURIComponent(featureId)}/embed-meta`);
}
