import { api, getApiBase, getToken, rejectHttpFailure } from "./http.js";
import { createPlatformChatStream } from "./rag.js";
import { sanitizeUserFacingMessage } from "../utils/uiMessage.js";
import { downloadBlob } from "../utils/downloadBlob.js";

export async function fetchReportGenerationMeta() {
  return api("/api/v1/report-generation/meta", { preserveOnNavigate: true });
}

export async function fetchReportOptimizePresets() {
  return api("/api/v1/report-generation/presets", { preserveOnNavigate: true });
}

export async function fetchReportAgentSkills() {
  return api("/api/v1/report-generation/skills", { preserveOnNavigate: true });
}

export async function fetchReportMindmap({ question, answer }) {
  return api("/api/v1/report-generation/mindmap", {
    method: "POST",
    body: JSON.stringify({ question, answer }),
  });
}

export async function downloadReportDocx({ title, markdown }) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${getApiBase()}/api/v1/report-generation/export/docx`, {
    method: "POST",
    headers,
    body: JSON.stringify({ title, markdown }),
  });

  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    rejectHttpFailure(res, json);
  }

  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const utf8Match = disp.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disp.match(/filename="([^"]+)"/);
  let name = "研究报告.docx";
  if (utf8Match) {
    try {
      name = decodeURIComponent(utf8Match[1]);
    } catch {
      name = utf8Match[1];
    }
  } else if (plainMatch) {
    name = plainMatch[1];
  } else if (title) {
    name = `${String(title).replace(/[\\/:*?"<>|]+/g, "_").slice(0, 80) || "研究报告"}.docx`;
  }
  downloadBlob(blob, name);
}

export async function importReportToLibrary({ title, markdown, syncKnowflow = true }) {
  return api("/api/v1/report-generation/import-library", {
    method: "POST",
    body: JSON.stringify({
      title,
      markdown,
      sync_knowflow: syncKnowflow,
    }),
  });
}

const baseReportGenerationChatStream = createPlatformChatStream(
  "/api/v1/report-generation/chat/stream",
  {
    sanitizeErrorMessage: (error) =>
      sanitizeUserFacingMessage(error, "报告生成失败，请稍后重试"),
  },
);

export function reportGenerationChatStream(
  { message, history = [], conversationId = null, documentIds = null },
  handlers,
) {
  const extraBody = documentIds?.length ? { document_ids: documentIds } : {};
  return baseReportGenerationChatStream(
    { message, history, conversationId, ...extraBody },
    handlers,
  );
}
