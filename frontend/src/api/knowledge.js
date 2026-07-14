/** 平台原生知识库 / 知识检索 API */
import { api } from "./http.js";
import { createPlatformChatStream } from "./rag.js";
import { sanitizeUserFacingMessage } from "../utils/uiMessage.js";
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

export async function fetchKnowledgeLibraries() {
  return api("/api/v1/knowledge/libraries");
}

export async function fetchLibraryDocuments(
  datasetId,
  { page = 1, pageSize = LIST_PAGE_SIZE, keyword, folderId, virtualFolderId } = {}
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
  { versionId, page = 1, pageSize = LIST_PAGE_SIZE, keywords } = {}
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

/** 重新索引当前用户指定范围内所有未索引或索引失败的文档 */
export async function reindexUnindexedDocuments({
  scope = "personal",
  deptId,
  ownerId,
} = {}) {
  const q = new URLSearchParams({ scope });
  if (deptId) q.set("dept_id", deptId);
  if (ownerId) q.set("owner_id", ownerId);
  return api(`/api/v1/knowledge/documents/reindex-unindexed?${q}`, {
    method: "POST",
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

const _knowledgeQaStream = createPlatformChatStream(
  "/api/v1/knowledge/qa/chat/stream",
  {
    sanitizeErrorMessage: (msg) =>
      sanitizeUserFacingMessage(msg, "检索失败，请稍后重试"),
  }
);

/** 流式问答，供知识检索 AiChatPanel 使用 */
export async function knowledgeQaChatStream(
  { message, history = [], conversationId = null, documentIds = null, useAgentic = true },
  callbacks = {}
) {
  return _knowledgeQaStream(
    {
      message,
      history,
      conversationId,
      use_agentic: useAgentic,
      ...(documentIds?.length ? { document_ids: documentIds } : {}),
    },
    callbacks
  );
}

export async function fetchKnowledgeMindmap({ question, answer }) {
  return api("/api/v1/knowledge/qa/mindmap", {
    method: "POST",
    body: JSON.stringify({ question, answer }),
  });
}
