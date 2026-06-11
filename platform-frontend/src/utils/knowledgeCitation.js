import { getApiBase, getToken } from "../api/http.js";

/** KnowFlow 切片引用截图 API 路径（需带 Authorization 请求） */
export function knowledgeCitationImagePath(imageId) {
  const id = String(imageId || "").trim();
  if (!id) return "";
  return `${getApiBase()}/api/v1/knowledge/citations/images/${encodeURIComponent(id)}`;
}

export async function fetchKnowledgeCitationImageBlob(imageId) {
  const path = knowledgeCitationImagePath(imageId);
  if (!path) throw new Error("缺少引用截图");
  const token = getToken();
  const res = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `加载引用截图失败 (${res.status})`);
  }
  return res.blob();
}

export function citationPageLabel(citation) {
  const page = citation?.anchor_json?.page;
  if (page == null || page === "") return "";
  return `第 ${page} 页`;
}
