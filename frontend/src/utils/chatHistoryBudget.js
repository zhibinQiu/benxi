/** 发给 API 的 history：条数 + 字符双预算 */

import { MAX_HISTORY_CHARS, MAX_HISTORY_FOR_API } from "./chatMessageLimits.js";

export function trimHistoryForApi(
  messages,
  { maxMessages = MAX_HISTORY_FOR_API, maxChars = MAX_HISTORY_CHARS } = {}
) {
  const rows = (messages || [])
    .filter((m) => m.role === "user" || m.role === "assistant" || m.role === "robot")
    .map((m) => ({
      role: m.role,
      content: String(m.content || ""),
    }));

  const tail = rows.slice(-Math.max(1, maxMessages));
  const kept = [];
  let total = 0;
  for (let i = tail.length - 1; i >= 0; i -= 1) {
    const size = tail[i].content.length;
    if (kept.length && total + size > maxChars) break;
    kept.unshift(tail[i]);
    total += size;
  }
  return kept;
}
