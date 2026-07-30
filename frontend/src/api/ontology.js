/** 本体定义（Ontology）REST API — 实体类型/关系类型/公理管理 */
import { api } from "./http.js";

// ── 实体类型 ─────────────────────────────────────────────────────────────

export function fetchOntologyEntityTypes() {
  return api("/api/v1/ontology/entity-types");
}

export function createOntologyEntityType(body) {
  return api("/api/v1/ontology/entity-types", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateOntologyEntityType(code, body) {
  return api(`/api/v1/ontology/entity-types/${encodeURIComponent(code)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteOntologyEntityType(code) {
  return api(`/api/v1/ontology/entity-types/${encodeURIComponent(code)}`, {
    method: "DELETE",
  });
}

export function validateOntologyEntityType(code, properties) {
  return api(
    `/api/v1/ontology/entity-types/${encodeURIComponent(code)}/validate`,
    {
      method: "POST",
      body: JSON.stringify({ properties }),
    }
  );
}

// ── 关系类型 ─────────────────────────────────────────────────────────────

export function fetchOntologyRelationTypes() {
  return api("/api/v1/ontology/relation-types");
}

export function createOntologyRelationType(body) {
  return api("/api/v1/ontology/relation-types", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateOntologyRelationType(code, body) {
  return api(`/api/v1/ontology/relation-types/${encodeURIComponent(code)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteOntologyRelationType(code) {
  return api(`/api/v1/ontology/relation-types/${encodeURIComponent(code)}`, {
    method: "DELETE",
  });
}

// ── 公理 ─────────────────────────────────────────────────────────────────

export function fetchOntologyAxioms() {
  return api("/api/v1/ontology/axioms");
}

export function createOntologyAxiom(body) {
  return api("/api/v1/ontology/axioms", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateOntologyAxiom(name, body) {
  return api(
    `/api/v1/ontology/axioms/${encodeURIComponent(name)}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    }
  );
}

export function deleteOntologyAxiom(name) {
  return api(
    `/api/v1/ontology/axioms/${encodeURIComponent(name)}`,
    { method: "DELETE" }
  );
}

export function runOntologyAxiom(name) {
  return api(
    `/api/v1/ontology/axioms/${encodeURIComponent(name)}/run`,
    { method: "POST" }
  );
}

export function runAllOntologyAxioms() {
  return api("/api/v1/ontology/axioms/run-all", { method: "POST" });
}

// ── 概览 ─────────────────────────────────────────────────────────────────

export function fetchOntologyMeta() {
  return api("/api/v1/ontology/meta");
}

/** 本体 TBox 可视化图（Class / Property / subClassOf） */
export function fetchOntologySchemaGraph() {
  return api("/api/v1/ontology/schema-graph");
}

// ── 默认种子 ─────────────────────────────────────────────────────────────

export function seedOntologyDefaults() {
  return api("/api/v1/ontology/seed-defaults", {
    method: "POST",
    body: JSON.stringify({ confirm: true }),
  });
}

/** LLM 发现 TBox 候选（不写库） */
export function discoverOntologyFromText({ title = "文档抽取", text, maxChars } = {}) {
  return api("/api/v1/ontology/discover-from-text", {
    method: "POST",
    body: JSON.stringify({
      title,
      text,
      ...(maxChars != null ? { max_chars: maxChars } : {}),
    }),
  });
}

export function discoverOntologyFromDocuments({ documentIds = [], maxChars } = {}) {
  return api("/api/v1/ontology/discover-from-documents", {
    method: "POST",
    body: JSON.stringify({
      document_ids: documentIds,
      ...(maxChars != null ? { max_chars: maxChars } : {}),
    }),
  });
}

/** 将勾选候选写入 GraphDB */
export function applyOntologyDiscover({ entityTypes = [], relationTypes = [] } = {}) {
  return api("/api/v1/ontology/discover-from-text/apply", {
    method: "POST",
    body: JSON.stringify({
      entity_types: entityTypes,
      relation_types: relationTypes,
    }),
  });
}

// ── 问数映射（自动发现）────────────────────────────────────────────────

export function fetchFieldBindings({ enabledOnly = false } = {}) {
  const q = enabledOnly ? "?enabled_only=true" : "";
  return api(`/api/v1/ontology/field-bindings${q}`);
}

export function fetchFieldBindingSchema() {
  return api("/api/v1/ontology/field-bindings/schema");
}

export function discoverFieldBindings() {
  return api("/api/v1/ontology/field-bindings/discover", { method: "POST" });
}

export function updateFieldBinding(id, body) {
  return api(`/api/v1/ontology/field-bindings/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function upsertFieldBinding(body) {
  return api("/api/v1/ontology/field-bindings", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
