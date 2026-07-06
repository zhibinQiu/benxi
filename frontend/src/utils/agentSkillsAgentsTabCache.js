import { createSessionTabCache } from "./sessionTabCache.js";

const cache = createSessionTabCache("platform:agent-skills-agents-tab:v1", {
  validate: (data) => Array.isArray(data?.agents),
});

export function hasAgentsTabCacheData(data) {
  return cache.hasData(data);
}

export const isAgentsTabCacheFresh = cache.isFreshCache;
export const readAgentsTabCache = cache.read;
export const writeAgentsTabCache = cache.write;
export const clearAgentsTabCache = cache.clear;
