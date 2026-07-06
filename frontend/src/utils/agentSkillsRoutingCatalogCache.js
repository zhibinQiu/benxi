const catalogCache = new Map();

export function readRoutingCatalogCache(filename) {
  return catalogCache.get(filename) || "";
}

export function writeRoutingCatalogCache(filename, text) {
  if (!filename) return;
  catalogCache.set(filename, text || "");
}

export function clearRoutingCatalogCache() {
  catalogCache.clear();
}
