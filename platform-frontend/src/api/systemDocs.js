import { api } from "./http.js";

export function fetchSystemDocCatalog() {
  return api("/api/v1/system/docs/catalog");
}

export function fetchSystemDocContent(path) {
  const q = new URLSearchParams({ path });
  return api(`/api/v1/system/docs/content?${q}`);
}
