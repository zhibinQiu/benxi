/** 文档对比 REST API */
import { api, getApiBase, getToken, rejectHttpFailure } from "./http.js";
import { messages } from "../locales/index.js";

function compareMessage(key) {
  const locale = localStorage.getItem("platform-locale") === "en" ? "en" : "zh";
  const raw = key.split(".").reduce((obj, part) => obj?.[part], messages[locale]);
  return typeof raw === "string" ? raw : key;
}

export async function fetchCompareDocuments({ page = 1, page_size = 10, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/compare/documents?${q}`);
}

export async function createCompareJob({ leftDocumentId, rightDocumentId }) {
  return api("/api/v1/compare/jobs", {
    method: "POST",
    body: JSON.stringify({
      left_document_id: leftDocumentId,
      right_document_id: rightDocumentId,
    }),
  });
}

export async function fetchCompareJob(jobId) {
  return api(`/api/v1/compare/jobs/${jobId}`);
}

/** 轮询对比任务直至完成或失败（SSE 优先，失败时降级轮询） */
export async function waitCompareJob(jobId, { intervalMs = 1500, timeoutMs = 120000 } = {}) {
  try {
    const { waitCompareJobViaSse } = await import("./jobEvents.js");
    return await waitCompareJobViaSse(jobId, { timeoutMs });
  } catch {
    /* fallback below */
  }
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await fetchCompareJob(jobId);
    if (job?.status === "done" || job?.status === "failed") {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(compareMessage("compare.timeout"));
}

export async function searchCompareJob(jobId, { query, scope = "right", fieldMatch = true }) {
  return api(`/api/v1/compare/jobs/${jobId}/search`, {
    method: "POST",
    body: JSON.stringify({
      query,
      scope,
      field_match: fieldMatch,
    }),
  });
}

/** 右侧目标文档内检索（KnowFlow / 本地），无需先段落比对 */
export async function searchCompareDocuments({
  rightDocumentId,
  query,
  fieldMatch = true,
}) {
  return api("/api/v1/compare/search", {
    method: "POST",
    body: JSON.stringify({
      right_document_id: rightDocumentId,
      query,
      field_match: fieldMatch,
    }),
  });
}

export async function getCompareDocumentDownload(documentId) {
  return api(`/api/v1/compare/documents/${documentId}/download`);
}

export async function fetchCompareDocumentContent(documentId, versionId = null) {
  const q = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  return api(`/api/v1/compare/documents/${documentId}/content${q}`);
}

/** 只读：加载时间线相邻版本对的预计算 diff */
export async function fetchVersionCompareAdjacent(documentId, versionIds) {
  const q = new URLSearchParams({
    version_ids: versionIds.join(","),
  });
  return api(
    `/api/v1/compare/documents/${documentId}/version-compare/adjacent?${q}`
  );
}

/** 版本差异问答（基于入库 diff + LLM 总结） */
export async function askVersionCompare(documentId, { leftVersionId, rightVersionId, question }) {
  return api(`/api/v1/compare/documents/${documentId}/version-compare/ask`, {
    method: "POST",
    body: JSON.stringify({
      left_version_id: leftVersionId,
      right_version_id: rightVersionId,
      question,
    }),
  });
}

export async function pollVersionCompareAdjacent(
  documentId,
  versionIds,
  { intervalMs = 1500, timeoutMs = 120000 } = {}
) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const rows = await fetchVersionCompareAdjacent(documentId, versionIds);
    if (rows.every((r) => r.status === "done" || r.status === "failed")) {
      return rows;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(compareMessage("compare.precomputePartialPending"));
}

/** 带鉴权拉取原文，用于对比页 iframe（blob URL） */
export async function fetchCompareDocumentFileBlob(documentId) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${getApiBase()}/api/v1/compare/documents/${documentId}/file`, {
    headers,
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    rejectHttpFailure(res, json);
  }
  return res.blob();
}
