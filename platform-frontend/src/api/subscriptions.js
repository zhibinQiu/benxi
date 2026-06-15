/** 统一资讯订阅 REST API */
import { api, IMPORT_API_TIMEOUT_MS } from "./http.js";

export async function ingestSubscriptionUrl(url) {
  return api("/api/v1/subscriptions/ingest-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function fetchSubscriptionItems({
  page = 1,
  page_size = 20,
  keyword,
  created_from,
  created_to,
} = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (keyword) q.set("keyword", keyword);
  if (created_from) q.set("created_from", created_from);
  if (created_to) q.set("created_to", created_to);
  return api(`/api/v1/subscriptions/items?${q}`);
}

export async function fetchSubscriptionItem(ref) {
  return api(`/api/v1/subscriptions/items/${encodeURIComponent(ref)}`);
}

export async function importSubscriptionItem(ref, body = {}) {
  return api(`/api/v1/subscriptions/items/${encodeURIComponent(ref)}/import`, {
    method: "POST",
    timeoutMs: IMPORT_API_TIMEOUT_MS,
    body: JSON.stringify({
      sync_knowflow: body.sync_knowflow !== false,
      ...body,
    }),
  });
}

export async function deleteSubscriptionItem(ref) {
  return api(`/api/v1/subscriptions/items/${encodeURIComponent(ref)}`, {
    method: "DELETE",
  });
}

export async function fetchWebSearchStatus() {
  return api("/api/v1/subscriptions/web-search/status");
}

export async function searchSubscriptionWeb({ q, page = 1, page_size = 20 } = {}) {
  const params = new URLSearchParams({ q, page, page_size });
  return api(`/api/v1/subscriptions/web-search?${params}`);
}
