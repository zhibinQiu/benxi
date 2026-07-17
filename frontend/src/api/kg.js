/** 知识图谱（KG）REST API — Neo4j 版实体/关系/图谱/抽取 */
import { api } from "./http.js";

// ── 元数据 ───────────────────────────────────────────────────────────────

export function fetchKgMeta() {
  return api("/api/v1/kg/meta");
}

// ── 实体 CRUD ───────────────────────────────────────────────────────────

export function fetchKgEntities({ typeCode, q, limit, offset } = {}) {
  const params = new URLSearchParams();
  if (typeCode) params.set("type_code", typeCode);
  if (q) params.set("q", q);
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  const qs = params.toString();
  return api(`/api/v1/kg/entities${qs ? `?${qs}` : ""}`);
}

export function fetchKgEntity(entityId) {
  return api(`/api/v1/kg/entities/${entityId}`);
}

export function createKgEntity(body) {
  return api("/api/v1/kg/entities", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateKgEntity(entityId, body) {
  return api(`/api/v1/kg/entities/${entityId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteKgEntity(entityId) {
  return api(`/api/v1/kg/entities/${entityId}`, { method: "DELETE" });
}

// ── 关系 CRUD ───────────────────────────────────────────────────────────

export function fetchKgRelations({ entityId, typeCode } = {}) {
  const params = new URLSearchParams();
  if (entityId) params.set("entity_id", entityId);
  if (typeCode) params.set("type_code", typeCode);
  const qs = params.toString();
  return api(`/api/v1/kg/relations${qs ? `?${qs}` : ""}`);
}

export function createKgRelation(body) {
  return api("/api/v1/kg/relations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteKgRelation(relationId) {
  return api(`/api/v1/kg/relations/${relationId}`, { method: "DELETE" });
}

export function updateKgRelation(relationId, body) {
  return api(`/api/v1/kg/relations/${relationId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ── 图谱可视化 ───────────────────────────────────────────────────────────

export function fetchKgGraph({ focusEntityId, depth } = {}) {
  const params = new URLSearchParams();
  if (focusEntityId) params.set("focus_entity_id", focusEntityId);
  if (depth) params.set("depth", String(depth));
  const qs = params.toString();
  return api(`/api/v1/kg/graph${qs ? `?${qs}` : ""}`);
}

export function clearKgGraph() {
  return api("/api/v1/kg/graph/clear", { method: "POST" });
}

export function reasonKgGraph(question, { depth = 3, includeInferred = true } = {}) {
  return api("/api/v1/kg/graph/reason", {
    method: "POST",
    body: JSON.stringify({
      question,
      depth,
      include_inferred: includeInferred,
    }),
  });
}

// ── 平台数据同步 ────────────────────────────────────────────────

export function syncKgOrg() {
  return api("/api/v1/kg/sync/org", { method: "POST" });
}

export function syncKgAgents() {
  return api("/api/v1/kg/sync/agents", { method: "POST" });
}

export function syncKgMemory() {
  return api("/api/v1/kg/sync/memory", { method: "POST" });
}

export function syncKgAll() {
  return api("/api/v1/kg/sync/all", { method: "POST" });
}

// ── 文档内容抽取 ──────────────────────────────────────────────

export function extractKgDocuments({ maxDocs = 20 } = {}) {
  return api("/api/v1/kg/extract/documents", {
    method: "POST",
    body: JSON.stringify({ max_docs: maxDocs, scope: "knowledge" }),
  });
}

// ── LLM 抽取 ────────────────────────────────────────────────────────────

export function extractKgFromText(title, text, { sourceType = "manual", sourceId = null } = {}) {
  return api("/api/v1/kg/extract-from-text", {
    method: "POST",
    body: JSON.stringify({
      title,
      text,
      source_type: sourceType,
      source_id: sourceId,
    }),
  });
}
