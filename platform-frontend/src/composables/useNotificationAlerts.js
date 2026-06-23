import { ref } from "vue";
import { fetchNotifications, markNotificationRead } from "../api/client";
import { getToken } from "../api/http";

const POLL_MS = 5_000;
const BOOST_POLL_MS = 2_500;
const MAX_TOASTS = 4;
const AUTO_DISMISS_MS = 14_000;
const DEFAULT_BOOST_MS = 15 * 60 * 1000;
/** 客户端与服务器时钟偏差容错（秒），避免新通知在 seed 阶段被误标为已处理 */
const SESSION_CLOCK_SKEW_MS = 120_000;

const activeToasts = ref([]);
const unreadCount = ref(0);
/** 本会话已弹过窗的通知 id（与「铃铛未读」解耦，避免时钟偏差吞掉 toast） */
const toastedIds = new Set();
let seeded = false;
let sessionStartMs = 0;
let pollTimer = null;
let boostUntil = 0;
let pollActive = false;
let onVisibilityChange = null;
const dismissTimers = new Map();

function currentPollMs() {
  return Date.now() < boostUntil ? BOOST_POLL_MS : POLL_MS;
}

function parseNotificationCreatedAt(notification) {
  const raw = notification?.created_at;
  if (!raw) return 0;
  const ts = Date.parse(raw);
  return Number.isFinite(ts) ? ts : 0;
}

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
  const key = `${notification.id}-${Date.now()}`;
  activeToasts.value = [{ key, notification }, ...activeToasts.value].slice(0, MAX_TOASTS);
  vibrateAlert();
  scheduleDismiss(key);
}

function shouldToastNotification(notification) {
  if (!notification?.id || toastedIds.has(notification.id)) return false;
  if (document.hidden) return false;
  return true;
}

function markToasted(notification) {
  if (notification?.id) toastedIds.add(notification.id);
}

async function pollNotifications({ seedOnly = false } = {}) {
  if (!getToken()) return;
  try {
    const data = await fetchNotifications({ page: 1, page_size: 15, unread_only: true });
    const items = data.items || [];
    unreadCount.value = data.total ?? items.length;

    if (!seeded || seedOnly) {
      const start = sessionStartMs || Date.now();
      for (const n of items) {
        const createdAt = parseNotificationCreatedAt(n);
        // 仅抑制「进入页面前」就存在的旧未读；时钟慢的 server 上新建通知不会误入
        if (!createdAt || createdAt < start - SESSION_CLOCK_SKEW_MS) {
          markToasted(n);
        }
      }
      seeded = true;
      if (seedOnly) return;
    }

    for (const n of items) {
      if (!shouldToastNotification(n)) continue;
      markToasted(n);
      pushToast(n);
    }
  } catch {
    /* 轮询失败不打断 UI */
  }
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
  const title = String(ev.title || "");
  if (toolName !== "schedule_notification" && title !== "定时通知已设置") return;

  let boostMs = DEFAULT_BOOST_MS;
  const boostSeconds = Number(ev.boost_seconds);
  if (Number.isFinite(boostSeconds) && boostSeconds > 0) {
    boostMs = (boostSeconds + 30) * 1000;
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
  sessionStartMs = Date.now();
  void pollNotifications({ seedOnly: true });
  onVisibilityChange = () => {
    if (!document.hidden) void pollNotifications();
  };
  document.addEventListener("visibilitychange", onVisibilityChange);
  scheduleNextPoll();
}

export function stopNotificationAlerts() {
  pollActive = false;
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  if (onVisibilityChange) {
    document.removeEventListener("visibilitychange", onVisibilityChange);
    onVisibilityChange = null;
  }
  seeded = false;
  sessionStartMs = 0;
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
