/** 平台原生对话流式 API（AI 智能体 / 智能问数 / 双碳问答） */
import { getApiBase, getToken, rejectHttpFailure } from "./http.js";

export function createPlatformChatStream(path) {
  return async function platformChatStream(
    { message, history = [], conversationId = null },
    { onDelta, onReplace, onWorkflow, onCitations, onDone, onError, signal } = {}
  ) {
    const headers = { "Content-Type": "application/json" };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const body = { message, history };
    if (conversationId) body.conversation_id = conversationId;

    const res = await fetch(`${getApiBase()}${path}`, {
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
    let hasContent = false;

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
          // 正文已输出后的上游错误（常见于引用检索节点）不应覆盖成功回答
          if (hasContent) {
            console.warn("[chat-stream] ignored post-answer error:", payload.error);
            continue;
          }
          onError?.(new Error(payload.error));
          return;
        }
        if (payload.workflow) onWorkflow?.(payload.workflow);
        if (payload.replace != null) {
          hasContent = Boolean(String(payload.replace).trim());
          onReplace?.(payload.replace);
        }
        if (payload.citations) onCitations?.(payload.citations);
        if (payload.delta) {
          hasContent = true;
          onDelta?.(payload.delta);
        }
        if (payload.done) {
          if ((payload.reply || "").trim()) hasContent = true;
          onDone?.(payload);
          return;
        }
      }
    }
    onDone?.({});
  };
}

export const aiHomeChatStream = createPlatformChatStream("/api/v1/ai-chat/chat/stream");

export const smartDataQueryChatStream = createPlatformChatStream(
  "/api/v1/smart-data-query/chat/stream"
);

export const carbonQaChatStream = createPlatformChatStream(
  "/api/v1/carbon-qa/chat/stream"
);
