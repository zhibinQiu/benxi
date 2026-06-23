/** 对话页内存控制：限制 DOM / sessionStorage 中的消息条数 */

/** 页面上默认渲染的最大消息条数（超出可点「加载更早」） */
export const MAX_VISIBLE_CHAT_MESSAGES = 24;

/** 内存与 sessionStorage 保留的上限 */
export const MAX_CHAT_MESSAGES = 48;

/** 同时渲染 Markdown / 图表的最大 assistant 条数（其余降级为纯文本预览） */
export const MAX_RICH_RENDER_MESSAGES = 4;

/** 降级预览的单条字符上限 */
export const PLAIN_MESSAGE_PREVIEW_CHARS = 320;

/** sessionStorage 单条 assistant 正文上限（报告类长文） */
export const MAX_PERSISTED_MESSAGE_CHARS = 48000;

/** 发给后端的 history 条数上限 */
export const MAX_HISTORY_FOR_API = 8;

/** 发给后端的 history 总字符预算 */
export const MAX_HISTORY_CHARS = 6000;

export function trimChatMessages(messages, max = MAX_CHAT_MESSAGES) {
  const list = messages || [];
  if (list.length <= max) return list;
  return list.slice(-max);
}

export function chatMessageWindowStart(total, windowSize = MAX_VISIBLE_CHAT_MESSAGES, currentStart = 0) {
  if (total <= windowSize) return 0;
  return Math.max(currentStart, total - windowSize);
}
