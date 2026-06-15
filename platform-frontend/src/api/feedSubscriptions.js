/** 资讯订阅（Feed）REST API */
import { api, buildImportToPersonalLibraryBody, IMPORT_API_TIMEOUT_MS } from "./http.js";

export async function fetchFeedPresets() {
  return api("/api/v1/feed-subscriptions/presets");
}

export async function fetchFeedSources({ kind } = {}) {
  const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  return api(`/api/v1/feed-subscriptions/sources${q}`);
}

export async function createFeedSubscription(body) {
  return api("/api/v1/feed-subscriptions/sources", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function subscribeFeedPreset(index) {
  return api(`/api/v1/feed-subscriptions/presets/${index}`, { method: "POST" });
}

export async function deleteFeedSubscription(sourceId) {
  return api(`/api/v1/feed-subscriptions/sources/${sourceId}`, { method: "DELETE" });
}

export async function syncFeedSubscription(sourceId) {
  return api(`/api/v1/feed-subscriptions/sources/${sourceId}/sync`, { method: "POST" });
}

export async function fetchFeedEntries({ page = 1, page_size = 20, source_id, kind } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (source_id) q.set("source_id", source_id);
  if (kind) q.set("kind", kind);
  return api(`/api/v1/feed-subscriptions/entries?${q}`);
}

export async function fetchFeedEntry(entryId) {
  return api(`/api/v1/feed-subscriptions/entries/${entryId}`);
}

export async function importFeedEntry(entryId, body = {}) {
  return api(`/api/v1/feed-subscriptions/entries/${entryId}/import`, {
    method: "POST",
    timeoutMs: IMPORT_API_TIMEOUT_MS,
    body: JSON.stringify(buildImportToPersonalLibraryBody(body)),
  });
}
