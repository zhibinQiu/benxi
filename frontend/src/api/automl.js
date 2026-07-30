/** 自动化机器学习 REST API */
import { api, getApiBase, getToken, rejectHttpFailure } from "./http.js";
import { downloadBlob } from "../utils/downloadBlob.js";

export async function fetchAutoMlMeta() {
  return api("/api/v1/auto-ml/meta");
}

export async function uploadAutoMlDataset(file) {
  const form = new FormData();
  form.append("file", file);
  return api("/api/v1/auto-ml/datasets/upload", { method: "POST", body: form });
}

export async function fetchAutoMlDataset(datasetId) {
  return api(`/api/v1/auto-ml/datasets/${datasetId}`);
}

export async function fetchAutoMlModels(task) {
  return api(`/api/v1/auto-ml/models?task=${encodeURIComponent(task)}`);
}

export async function createAutoMlRun(body) {
  return api("/api/v1/auto-ml/runs", { method: "POST", body });
}

export async function fetchAutoMlRun(runId) {
  return api(`/api/v1/auto-ml/runs/${runId}`);
}

export async function listAutoMlRuns(limit = 30) {
  return api(`/api/v1/auto-ml/runs?limit=${limit}`);
}

async function downloadAutoMlFile(url, fallbackName) {
  const res = await fetch(`${getApiBase()}${url}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    rejectHttpFailure(res, json);
  }
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disp);
  const name = decodeURIComponent(m?.[1] || m?.[2] || fallbackName);
  downloadBlob(blob, name);
}

export async function downloadAutoMlPredictions(runId) {
  await downloadAutoMlFile(
    `/api/v1/auto-ml/runs/${runId}/download/predictions`,
    `automl_${String(runId).slice(0, 8)}_predictions.csv`
  );
}

export async function downloadAutoMlModel(runId) {
  await downloadAutoMlFile(
    `/api/v1/auto-ml/runs/${runId}/download/model`,
    `automl_${String(runId).slice(0, 8)}_model.pkl`
  );
}
