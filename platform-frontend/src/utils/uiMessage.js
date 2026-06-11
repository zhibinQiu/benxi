/** 短时间相同文案只提示一次，避免同一操作链重复弹窗 */
const DEDUPE_MS = 2200;
let lastKey = "";
let lastAt = 0;

export const KNOWLEDGE_UNAVAILABLE =
  "知识服务暂不可用，请稍后重试或联系管理员。";

const VENDOR_RE = /ragflow|knowflow/i;

/** 去掉内部产品名，统一为对用户友好的提示 */
export function sanitizeUserFacingMessage(text, fallback = KNOWLEDGE_UNAVAILABLE) {
  const m = String(text || "").trim();
  if (!m) return fallback;
  if (
    VENDOR_RE.test(m) ||
    m.includes("服务器内部") ||
    m.includes("Internal Server") ||
    m.includes("Connection refused") ||
    m.includes("ECONNREFUSED") ||
    m.includes("QueuePool") ||
    m.includes("连接池")
  ) {
    return fallback;
  }
  if (m.startsWith("自动登录失败")) {
    return KNOWLEDGE_UNAVAILABLE;
  }
  return m;
}

export function notifyDeduped(messageApi, type, text, fallback = "") {
  const fb =
    fallback ||
    (type === "error" ? "操作失败" : type === "warning" ? "请注意" : "操作成功");
  const msg = sanitizeUserFacingMessage(text, fb) || fb;
  const key = `${type}:${msg}`;
  const now = Date.now();
  if (key === lastKey && now - lastAt < DEDUPE_MS) return;
  lastKey = key;
  lastAt = now;
  const fn = messageApi?.[type];
  if (typeof fn === "function") fn(msg);
}

/** 知识服务不可用时的页面提示 */
export function knowflowUnavailableHint(error) {
  return sanitizeUserFacingMessage(error?.message, KNOWLEDGE_UNAVAILABLE);
}
