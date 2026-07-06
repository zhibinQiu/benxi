import { createSessionTabCache } from "./sessionTabCache.js";

const cache = createSessionTabCache("platform:agent-skills-tools-tab:v1", {
  validate: (data) => Array.isArray(data?.tools),
});

export const readToolsTabCache = cache.read;
export const writeToolsTabCache = cache.write;
export const isToolsTabCacheFresh = cache.isFreshCache;
export const hasToolsTabCacheData = cache.hasData;
