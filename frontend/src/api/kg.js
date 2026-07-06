/** 知识图谱（本体）REST API */
import { api } from "./http.js";

export async function fetchKgMeta({ syncSystem = false } = {}) {
  const params = new URLSearchParams();
  if (syncSystem) params.set("sync_system", "true");
  const qs = params.toString();
  return api(`/api/v1/kg/meta${qs ? `?${qs}` : ""}`);
}

export async function createKgEntityFromDocument(documentId) {
  return api(`/api/v1/kg/entities/from-document/${documentId}`, { method: "POST" });
}

export async function fetchKgEntities({ typeId, q } = {}) {
  const params = new URLSearchParams();
  if (typeId) params.set("type_id", typeId);
  if (q) params.set("q", q);
  const qs = params.toString();
  return api(`/api/v1/kg/entities${qs ? `?${qs}` : ""}`);
}

export async function fetchKgEntity(entityId) {
  return api(`/api/v1/kg/entities/${entityId}`);
}

export async function createKgEntity(body) {
  return api("/api/v1/kg/entities", { method: "POST", body: JSON.stringify(body) });
}

export async function updateKgEntity(entityId, body) {
  return api(`/api/v1/kg/entities/${entityId}`, { method: "PATCH", body: JSON.stringify(body) });
}

export async function deleteKgEntity(entityId) {
  return api(`/api/v1/kg/entities/${entityId}`, { method: "DELETE" });
}

export async function batchDeleteKgEntities({ entityIds, typeId, q } = {}) {
  return api("/api/v1/kg/entities/batch-delete", {
    method: "POST",
    body: JSON.stringify({
      entity_ids: entityIds || [],
      type_id: typeId || null,
      q: q || null,
    }),
  });
}

export async function clearKgGraph() {
  return api("/api/v1/kg/graph/clear", { method: "POST" });
}

export async function fetchKgRelations({ entityId, relationTypeId } = {}) {
  const params = new URLSearchParams();
  if (entityId) params.set("entity_id", entityId);
  if (relationTypeId) params.set("relation_type_id", relationTypeId);
  const qs = params.toString();
  return api(`/api/v1/kg/relations${qs ? `?${qs}` : ""}`);
}

export async function createKgRelation(body) {
  return api("/api/v1/kg/relations", { method: "POST", body: JSON.stringify(body) });
}

export async function deleteKgRelation(relationId) {
  return api(`/api/v1/kg/relations/${relationId}`, { method: "DELETE" });
}

export async function fetchKgGraph({ focusEntityId, depth = 1 } = {}) {
  const params = new URLSearchParams();
  if (focusEntityId) params.set("focus_entity_id", focusEntityId);
  if (depth) params.set("depth", String(depth));
  const qs = params.toString();
  return api(`/api/v1/kg/graph${qs ? `?${qs}` : ""}`);
}

export async function createKgEntityType(body) {
  return api("/api/v1/kg/entity-types", { method: "POST", body: JSON.stringify(body) });
}

export async function updateKgEntityType(typeId, body) {
  return api(`/api/v1/kg/entity-types/${typeId}`, { method: "PATCH", body: JSON.stringify(body) });
}

export async function deleteKgEntityType(typeId) {
  return api(`/api/v1/kg/entity-types/${typeId}`, { method: "DELETE" });
}

export async function createKgRelationType(body) {
  return api("/api/v1/kg/relation-types", { method: "POST", body: JSON.stringify(body) });
}

export async function updateKgRelationType(typeId, body) {
  return api(`/api/v1/kg/relation-types/${typeId}`, { method: "PATCH", body: JSON.stringify(body) });
}

export async function deleteKgRelationType(typeId) {
  return api(`/api/v1/kg/relation-types/${typeId}`, { method: "DELETE" });
}

export async function extractKgFromText({ title, text, sourceType, sourceId } = {}) {
  return api("/api/v1/kg/extract-from-text", {
    method: "POST",
    body: JSON.stringify({
      title: title || "会议总结",
      text,
      source_type: sourceType || "meeting_summary",
      source_id: sourceId || null,
    }),
  });
}

export async function extractKgBatch({ scope = "knowledge", force = false } = {}) {
  return api("/api/v1/kg/extract/batch", {
    method: "POST",
    body: JSON.stringify({ scope, force }),
  });
}
