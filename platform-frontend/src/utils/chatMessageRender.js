/** 对话消息渲染分级：仅最近若干条挂载富文本 DOM */

import {
  MAX_RICH_RENDER_MESSAGES,
  PLAIN_MESSAGE_PREVIEW_CHARS,
} from "./chatMessageLimits.js";

export function plainMessagePreview(content, max = PLAIN_MESSAGE_PREVIEW_CHARS) {
  const text = String(content || "").trim();
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}

export function shouldRenderMessageRich({
  messageIndex,
  totalMessages,
  message,
  chatDomActive = true,
  expandedIndexes,
  maxRich = MAX_RICH_RENDER_MESSAGES,
}) {
  if (!chatDomActive) return false;
  if (message?.streaming) return true;
  if (expandedIndexes?.has?.(messageIndex)) return true;
  return messageIndex >= totalMessages - maxRich;
}

export function isPlainPreviewTruncated(content, max = PLAIN_MESSAGE_PREVIEW_CHARS) {
  return String(content || "").trim().length > max;
}
