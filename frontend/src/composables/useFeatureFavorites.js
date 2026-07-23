import { ref, watch } from "vue";

const STORAGE_KEY = "platform-feature-favorites";
const MIGRATION_KEY = "platform-feature-favorites-defaults-v1";
const CLEANUP_MIGRATION_KEY = "platform-feature-favorites-cleanup-v2";

/** 侧栏默认收藏：知识检索、报告生成 */
export const DEFAULT_FEATURE_FAVORITE_IDS = [
  "knowledge_search",
  "report_generation",
];

/**
 * 已有独立侧栏入口的功能，不应再作为收藏项出现在侧栏，
 * 也不在功能列表中展示（避免「本体定义」等重复）。
 */
export const SIDEBAR_DEDICATED_FEATURE_IDS = Object.freeze([
  "ai_home",
  "agent_skills",
  "ontology",
]);

const SIDEBAR_DEDICATED_SET = new Set(SIDEBAR_DEDICATED_FEATURE_IDS);

function stripDedicatedFavorites(ids) {
  return ids.filter((id) => !SIDEBAR_DEDICATED_SET.has(id));
}

function mergeDefaultFavorites(ids) {
  const rest = ids.filter((id) => !DEFAULT_FEATURE_FAVORITE_IDS.includes(id));
  return [...DEFAULT_FEATURE_FAVORITE_IDS, ...rest];
}

function loadFavorites() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    let ids = [];
    if (raw) {
      const parsed = JSON.parse(raw);
      ids = Array.isArray(parsed)
        ? parsed.filter((id) => typeof id === "string" && id.trim())
        : [];
    }
    if (localStorage.getItem(MIGRATION_KEY) !== "1") {
      ids = mergeDefaultFavorites(ids);
      ids = stripDedicatedFavorites(ids);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
      localStorage.setItem(MIGRATION_KEY, "1");
      localStorage.setItem(CLEANUP_MIGRATION_KEY, "1");
      return ids;
    }
    /* 迁移：移除侧栏中已独立入口的功能（避免菜单重复） */
    if (localStorage.getItem(CLEANUP_MIGRATION_KEY) !== "1") {
      ids = stripDedicatedFavorites(ids);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
      localStorage.setItem(CLEANUP_MIGRATION_KEY, "1");
      return ids;
    }
    if (!raw) {
      return [...DEFAULT_FEATURE_FAVORITE_IDS];
    }
    return stripDedicatedFavorites(ids);
  } catch {
    return [...DEFAULT_FEATURE_FAVORITE_IDS];
  }
}

const favoriteIds = ref(loadFavorites());

watch(
  favoriteIds,
  (value) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  },
  { deep: true },
);

export function useFeatureFavorites() {
  function isFavorite(id) {
    return favoriteIds.value.includes(id);
  }

  function toggleFavorite(id) {
    const next = String(id || "").trim();
    if (!next || SIDEBAR_DEDICATED_SET.has(next)) return;
    if (favoriteIds.value.includes(next)) {
      favoriteIds.value = favoriteIds.value.filter((item) => item !== next);
    } else {
      favoriteIds.value = [...favoriteIds.value, next];
    }
  }

  return { favoriteIds, isFavorite, toggleFavorite };
}
