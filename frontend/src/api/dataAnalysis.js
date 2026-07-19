import { api } from "./http.js";

export async function fetchDataAnalysisMeta() {
  return api("/api/v1/data-analysis/meta");
}

export async function uploadDataAnalysisDataset(file) {
  const form = new FormData();
  form.append("file", file);
  return api("/api/v1/data-analysis/datasets/upload", { method: "POST", body: form });
}

export async function createDataAnalysisSession({ datasetId } = {}) {
  return api("/api/v1/data-analysis/sessions", {
    method: "POST",
    body: JSON.stringify({ dataset_id: datasetId || null }),
  });
}

export async function fetchDataAnalysisSession(sessionId) {
  return api(`/api/v1/data-analysis/sessions/${sessionId}`);
}

export async function dataAnalysisChat(sessionId, { message, datasetId, repairCellId } = {}) {
  return api(`/api/v1/data-analysis/sessions/${sessionId}/chat`, {
    method: "POST",
    body: JSON.stringify({
      message,
      dataset_id: datasetId || null,
      repair_cell_id: repairCellId || null,
    }),
  });
}

export async function createDataAnalysisCell(sessionId, { title, code } = {}) {
  return api(`/api/v1/data-analysis/sessions/${sessionId}/cells`, {
    method: "POST",
    body: JSON.stringify({ title, code }),
  });
}

export async function updateDataAnalysisCell(sessionId, cellId, { code, title } = {}) {
  return api(`/api/v1/data-analysis/sessions/${sessionId}/cells/${cellId}`, {
    method: "PUT",
    body: JSON.stringify({ code, title }),
  });
}

export async function runDataAnalysisCell(sessionId, cellId) {
  return api(`/api/v1/data-analysis/sessions/${sessionId}/cells/${cellId}/run`, {
    method: "POST",
  });
}

export async function previewDataAnalysisData(sessionId, { limit } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  const qs = params.toString();
  return api(`/api/v1/data-analysis/sessions/${sessionId}/preview${qs ? `?${qs}` : ""}`);
}
