/** 平台原生知识库 / 知识检索 API */
import { api } from "./http.js";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";

/** scope-tree 构建可能较慢（多库/多文档），统一放宽超时避免首次加载误报 */
const SCOPE_TREE_TIMEOUT_MS = 60_000;

export async function fetchKnowledgeScopeTree({ refresh = false } = {}) {
  const q = refresh ? "?refresh=1" : "";
  return api(`/api/v1/knowledge/scope-tree${q}`, {
    timeoutMs: SCOPE_TREE_TIMEOUT_MS,
    /** 预取/建树耗时长，切换路由时不应 cancel，否则数据已到却无法渲染 */
    preserveOnNavigate: true,
  });
}

export async function fetchMountableFolders() {
  return api("/api/v1/knowledge/mountable-folders", {
    timeoutMs: SCOPE_TREE_TIMEOUT_MS,
  });
}

export async function fetchKnowledgeLibraries() {
  return api("/api/v1/knowledge/libraries");
}

export async function fetchLibraryDocuments(
  datasetId,
  { page = 1, pageSize = LIST_PAGE_SIZE, folderId } = {}
) {
  const q = new URLSearchParams({ page, page_size: pageSize });
  if (folderId) q.set("folder_id", folderId);
  return api(`/api/v1/knowledge/libraries/${datasetId}/documents?${q}`);
}

export async function fetchLibraryDocumentChunks(documentId) {
  return api(`/api/v1/knowledge/documents/${documentId}/chunks`);
}

export async function fetchReindexDocument(
  documentId,
  { versionId, parserId, layoutRecognize, resync = false } = {}
) {
  const body = { resync };
  if (parserId) body.parser_id = parserId;
  if (versionId) body.version_id = versionId;
  if (layoutRecognize) body.layout_recognize = layoutRecognize;
  return api(`/api/v1/knowledge/documents/${encodeURIComponent(documentId)}/reindex`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchReindexUnindexedDocuments() {
  return api("/api/v1/knowledge/documents/reindex-unindexed", {
    method: "POST",
  });
}

export async function fetchParsers() {
  return api("/api/v1/knowledge/parsers", { cache: new Date() });
}

export async function fetchCitationPreview({ ragflowDocId, chunkId, pageNum }) {
  const q = new URLSearchParams({ ragflow_doc_id: ragflowDocId, chunk_id: chunkId, page_num: pageNum });
  return api(`/api/v1/knowledge/citations/preview?${q}`);
}

export async function fetchCitationImage(imageId) {
  return api(`/api/v1/knowledge/citations/images/${imageId}`, {
    responseType: "blob",
  });
}

export async function createKnowledgeQaSession(documentIds) {
  return api("/api/v1/knowledge/qa/sessions", {
    method: "POST",
    body: { document_ids: documentIds },
  });
}

export async function askKnowledgeQaSession(sessionId, question) {
  return api(`/api/v1/knowledge/qa/sessions/${sessionId}/ask`, {
    method: "POST",
    body: { question, use_agentic: true },
  });
}

export async function fetchKnowledgeQaMindmap({ question, answer }) {
  return api("/api/v1/knowledge/qa/mindmap", {
    method: "POST",
    body: { question, answer },
    timeoutMs: 30_000,
  });
}
