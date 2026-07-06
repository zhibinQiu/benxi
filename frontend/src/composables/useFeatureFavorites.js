import { ref, watch } from "vue";

const STORAGE_KEY = "platform-feature-favorites";
const MIGRATION_KEY = "platform-feature-favorites-defaults-v1";

/** 侧栏默认收藏：知识检索、报告生成、Agent Skills、本体图谱 */
export const DEFAULT_FEATURE_FAVORITE_IDS = [
  "knowledge_search",
  "report_generation",
  "agent_skills",
  "kg_palantir",
];

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
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
      localStorage.setItem(MIGRATION_KEY, "1");
      return ids;
    }
    if (!raw) {
      return [...DEFAULT_FEATURE_FAVORITE_IDS];
    }
    return ids;
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
    if (!next) return;
    if (favoriteIds.value.includes(next)) {
      favoriteIds.value = favoriteIds.value.filter((item) => item !== next);
    } else {
      favoriteIds.value = [...favoriteIds.value, next];
    }

  }

  return { favoriteIds, isFavorite, toggleFavorite };
}
