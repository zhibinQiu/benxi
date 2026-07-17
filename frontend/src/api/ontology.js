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

// ── 默认种子 ─────────────────────────────────────────────────────────────

export function seedOntologyDefaults() {
  return api("/api/v1/ontology/seed-defaults", {
    method: "POST",
    body: JSON.stringify({ confirm: true }),
  });
}
