/** PageIndex 实验性树搜索 API */
import { getApiBase, getToken, rejectHttpFailure } from "./http.js";
import { sanitizeUserFacingMessage } from "../utils/uiMessage.js";

export async function fetchPageindexMeta() {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${getApiBase()}/api/v1/pageindex/meta`, { headers });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) rejectHttpFailure(res, json);
  return json.data;
}

export async function pageindexSearchStream(
  { question, documentIds },
  { onDelta, onWorkflow, onCitations, onDone, onError, signal } = {}
) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${getApiBase()}/api/v1/pageindex/search/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question, document_ids: documentIds }),
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
            sanitizeUserFacingMessage(payload.error, "PageIndex 检索失败")
          )
        );
        return;
      }
      if (payload.workflow) onWorkflow?.(payload.workflow);
      if (payload.citations) {
        const mapped = payload.citations.map((c) => ({
          ...c,
          snippet: c.snippet || c.content || "",
          page_number: c.page ?? c.page_number,
        }));
        onCitations?.(mapped);
      }
      if (payload.delta) onDelta?.(payload.delta);
      if (payload.message) {
        onDone?.(payload);
        return;
      }
    }
  }
  onDone?.({});
}
