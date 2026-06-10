/** 平台原生知识库 / 知识检索 API */
import { api } from "./http.js";
import { searchKnowledge } from "./rag.js";

export { searchKnowledge };

export async function fetchKnowledgeScopeTree() {
  return api("/api/v1/knowledge/scope-tree");
}

export async function fetchKnowledgeLibraries() {
  return api("/api/v1/knowledge/libraries");
}

export async function fetchLibraryDocuments(datasetId, { page = 1, pageSize = 50, keyword } = {}) {
  const q = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (keyword) q.set("keyword", keyword);
  return api(`/api/v1/knowledge/libraries/${encodeURIComponent(datasetId)}/documents?${q}`);
}

export async function fetchDocumentChunks(
  documentId,
  { versionId, page = 1, pageSize = 30, keywords } = {}
) {
  const q = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (versionId) q.set("version_id", versionId);
  if (keywords) q.set("keywords", keywords);
  return api(`/api/v1/knowledge/documents/${encodeURIComponent(documentId)}/chunks?${q}`);
}

export async function fetchParserOptions() {
  return api("/api/v1/knowledge/parsers");
}

export async function reindexDocument(
  documentId,
  { versionId, parserId = "smart", layoutRecognize, resync = false } = {}
) {
  const body = { parser_id: parserId, resync };
  if (versionId) body.version_id = versionId;
  if (layoutRecognize) body.layout_recognize = layoutRecognize;
  return api(`/api/v1/knowledge/documents/${encodeURIComponent(documentId)}/reindex`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createKnowledgeQaSession(documentIds, title = "知识检索") {
  return api("/api/v1/knowledge/qa/sessions", {
    method: "POST",
    body: JSON.stringify({ document_ids: documentIds, title }),
  });
}

export async function askKnowledgeQaSession(sessionId, question) {
  return api(`/api/v1/knowledge/qa/sessions/${encodeURIComponent(sessionId)}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

/** 非流式问答，供 AiChatPanel chatSend 或自定义面板使用 */
export async function knowledgeQaChatSend({ message, conversationId, documentIds }) {
  let sessionId = conversationId;
  if (!sessionId) {
    if (!documentIds?.length) {
      throw new Error("请从左侧选择知识库或文档");
    }
    const session = await createKnowledgeQaSession(documentIds);
    sessionId = session.id;
  }
  const data = await askKnowledgeQaSession(sessionId, message);
  const msg = data.message || {};
  return {
    reply: msg.content || "",
    citations: msg.citations || [],
    conversation_id: sessionId,
  };
}
