/** 文档对比 REST API */
import { api, getApiBase, getToken } from "./http.js";

export async function fetchCompareDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/compare/documents?${q}`);
}

export async function createCompareJob({ leftDocumentId, rightDocumentId, syncKnowflow = true }) {
  return api("/api/v1/compare/jobs", {
    method: "POST",
    body: JSON.stringify({
      left_document_id: leftDocumentId,
      right_document_id: rightDocumentId,
      sync_knowflow: syncKnowflow,
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
  throw new Error("文档对比超时，请稍后重试");
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
  syncKnowflow = true,
  fieldMatch = true,
}) {
  return api("/api/v1/compare/search", {
    method: "POST",
    body: JSON.stringify({
      right_document_id: rightDocumentId,
      query,
      sync_knowflow: syncKnowflow,
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

/** 单文档版本对 diff：只读，返回上传时预计算入库的结果 */
export async function fetchVersionCompare(documentId, leftVersionId, rightVersionId) {
  const q = new URLSearchParams({
    left_version_id: leftVersionId,
    right_version_id: rightVersionId,
  });
  return api(`/api/v1/compare/documents/${documentId}/version-compare?${q}`);
}

export async function pollVersionCompare(
  documentId,
  leftVersionId,
  rightVersionId,
  { intervalMs = 1500, timeoutMs = 120000 } = {}
) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const rel = await fetchVersionCompare(documentId, leftVersionId, rightVersionId);
    if (rel?.status === "done" || rel?.status === "failed") return rel;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("预计算差异尚未就绪，请稍后刷新");
}

export async function fetchDocumentVersionCompareRelations(documentId) {
  return api(`/api/v1/compare/documents/${documentId}/version-compare/relations`);
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

/** @deprecated 使用 fetchVersionCompareAdjacent */
export async function fetchVersionCompareBatch(documentId, versionIds) {
  return api(`/api/v1/compare/documents/${documentId}/version-compare/batch`, {
    method: "POST",
    body: JSON.stringify({ version_ids: versionIds }),
  });
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
  throw new Error("部分版本差异仍在后台预计算，请稍后刷新");
}

/** @deprecated */
export async function waitVersionCompareBatch(
  documentId,
  versionIds,
  opts = {}
) {
  return pollVersionCompareAdjacent(documentId, versionIds, opts);
}

/** @deprecated */
export async function waitVersionCompare(
  documentId,
  leftVersionId,
  rightVersionId,
  opts = {}
) {
  return pollVersionCompare(documentId, leftVersionId, rightVersionId, opts);
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
    throw new Error(json?.message || res.statusText || "加载文档失败");
  }
  return res.blob();
}
