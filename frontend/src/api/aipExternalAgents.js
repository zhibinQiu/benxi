import { api } from "./http.js";

const BASE = "/api/v1/admin/agent-skills/external-agents";

export async function fetchExternalAgents() {
  return api(BASE);
}

export async function createExternalAgent(payload) {
  return api(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function patchExternalAgent(agentId, payload) {
  return api(`${BASE}/${encodeURIComponent(agentId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteExternalAgent(agentId) {
  return api(`${BASE}/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
  });
}
