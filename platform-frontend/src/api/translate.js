/** PDF 翻译 REST API */
import { api, getApiBase, getToken, rejectHttpFailure } from "./http.js";

export async function fetchTranslateMeta() {
  return api("/api/v1/translate/meta");
}

export async function fetchTranslateJobs({ page = 1, page_size = 15 } = {}) {
  const q = new URLSearchParams({ page, page_size });
  return api(`/api/v1/translate/jobs?${q}`);
}

export async function fetchTranslateDocuments({ page = 1, page_size = 15, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/translate/documents?${q}`);
}

export async function createTranslateJob({
  pdf,
  documentId,
  langIn,
  langOut,
  service,
  glossaries,
}) {
  const form = new FormData();
  if (pdf) form.append("file", pdf);
  if (documentId) form.append("document_id", documentId);
  form.append("lang_in", langIn);
  form.append("lang_out", langOut);
  form.append("service", service);
  for (const g of glossaries || []) {
    form.append("glossary_files", g);
  }
  return api("/api/v1/translate/jobs", { method: "POST", body: form });
}

/** @param {string} platformJobId 平台任务 UUID */
export async function fetchTranslateJob(platformJobId) {
  return api(`/api/v1/translate/jobs/${platformJobId}`);
}

export async function importTranslateToLibrary(
  platformJobId,
  { variant = "mono", syncKnowflow = true } = {}
) {
  return api(`/api/v1/translate/jobs/${platformJobId}/import-library`, {
    method: "POST",
    body: JSON.stringify({ variant, sync_knowflow: syncKnowflow }),
  });
}

export function subscribeTranslateEvents(platformJobId, { onEvent, onError, onComplete }) {
  const token = getToken();
  const url = `${getApiBase()}/api/v1/translate/jobs/${platformJobId}/events${
    token ? `?token=${encodeURIComponent(token)}` : ""
  }`;
  const es = new EventSource(url);
  const types = [
    "progress_update",
    "progress_start",
    "progress_end",
    "finish",
    "error",
    "job_finished",
    "complete",
    "snapshot",
    "files_updated",
  ];
  for (const type of types) {
    es.addEventListener(type, (e) => {
      try {
        const data = JSON.parse(e.data);
        if (type === "complete") onComplete?.(data);
        else onEvent?.({ type, ...data });
      } catch {
        /* ignore */
      }
    });
  }
  es.onerror = () => {
    onError?.(new Error("SSE 连接中断"));
    es.close();
  };
  return () => es.close();
}

async function fetchTranslateFileResponse(jobId, kind) {
  const res = await fetch(`${getApiBase()}/api/v1/translate/jobs/${jobId}/download/${kind}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    rejectHttpFailure(res, { message: text });
  }
  return res;
}

export async function fetchTranslateFileBlob(jobId, kind) {
  const res = await fetchTranslateFileResponse(jobId, kind);
  return res.blob();
}

export async function downloadTranslateFile(jobId, kind, fallbackName = "download") {
  const res = await fetchTranslateFileResponse(jobId, kind);
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = disp.match(/filename="?([^";]+)"?/);
  const name = match ? match[1] : fallbackName;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
