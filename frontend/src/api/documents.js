/** 文档库 REST API */
import {
  getApiBase,
  api,
  getToken,
  fetchWithTimeout,
  rejectHttpFailure,
  LIST_API_TIMEOUT_MS,
  UPLOAD_API_TIMEOUT_MS,
} from "./http.js";
import { downloadBlob } from "../utils/downloadBlob.js";

const listReadOpts = { timeoutMs: LIST_API_TIMEOUT_MS };

export async function fetchDocumentLibrary() {
  return api("/api/v1/documents/library", listReadOpts);
}

export async function fetchDocumentOverview({ scope, dept_id, owner_id } = {}) {
  const q = new URLSearchParams({ scope });
  if (dept_id) q.set("dept_id", dept_id);
  if (owner_id) q.set("owner_id", owner_id);
  return api(`/api/v1/documents/overview?${q}`, listReadOpts);
}

export async function fetchDocuments({
  page = 1,
  page_size = 15,
  keyword,
  scope,
  folder_id,
  uncategorized,
  dept_id,
  owner_id,
} = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  if (scope) q.set("scope", scope);
  if (folder_id) q.set("folder_id", folder_id);
  if (uncategorized) q.set("uncategorized", "true");
  if (dept_id) q.set("dept_id", dept_id);
  if (owner_id) q.set("owner_id", owner_id);
  return api(`/api/v1/documents?${q}`, listReadOpts);
}

export async function fetchKbFolders({ scope, dept_id, owner_id } = {}) {
  const q = new URLSearchParams({ scope });
  if (dept_id) q.set("dept_id", dept_id);
  if (owner_id) q.set("owner_id", owner_id);
  return api(`/api/v1/documents/kb-folders?${q}`, listReadOpts);
}

