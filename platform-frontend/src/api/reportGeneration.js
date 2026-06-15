import { api, getApiBase, getToken, rejectHttpFailure } from "./http.js";
import { sanitizeUserFacingMessage } from "../utils/uiMessage.js";

export async function fetchReportGenerationMeta() {
  return api("/api/v1/report-generation/meta");
}

export async function fetchReportOptimizePresets() {
  return api("/api/v1/report-generation/presets");
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
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function reportGenerationChatStream(
  { message, history = [], conversationId = null, documentIds = null, useWebSearch = true },
  { onDelta, onReplace, onWorkflow, onCitations, onDone, onError, signal } = {}
) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const body = { message, history, use_web_search: useWebSearch };
  if (conversationId) body.conversation_id = conversationId;
  if (documentIds?.length) body.document_ids = documentIds;

  const res = await fetch(`${getApiBase()}/api/v1/report-generation/chat/stream`, {
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
            sanitizeUserFacingMessage(payload.error, "报告生成失败，请稍后重试")
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
