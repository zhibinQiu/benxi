import { ref } from "vue";
import { fetchSystemFeatures } from "../api/system.js";

const SYSTEM_FEATURES_CACHE_KEY = "platform:system-features";
const SYSTEM_FEATURES_TTL = 300_000; // 5min

const features = ref([]);
const loading = ref(false);
const loaded = ref(false);
const loadError = ref("");
let loadPromise = null;

/** 从 sessionStorage 还原功能列表（避免页面刷新后 beforeEach 阻塞） */
function _restoreCachedFeatures() {
  try {
    const raw = sessionStorage.getItem(SYSTEM_FEATURES_CACHE_KEY);
    if (!raw) return false;
    const { data, savedAt } = JSON.parse(raw);
    if (Date.now() - savedAt > SYSTEM_FEATURES_TTL) {
      sessionStorage.removeItem(SYSTEM_FEATURES_CACHE_KEY);
      return false;
    }
    features.value = data || [];
    loaded.value = true;
    return true;
  } catch {
    return false;
  }
}
_restoreCachedFeatures();

export function useSystemFeatures() {
  async function loadSystemFeatures(force = false) {
    if (loaded.value && !force) return features.value;
    if (loadPromise && !force) return loadPromise;

    loading.value = true;
    loadError.value = "";
    loadPromise = (async () => {
      try {
        features.value = (await fetchSystemFeatures()) || [];
        loaded.value = true;
        try {
          sessionStorage.setItem(SYSTEM_FEATURES_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), data: features.value }));
        } catch { /* quota exceeded */ }
        return features.value;
      } catch (err) {
        features.value = [];
        loaded.value = false;
        loadError.value = err?.message || "加载功能列表失败";
        throw err;
      } finally {
        loading.value = false;
        loadPromise = null;
      }
    })();
    return loadPromise;
  }

  return { features, loading, loaded, loadError, loadSystemFeatures };
}
