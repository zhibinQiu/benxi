/** 微信公众号资讯 REST API */
import { api, buildImportToPersonalLibraryBody } from "./http.js";

export async function parseWechatMpUrl(url) {
  return api("/api/v1/wechat-mp/parse-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function fetchWechatMpSources() {
  return api("/api/v1/wechat-mp/sources");
}

export async function createWechatMpSource({ name, sample_url, biz }) {
  return api("/api/v1/wechat-mp/sources", {
    method: "POST",
    body: JSON.stringify({ name, sample_url, biz: biz || undefined }),
  });
}

export async function deleteWechatMpSource(sourceId) {
  return api(`/api/v1/wechat-mp/sources/${sourceId}`, { method: "DELETE" });
}

export async function syncWechatMpSource(sourceId) {
  return api(`/api/v1/wechat-mp/sources/${sourceId}/sync`, { method: "POST" });
}

export async function fetchWechatMpArticles({ page = 1, page_size = 20, source_id } = {}) {
  const q = new URLSearchParams({ page, page_size });
  if (source_id) q.set("source_id", source_id);
  return api(`/api/v1/wechat-mp/articles?${q}`);
}

export async function fetchWechatMpArticle(articleId) {
  return api(`/api/v1/wechat-mp/articles/${articleId}`);
}

export async function ingestWechatMpUrl(url) {
  return api("/api/v1/wechat-mp/articles/ingest-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function importWechatMpArticle(articleId, body = {}) {
  return api(`/api/v1/wechat-mp/articles/${articleId}/import`, {
    method: "POST",
    body: JSON.stringify(buildImportToPersonalLibraryBody(body)),
  });
}
