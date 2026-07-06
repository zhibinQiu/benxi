/** 模型与资源健康 REST API */
import { api } from "./http.js";

export async function fetchModelSettings() {
  return api("/api/v1/admin/model-settings");
}

export async function updateModelSettings(payload) {
  return api("/api/v1/admin/model-settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchResourceHealth() {
  return api("/api/v1/admin/model-settings/health");
}

export async function testResourceHealth(resourceId, draft = {}, timeoutMs) {
  return api("/api/v1/admin/model-settings/health/test", {
    method: "POST",
    body: JSON.stringify({ resource_id: resourceId, draft }),
    ...(timeoutMs != null ? { timeoutMs } : {}),
  });
}
