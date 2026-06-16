/** 平台原生知识库 / 知识检索 API */
import { api, getApiBase, getToken, rejectHttpFailure } from "./http.js";
import { sanitizeUserFacingMessage } from "../utils/uiMessage.js";

export async function fetchKnowledgeScopeTree({ refresh = false } = {}) {
  const q = refresh ? "?refresh=1" : "";
  return api(`/api/v1/knowledge/scope-tree${q}`);
}

export async function fetchKnowledgeLibraries() {
  return api("/api/v1/knowledge/libraries");
}

export async function fetchLibraryDocuments(
  datasetId,
  { page = 1, pageSize = 50, keyword, folderId, virtualFolderId } = {}
) {
  const q = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (keyword) q.set("keyword", keyword);
  if (folderId) q.set("folder_id", folderId);
  if (virtualFolderId) q.set("virtual_folder", virtualFolderId);
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

/** 流式问答，供知识检索 AiChatPanel 使用 */
export async function knowledgeQaChatStream(
  { message, history = [], conversationId = null, documentIds = null },
  { onDelta, onReplace, onWorkflow, onCitations, onDone, onError, signal } = {}
) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const body = { message, history };
  if (conversationId) body.conversation_id = conversationId;
  if (documentIds?.length) body.document_ids = documentIds;

  const res = await fetch(`${getApiBase()}/api/v1/knowledge/qa/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    rejectHttpFailure(res, json);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("浏览器不支持流式响应");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const block of parts) {
      const line = block
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("data:"));
      if (!line) continue;
      let payload;
      try {
        payload = JSON.parse(line.slice(5).trim());
      } catch {
        continue;
      }
      if (payload.error) {
        onError?.(
          new Error(
            sanitizeUserFacingMessage(payload.error, "检索失败，请稍后重试")
          )
        );
        return;
      }
      if (payload.workflow) onWorkflow?.(payload.workflow);
      if (payload.citations) onCitations?.(payload.citations);
      if (payload.replace != null) onReplace?.(payload.replace);
      if (payload.delta) onDelta?.(payload.delta);
      if (payload.done) {
        onDone?.(payload);
        return;
      }
    }
  }
  onDone?.({});
}

export async function fetchKnowledgeMindmap({ question, answer }) {
  return api("/api/v1/knowledge/qa/mindmap", {
    method: "POST",
    body: JSON.stringify({ question, answer }),
  });
}
