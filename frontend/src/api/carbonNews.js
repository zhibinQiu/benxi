/** 碳新闻：实时爬取 + 一问一答 */
import { api, IMPORT_API_TIMEOUT_MS } from "./http.js";

/** 一次爬取最多 100 条详情，耗时较长 */
const CRAWL_TIMEOUT_MS = 600_000;

export async function crawlCarbonNews({
  keyword = "碳",
  limit = 100,
} = {}) {
  return api("/api/v1/carbon-news/crawl", {
    method: "POST",
    body: JSON.stringify({ keyword, limit }),
    timeoutMs: CRAWL_TIMEOUT_MS,
  });
}

export async function askCarbonNews({ question, items }) {
  return api("/api/v1/carbon-news/ask", {
    method: "POST",
    body: JSON.stringify({ question, items }),
    timeoutMs: IMPORT_API_TIMEOUT_MS,
  });
}
