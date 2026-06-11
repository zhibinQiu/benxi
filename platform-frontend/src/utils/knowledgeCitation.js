import { getApiBase, getToken } from "../api/http.js";

/** KnowFlow 切片引用截图 API（源 PDF 区域快照，非提取文本） */
export function knowledgeCitationPreviewPath(citation) {
  const c = citation || {};
  const params = new URLSearchParams();
  const imageId = String(c.image_id || "").trim();
  const chunkId = String(c.chunk_id || "").trim();
  const datasetId = String(c.dataset_id || "").trim();
  const ragDocId = String(c.ragflow_document_id || "").trim();
  if (imageId) params.set("image_id", imageId);
  if (chunkId) params.set("chunk_id", chunkId);
  if (datasetId) params.set("dataset_id", datasetId);
  if (ragDocId) params.set("ragflow_document_id", ragDocId);
  if (!params.toString()) return "";
  return `${getApiBase()}/api/v1/knowledge/citations/preview?${params}`;
}

/** @deprecated 使用 knowledgeCitationPreviewPath */
export function knowledgeCitationImagePath(imageId) {
  const id = String(imageId || "").trim();
  if (!id) return "";
  return `${getApiBase()}/api/v1/knowledge/citations/images/${encodeURIComponent(id)}`;
}

async function fetchCitationBlob(path) {
  if (!path) throw new Error("缺少引用溯源参数");
  const token = getToken();
  const res = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `加载引用原文截图失败 (${res.status})`);
  }
  return res.blob();
}

/** 按完整 citation 加载源 PDF 区域截图 */
export async function fetchKnowledgeCitationPreviewBlob(citation) {
  const path = knowledgeCitationPreviewPath(citation);
  return fetchCitationBlob(path);
}

export async function fetchKnowledgeCitationImageBlob(imageId) {
  const path = knowledgeCitationImagePath(imageId);
  return fetchCitationBlob(path);
}

export function citationPageLabel(citation) {
  const page = citation?.anchor_json?.page;
  if (page == null || page === "") return "";
  return `第 ${page} 页`;
}

export function citationCanPreviewImage(citation) {
  const c = citation || {};
  return Boolean(
    String(c.image_id || "").trim() ||
      (String(c.chunk_id || "").trim() &&
        String(c.dataset_id || "").trim() &&
        String(c.ragflow_document_id || "").trim())
  );
}
