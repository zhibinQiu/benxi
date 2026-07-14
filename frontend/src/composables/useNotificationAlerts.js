import { ref } from "vue";
import { fetchNotifications, markNotificationRead } from "../api/client";
import { getToken } from "../api/http";

const POLL_MS = 5_000;
const BOOST_POLL_MS = 2_500;
const MAX_TOASTS = 2;
const AUTO_DISMISS_MS = 14_000;
const DEFAULT_BOOST_MS = 15 * 60 * 1000;

const activeToasts = ref([]);
const unreadCount = ref(0);
/** 本会话已弹过窗的通知 id（与「铃铛未读」解耦） */
const toastedIds = new Set();
let seeded = false;
let pollTimer = null;
let boostUntil = 0;
let pollActive = false;
let onVisibilityChange = null;
const dismissTimers = new Map();

function currentPollMs() {
  return Date.now() < boostUntil ? BOOST_POLL_MS : POLL_MS;
}

let pollLock = Promise.resolve();

function vibrateAlert() {
  try {
    if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
      navigator.vibrate([100, 50, 100, 50, 140]);
    }
  } catch {
    /* ignore */
  }
}

function scheduleDismiss(key) {
  const existing = dismissTimers.get(key);
  if (existing) clearTimeout(existing);
  dismissTimers.set(
    key,
    setTimeout(() => {
      dismissTimers.delete(key);
      dismissToast(key);
    }, AUTO_DISMISS_MS)
  );
}

export function dismissToast(key) {
  activeToasts.value = activeToasts.value.filter((t) => t.key !== key);
  const timer = dismissTimers.get(key);
  if (timer) {
    clearTimeout(timer);
    dismissTimers.delete(key);
  }
}

function pushToast(notification) {
  const id = notification?.id;
  if (id && activeToasts.value.some((t) => t.notification?.id === id)) return;
  const key = `${id}-${Date.now()}`;
  activeToasts.value = [{ key, notification }, ...activeToasts.value].slice(0, MAX_TOASTS);
  vibrateAlert();
  scheduleDismiss(key);
}

/** 同步占位，避免并发轮询对同一通知重复弹窗 */
function reserveToast(notification) {
  if (!notification?.id) return false;
  if (toastedIds.has(notification.id)) return false;
  toastedIds.add(notification.id);
  return true;
}

function shouldToastNotification(notification) {
  return reserveToast(notification);
}

function markToasted(notification) {
  if (notification?.id) toastedIds.add(notification.id);
}

async function executePollNotifications({ seedOnly = false } = {}) {
  const data = await fetchNotifications({ page: 1, page_size: 15, unread_only: true });
  const items = data.items || [];
  unreadCount.value = data.total ?? items.length;

  if (!seeded || seedOnly) {
    // 进入会话时已有的未读只显示在铃铛，不弹窗（不依赖客户端/服务端时钟对齐）
    for (const n of items) {
      markToasted(n);
    }
    seeded = true;
    if (seedOnly) return;
  }

  for (const n of items) {
    if (!shouldToastNotification(n)) continue;
    pushToast(n);
  }
}

async function pollNotifications({ seedOnly = false } = {}) {
  if (!getToken()) return;
  const run = async () => {
    try {
      await executePollNotifications({ seedOnly });
    } catch {
      /* 轮询失败不打断 UI */
    }
  };
  const next = pollLock.then(run, run);
  pollLock = next.catch(() => {});
  return next;
}

function scheduleNextPoll() {
  if (!pollActive) return;
  pollTimer = setTimeout(() => {
    pollTimer = null;
    void pollNotifications();
    scheduleNextPoll();
  }, currentPollMs());
}

/** Agent 设置定时通知后加速轮询，避免短延迟提醒被慢轮询错过。 */
export function boostNotificationPolling(durationMs = DEFAULT_BOOST_MS) {
  boostUntil = Math.max(boostUntil, Date.now() + Math.max(5_000, durationMs));
  void pollNotifications();
}

export function handleAgentWorkflowForNotifications(ev) {
  if (ev?.phase !== "tool_result" || ev?.status === "failed") return;
  const toolName = String(ev.tool_name || "");
  const boostSeconds = Number(ev.boost_seconds);
  const hasBoost = Number.isFinite(boostSeconds) && boostSeconds > 0;

  // schedule_notification / send_notification 直接调用，或有 boost_seconds 的都加速轮询
  const isNotifTool = toolName === "schedule_notification"
    || toolName === "send_notification"
    || hasBoost;

  let boostMs = DEFAULT_BOOST_MS;
  if (hasBoost) {
    boostMs = (boostSeconds + 30) * 1000;
  } else if (!isNotifTool) {
    return;
  }
  // send_notification 已落库，只需立即轮询一次，无需长时间加速
  if (toolName === "send_notification" && !hasBoost) {
    void pollNotifications();
    return;
  }
  boostNotificationPolling(boostMs);
}

export async function acknowledgeToast(toast, { navigate } = {}) {
  const n = toast?.notification;
  if (!n) return;
  dismissToast(toast.key);
  if (!n.read_at) {
    try {
      await markNotificationRead(n.id);
      n.read_at = new Date().toISOString();
      unreadCount.value = Math.max(0, unreadCount.value - 1);
    } catch {
      /* ignore */
    }
  }
  if (n.link && typeof navigate === "function") {
    navigate(n.link);
  }
}

export function startNotificationAlerts() {
  stopNotificationAlerts();
  seeded = false;
  toastedIds.clear();
  boostUntil = 0;
  pollActive = true;
  void pollNotifications({ seedOnly: true });
  onVisibilityChange = () => {
    if (!document.hidden) {
      if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }
      void pollNotifications();
      scheduleNextPoll();
    }
  };
  document.addEventListener("visibilitychange", onVisibilityChange);
  scheduleNextPoll();
}

export function stopNotificationAlerts() {
  pollActive = false;
  pollLock = Promise.resolve();
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  if (onVisibilityChange) {
    document.removeEventListener("visibilitychange", onVisibilityChange);
    onVisibilityChange = null;
  }
  seeded = false;
  toastedIds.clear();
  boostUntil = 0;
  activeToasts.value = [];
  unreadCount.value = 0;
  for (const timer of dismissTimers.values()) clearTimeout(timer);
  dismissTimers.clear();
}

export function refreshNotificationAlerts() {
  return pollNotifications();
}

export function useNotificationAlerts() {
  return {
    activeToasts,
    unreadCount,
    dismissToast,
    acknowledgeToast,
    startNotificationAlerts,
    stopNotificationAlerts,
    refreshNotificationAlerts,
    boostNotificationPolling,
    handleAgentWorkflowForNotifications,
  };
}
