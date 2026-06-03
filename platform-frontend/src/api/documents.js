/** 文档库 REST API */
import { API_BASE, api, formatApiDetail, getToken } from "./http.js";

export async function fetchDocumentLibrary() {
  return api("/api/v1/documents/library");
}

export async function fetchDocuments({
  page = 1,
  page_size = 20,
  keyword,
  scope,
  folder_id,
  uncategorized,
  dept_id,
} = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  if (scope) q.set("scope", scope);
  if (folder_id) q.set("folder_id", folder_id);
  if (uncategorized) q.set("uncategorized", "true");
  if (dept_id) q.set("dept_id", dept_id);
  return api(`/api/v1/documents?${q}`);
}

export async function fetchKbFolders({ scope, dept_id } = {}) {
  const q = new URLSearchParams({ scope });
  if (dept_id) q.set("dept_id", dept_id);
  return api(`/api/v1/documents/kb-folders?${q}`);
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

export async function fetchRecycleDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/documents/trash?${q}`);
}

export async function fetchMySharedDocuments({ page = 1, page_size = 20, keyword } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/documents/my-shares?${q}`);
}

export async function createDocument(payload) {
  return api("/api/v1/documents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchDocument(id) {
  return api(`/api/v1/documents/${id}`);
}

export async function prepareUpload(documentId, fileName, mimeType) {
  const q = new URLSearchParams({ file_name: fileName, mime_type: mimeType });
  return api(`/api/v1/documents/${documentId}/upload/prepare?${q}`, {
    method: "POST",
  });
}

/** 解析 prepare 返回的上传地址（相对路径拼 API_BASE，presigned 原样返回） */
export function resolveUploadUrl(uploadUrl) {
  const raw = String(uploadUrl || "").trim();
  if (!raw) return raw;
  if (/^https?:\/\//i.test(raw)) return raw;
  const base = API_BASE.replace(/\/$/, "");
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
  const res = await fetch(url, { method: "PUT", body: file, headers });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = formatApiDetail(body?.detail ?? body?.message ?? body) || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg || "上传到存储失败");
  }
}

export async function completeUpload(documentId, body) {
  return api(`/api/v1/documents/${documentId}/upload/complete`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getDownloadUrl(documentId) {
  return api(`/api/v1/documents/${documentId}/download`);
}

export async function syncDocumentToKnowflow(documentId) {
  return api(`/api/v1/documents/${documentId}/sync-knowflow`, { method: "POST" });
}

export async function downloadDocumentFile(documentId, fallbackName = "document") {
  const res = await fetch(`${API_BASE}/api/v1/documents/${documentId}/file`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const json = await res.json();
      msg = json?.message || formatApiDetail(json?.detail) || msg;
    } catch {
      const text = await res.text().catch(() => "");
      if (text) msg = text;
    }
    throw new Error(msg);
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
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
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

/** @deprecated 使用 fetchDocumentShares */
export const fetchDocumentPermissions = fetchDocumentShares;

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