export async function createKbFolder(payload) {
  return api("/api/v1/documents/kb-folders", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateKbFolder(folderId, payload) {
  return api(`/api/v1/documents/kb-folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteKbFolder(folderId) {
  return api(`/api/v1/documents/kb-folders/${folderId}`, { method: "DELETE" });
}

export async function fetchRecycleDocuments({ page = 1, page_size = 15, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/documents/trash?${q}`);
}

export async function createDocument(payload) {
  return api("/api/v1/documents", {
    method: "POST",
    body: JSON.stringify(payload),
    preserveOnNavigate: true,
    timeoutMs: UPLOAD_API_TIMEOUT_MS,
  });
}

export async function fetchDocument(id, { liveIndex = false } = {}) {
  const q = liveIndex ? "?live_index=1" : "";
  return api(`/api/v1/documents/${id}${q}`);
}

export async function prepareUpload(documentId, fileName, mimeType) {
  const q = new URLSearchParams({ file_name: fileName, mime_type: mimeType });
  return api(`/api/v1/documents/${documentId}/upload/prepare?${q}`, {
    method: "POST",
    preserveOnNavigate: true,
    timeoutMs: UPLOAD_API_TIMEOUT_MS,
  });
}

/** 解析 prepare 返回的上传地址（相对路径拼 API 根地址，presigned 原样返回） */
export function resolveUploadUrl(uploadUrl) {
  const raw = String(uploadUrl || "").trim();
  if (!raw) return raw;
  if (/^https?:\/\//i.test(raw)) return raw;
  const base = getApiBase().replace(/\/$/, "");
  return raw.startsWith("/") ? `${base}${raw}` : `${base}/${raw}`;
}

/** 经平台鉴权上传文件 blob（MinIO 内网地址由后端代理） */
export async function uploadDocumentBlob(uploadUrl, file) {
  const url = resolveUploadUrl(uploadUrl);
  const headers = {
    "Content-Type": file.type || "application/octet-stream",
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetchWithTimeout(
    url,
    { method: "PUT", body: file, headers },
    UPLOAD_API_TIMEOUT_MS
  );
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    rejectHttpFailure(res, json);
  }
}

export async function completeUpload(documentId, body) {
  return api(`/api/v1/documents/${documentId}/upload/complete`, {
    method: "POST",
    body: JSON.stringify(body),
    preserveOnNavigate: true,
    timeoutMs: UPLOAD_API_TIMEOUT_MS,
  });
}

export async function getDownloadUrl(documentId) {
  return api(`/api/v1/documents/${documentId}/download`);
}

export async function syncDocumentToKnowflow(documentId) {
  return api(`/api/v1/documents/${documentId}/sync-knowflow`, { method: "POST" });
}

export async function downloadDocumentFile(
  documentId,
  fallbackName = "document",
  versionId = null,
) {
  const qs = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  const res = await fetch(`${getApiBase()}/api/v1/documents/${documentId}/file${qs}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    rejectHttpFailure(res, json);
  }
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const utf8Match = disp.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disp.match(/filename="([^"]+)"/);
  let name = fallbackName;
  if (utf8Match) {
    try {
      name = decodeURIComponent(utf8Match[1]);
    } catch {
      name = utf8Match[1];
    }
  } else if (plainMatch) {
    name = plainMatch[1];
  }
  downloadBlob(blob, name);
}

/** 拉取文档文件 blob（可选指定版本），供预览等场景 */
export async function fetchDocumentFileBlob(documentId, versionId = null) {
  const qs = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  const res = await fetch(`${getApiBase()}/api/v1/documents/${documentId}/file${qs}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    rejectHttpFailure(res, json);
  }
  return res.blob();
}

/** 浏览器内嵌预览 URL（iframe/embed；鉴权走 query token + inline disposition） */
export function buildDocumentFilePreviewUrl(documentId, versionId = null) {
  const params = new URLSearchParams({ disposition: "inline" });
  if (versionId) params.set("version_id", String(versionId));
  const token = getToken();
  if (token) params.set("token", token);
  return `${getApiBase()}/api/v1/documents/${documentId}/file?${params}`;
}

export async function deleteDocument(documentId) {
  return api(`/api/v1/documents/${documentId}`, { method: "DELETE" });
}

export async function deleteDocumentVersion(documentId, versionId) {
  return api(`/api/v1/documents/${documentId}/versions/${versionId}`, {
    method: "DELETE",
  });
}

export async function patchDocumentStatus(documentId, status) {
  return api(`/api/v1/documents/${documentId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function updateDocument(documentId, payload) {
  return api(`/api/v1/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function moveDocument(documentId, { folder_id } = {}) {
  return api(`/api/v1/documents/${documentId}/move`, {
    method: "POST",
    body: JSON.stringify({ folder_id: folder_id ?? null }),
  });
}

export async function restoreDocument(documentId) {
  return api(`/api/v1/documents/${documentId}/restore`, { method: "POST" });
}

export async function permanentlyDeleteDocument(documentId) {
  return api(`/api/v1/documents/${documentId}/permanent`, { method: "DELETE" });
}

export async function batchDeleteDocuments(documentIds, { permanent = true } = {}) {
  return api("/api/v1/documents/batch-delete", {
    method: "POST",
    body: JSON.stringify({ document_ids: documentIds, permanent }),
  });
}

export async function emptyRecycleBin() {
  return api("/api/v1/documents/trash/empty", { method: "POST" });
}

export async function fetchDocumentAccessControl(documentId) {
  return api(`/api/v1/documents/${documentId}/access-control`);
}

export async function fetchDocumentAclCandidates(documentId) {
  return api(`/api/v1/documents/${documentId}/acl-candidates`);
}

export async function fetchDocumentShares(documentId) {
  return api(`/api/v1/documents/${documentId}/permissions`);
}

export async function grantDocumentShares(documentId, { userIds, level }) {
  return api(`/api/v1/documents/${documentId}/permissions/batch`, {
    method: "POST",
    body: JSON.stringify({ user_ids: userIds, level }),
  });
}

export async function revokeDocumentShare(documentId, userId) {
  return api(
    `/api/v1/documents/${documentId}/permissions/users/${encodeURIComponent(userId)}`,
    { method: "DELETE" }
  );
}

export async function fetchDocumentDenials(documentId) {
  return api(`/api/v1/documents/${documentId}/denials`);
}

export async function denyDocumentAccess(documentId, body) {
  return api(`/api/v1/documents/${documentId}/denials`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function liftDocumentDenial(documentId, userId) {
  return api(`/api/v1/documents/${documentId}/denials/${userId}`, {
    method: "DELETE",
  });
}
