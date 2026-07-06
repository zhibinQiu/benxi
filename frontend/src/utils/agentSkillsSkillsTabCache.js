import { createSessionTabCache } from "./sessionTabCache.js";

const cache = createSessionTabCache("platform:agent-skills-skills-tab:v1", {
  validate: (data) => Array.isArray(data?.registry),
});

export const readSkillsTabCache = cache.read;
export const writeSkillsTabCache = cache.write;
export const isSkillsTabCacheFresh = cache.isFreshCache;
export const hasSkillsTabCacheData = cache.hasData;
