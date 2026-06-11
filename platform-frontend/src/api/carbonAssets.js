/** 碳资产交易演示 REST API */
import { api } from "./http.js";

export async function fetchCarbonAssetOverview() {
  return api("/api/v1/carbon-assets/overview");
}

export async function fetchCarbonAssetHoldings() {
  return api("/api/v1/carbon-assets/holdings");
}

export async function fetchCarbonAssetMarket({ refresh = false } = {}) {
  const q = refresh ? "?refresh=true" : "";
  return api(`/api/v1/carbon-assets/market${q}`);
}

export async function fetchCarbonAssetHistory(assetCode, { days = 90 } = {}) {
  const q = new URLSearchParams({ days: String(days) });
  return api(`/api/v1/carbon-assets/market/${encodeURIComponent(assetCode)}/history?${q}`);
}

export async function fetchCarbonAssetTrades() {
  return api("/api/v1/carbon-assets/trades");
}

export async function createCarbonAssetTrade(body) {
  return api("/api/v1/carbon-assets/trades", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function resetCarbonAssetDemo() {
  return api("/api/v1/carbon-assets/demo/reset", { method: "POST" });
}
