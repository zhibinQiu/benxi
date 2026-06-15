import { getApiBase, getToken, rejectHttpFailure } from "../api/http.js";

/** KnowFlow 切片引用截图 API（源 PDF 区域快照，非提取文本） */
export function knowledgeCitationPreviewPath(citation) {
  const c = citation || {};
  const params = new URLSearchParams();
  const imageId = String(c.image_id || "").trim();
  const chunkId = String(c.chunk_id || "").trim();
  const datasetId = String(c.dataset_id || "").trim();
  const ragDocId = String(c.ragflow_document_id || "").trim();
  const docId = String(c.document_id || "").trim();
  const anchor = c.anchor_json || {};
  if (imageId) params.set("image_id", imageId);
  if (chunkId) params.set("chunk_id", chunkId);
  if (datasetId) params.set("dataset_id", datasetId);
  if (ragDocId) params.set("ragflow_document_id", ragDocId);
  if (docId) params.set("document_id", docId);
  if (anchor.page != null && anchor.page !== "") {
    params.set("page", String(anchor.page));
  }
  if (Array.isArray(anchor.bbox) && anchor.bbox.length >= 4) {
    params.set("bbox", anchor.bbox.map((n) => Number(n)).join(","));
  }
  const bboxFormat = String(anchor.bbox_format || "").trim();
  if (bboxFormat) {
    params.set("bbox_format", bboxFormat);
  }
  const snippet = String(c.snippet || "").trim();
  if (snippet) {
    params.set("snippet", snippet.slice(0, 800));
  }
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
    rejectHttpFailure(res, { message: text });
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

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeRegExp(text) {
  return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function decodeHtmlEntities(text) {
  return String(text || "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
}

/** 从检索问句提取用于片段高亮的关键词（含中文双字切分） */
export function extractCitationQueryTerms(question, extraTerms = []) {
  const terms = [];
  const add = (term) => {
    const t = String(term || "").trim();
    if (t.length >= 2 && !terms.includes(t)) terms.push(t);
  };

  for (const term of extraTerms || []) add(term);

  const q = String(question || "").trim();
  if (!q) return terms.slice(0, 10);

  for (const token of q.split(/[\s,，。；;、？?！!]+/)) {
    add(token);
    if (terms.length >= 10) return terms.slice(0, 10);
  }
  for (const seg of q.match(/[\u4e00-\u9fff]{2,}/g) || []) {
    if (seg.length <= 4) add(seg);
    for (let i = 0; i < seg.length - 1; i += 1) {
      add(seg.slice(i, i + 2));
      if (terms.length >= 10) return terms.slice(0, 10);
    }
  }
  return terms.slice(0, 10).sort((a, b) => b.length - a.length);
}

function hasHighlightMarkup(html) {
  return /<(em|mark)\b|<\/(em|mark)>/i.test(html || "");
}

function normalizeHighlightTags(html) {
  let out = decodeHtmlEntities(String(html || ""));
  out = out
    .replace(/<mark\b[^>]*>(.*?)<\/mark>/gi, "<mark class=\"cite-hl\">$1</mark>")
    .replace(/<em\b[^>]*>(.*?)<\/em>/gi, "<mark class=\"cite-hl\">$1</mark>")
    .replace(
      /<font\b[^>]*\bclass=['"]highlight['"][^>]*>(.*?)<\/font>/gi,
      '<mark class="cite-hl">$1</mark>'
    )
    .replace(/\*\*(.+?)\*\*/g, '<mark class="cite-hl">$1</mark>');
  return out.replace(/\n/g, "<br/>");
}

function highlightPlainText(text, terms) {
  if (!text || !terms?.length) return escapeHtml(text);
  let html = escapeHtml(text);
  for (const term of terms) {
    if (term.length < 2) continue;
    const re = new RegExp(escapeRegExp(term), "gi");
    html = html.replace(re, '<mark class="cite-hl">$&</mark>');
  }
  return html.replace(/\n/g, "<br/>");
}

/**
 * 渲染引用片段 HTML（KnowFlow highlight + 问句关键词高亮）
 * @param {string} raw
 * @param {string} [question]
 * @param {string[]} [highlightTerms] 后端下发的 highlight_terms
 */
export function formatCitationSnippet(raw, question = "", highlightTerms = []) {
  const text = String(raw || "").trim();
  if (!text) return "";

  const terms = extractCitationQueryTerms(
    question,
    Array.isArray(highlightTerms) && highlightTerms.length
      ? highlightTerms
      : []
  );

  const decoded = decodeHtmlEntities(text);
  if (hasHighlightMarkup(decoded)) {
    return normalizeHighlightTags(decoded);
  }

  const plain = decoded.replace(/<[^>]+>/g, "");
  if (terms.length) {
    return highlightPlainText(plain, terms);
  }

  return normalizeHighlightTags(decoded) || escapeHtml(plain).replace(/\n/g, "<br/>");
}

export function citationPageLabel(citation, t) {
  const page = citation?.anchor_json?.page;
  if (page == null || page === "") return "";
  if (t) return t("knowledgeSearch.citations.page", { page });
  return `第 ${page} 页`;
}

export function citationCanPreviewImage(citation) {
  const c = citation || {};
  if (c.preview_available === true) return true;
  if (c.preview_available === false) return false;
  if (c.source === "pageindex") {
    const page = c.anchor_json?.page;
    if (String(c.document_id || "").trim() && page != null && page !== "") {
      return true;
    }
  }
  const anchor = c.anchor_json || {};
  const bbox = anchor.bbox;
  if (Array.isArray(bbox) && bbox.length >= 4) {
    return Boolean(
      String(c.chunk_id || "").trim() &&
        String(c.dataset_id || "").trim() &&
        String(c.ragflow_document_id || "").trim()
    );
  }
  if (String(c.image_id || "").trim()) return true;
  return Boolean(
    String(c.chunk_id || "").trim() &&
      String(c.dataset_id || "").trim() &&
      String(c.ragflow_document_id || "").trim()
  );
}
