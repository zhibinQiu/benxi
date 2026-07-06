import { api } from "./http.js";

const BASE = "/api/v1/admin/agent-skills/mcp-skills";

export async function fetchMcpSkills() {
  return api(BASE);
}

export async function createMcpSkill(payload) {
  return api(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function patchMcpSkill(skillId, payload) {
  return api(`${BASE}/${encodeURIComponent(skillId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function syncMcpSkill(skillId) {
  return api(`${BASE}/${encodeURIComponent(skillId)}/sync`, {
    method: "POST",
  });
}

export async function deleteMcpSkill(skillId) {
  return api(`${BASE}/${encodeURIComponent(skillId)}`, {
    method: "DELETE",
  });
}

export async function fetchMcpServerInfo() {
  return api("/api/v1/mcp/info");
}
