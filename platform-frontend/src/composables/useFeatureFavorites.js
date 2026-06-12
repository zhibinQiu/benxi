import { ref, watch } from "vue";

const STORAGE_KEY = "platform-feature-favorites";

function loadFavorites() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((id) => typeof id === "string" && id.trim())
      : [];
  } catch {
    return [];
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
