import { api, fetchWithTimeout, getApiBase, getToken } from "./http.js";
import { downloadBlob } from "../utils/downloadBlob.js";

export async function fetchAgentSkillRegistry({ includeDisabled = true, catalogOnly = true } = {}) {
  const params = new URLSearchParams();
  if (!includeDisabled) params.set("include_disabled", "false");
  if (!catalogOnly) params.set("catalog_only", "false");
  const qs = params.toString();
  return api(`/api/v1/admin/agent-skills/registry${qs ? `?${qs}` : ""}`);
}

export async function fetchAgentTools() {
  return api("/api/v1/admin/agent-skills/tools");
}

export async function patchBuiltinSkill(name, { enabled, title, description }) {
  const body = { enabled };
  if (title !== undefined) body.title = title;
  if (description !== undefined) body.description = description;
  return api(`/api/v1/admin/agent-skills/builtin/${encodeURIComponent(name)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function invokeAgentSkill({ skillName, toolName = "search", params = {} }) {
  return api("/api/v1/admin/agent-skills/invoke", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      skill_name: skillName,
      tool_name: toolName,
      params,
    }),
  });
}

export async function fetchAgentSkills({ page = 1, pageSize = 15, q = "", enabled = null } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q) params.set("q", q);
  if (enabled === true) params.set("enabled", "true");
  if (enabled === false) params.set("enabled", "false");
  return api(`/api/v1/admin/agent-skills?${params}`);
}

export async function fetchAgentSkill(skillId) {
  return api(`/api/v1/admin/agent-skills/${skillId}`);
}

export async function fetchAgentSkillFile(skillId, filePath) {
  const encoded = filePath.split("/").map(encodeURIComponent).join("/");
  return api(`/api/v1/admin/agent-skills/${skillId}/files/${encoded}`);
}

export async function downloadAgentSkillZip(skillId, filename = "skill.zip") {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetchWithTimeout(
    `${getApiBase()}/api/v1/admin/agent-skills/${skillId}/download`,
    { headers },
    60_000
  );
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    throw new Error(json?.message || res.statusText || "下载失败");
  }
  const blob = await res.blob();
  downloadBlob(blob, filename);
}

export async function uploadAgentSkillZip(file, { replaceExisting = true } = {}) {
  const form = new FormData();
  form.append("file", file);
  form.append("replace_existing", replaceExisting ? "true" : "false");
  return api("/api/v1/admin/agent-skills/upload/zip", { method: "POST", body: form });
}

export async function uploadAgentSkillFolder(fileList, { replaceExisting = true } = {}) {
  const form = new FormData();
  for (const file of fileList) {
    form.append("files", file);
    const rel = file.webkitRelativePath || file.name;
    form.append("paths", rel);
  }
  form.append("replace_existing", replaceExisting ? "true" : "false");
  return api("/api/v1/admin/agent-skills/upload/folder", { method: "POST", body: form });
}

export async function updateAgentSkill(skillId, payload) {
  return api(`/api/v1/admin/agent-skills/${skillId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateAgentSkillFile(skillId, filePath, content) {
  const encoded = filePath.split("/").map(encodeURIComponent).join("/");
  return api(`/api/v1/admin/agent-skills/${skillId}/files/${encoded}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export async function createGeneratedAgentSkill({
  name,
  description,
  skillMdBody,
  replaceExisting = false,
}) {
  return api("/api/v1/admin/agent-skills/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      description,
      skill_md_body: skillMdBody,
      replace_existing: replaceExisting,
    }),
  });
}

export async function fetchAgentMemory() {
  return api("/api/v1/ai-chat/agent-memory");
}

export async function updateAgentMemory(content) {
  return api("/api/v1/ai-chat/agent-memory", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export async function clearAgentMemory() {
  return api("/api/v1/ai-chat/agent-memory", { method: "DELETE" });
}

export async function deleteAgentSkill(skillId) {
  return api(`/api/v1/admin/agent-skills/${skillId}`, { method: "DELETE" });
}

export async function fetchAgentProfiles() {
  return api("/api/v1/admin/agent-skills/agents");
}

export async function fetchRoutingSkillsMd() {
  return api("/api/v1/admin/agent-skills/routing/skills.md");
}

export async function fetchRoutingAgentsMd() {
  return api("/api/v1/admin/agent-skills/routing/agents.md");
}

export async function fetchAgentProfile(agentId) {
  return api(`/api/v1/admin/agent-skills/agents/${encodeURIComponent(agentId)}`);
}

export async function fetchAgentProfileFile(agentId, filePath) {
  const encoded = filePath.split("/").map(encodeURIComponent).join("/");
  return api(
    `/api/v1/admin/agent-skills/agents/${encodeURIComponent(agentId)}/files/${encoded}`
  );
}

export async function updateAgentProfileFile(agentId, filePath, content) {
  const encoded = filePath.split("/").map(encodeURIComponent).join("/");
  return api(
    `/api/v1/admin/agent-skills/agents/${encodeURIComponent(agentId)}/files/${encoded}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }
  );
}

export async function patchAgentProfile(agentId, payload) {
  return api(`/api/v1/admin/agent-skills/agents/${encodeURIComponent(agentId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── 知识库文件夹挂载 ──────────────────────────────────

export async function fetchKnowledgeMounts(agentId) {
  return api(`/api/v1/admin/agent-skills/agents/${encodeURIComponent(agentId)}/knowledge-mounts`);
}

export async function addKnowledgeMount(agentId, { datasetId, folderId, scope, label }) {
  return api(`/api/v1/admin/agent-skills/agents/${encodeURIComponent(agentId)}/knowledge-mounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset_id: datasetId,
      folder_id: folderId,
      scope,
      label: label || undefined,
    }),
  });
}

export async function removeKnowledgeMount(agentId, mountId) {
  return api(`/api/v1/admin/agent-skills/agents/${encodeURIComponent(agentId)}/knowledge-mounts/${mountId}`, {
    method: "DELETE",
  });
}
