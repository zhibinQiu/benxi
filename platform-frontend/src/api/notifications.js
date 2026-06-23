/** 站内通知 REST API */
import { api } from "./http.js";

export async function fetchNotifications({ page = 1, page_size = 15, unread_only = false } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (unread_only) q.set("unread_only", "true");
  return api(`/api/v1/notifications?${q}`);
}

export async function markNotificationRead(id) {
  return api(`/api/v1/notifications/${id}/read`, { method: "PATCH" });
}

export async function markAllNotificationsRead() {
  return api("/api/v1/notifications/read-all", { method: "PATCH" });
}
