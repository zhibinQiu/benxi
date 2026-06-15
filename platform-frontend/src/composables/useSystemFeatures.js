import { ref } from "vue";
import { fetchSystemFeatures } from "../api/system.js";

const features = ref([]);
const loading = ref(false);
const loaded = ref(false);
const loadError = ref("");
let loadPromise = null;

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
