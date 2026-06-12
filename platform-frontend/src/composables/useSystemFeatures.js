import { ref } from "vue";
import { fetchSystemFeatures } from "../api/system.js";

const features = ref([]);
const loading = ref(false);
const loaded = ref(false);
let loadPromise = null;

export function useSystemFeatures() {
  async function loadSystemFeatures(force = false) {
    if (loaded.value && !force) return features.value;
    if (loadPromise && !force) return loadPromise;

    loading.value = true;
    loadPromise = (async () => {
      try {
        features.value = (await fetchSystemFeatures()) || [];
        loaded.value = true;
        return features.value;
      } catch {
        features.value = [];
        loaded.value = true;
        return [];
      } finally {
        loading.value = false;
        loadPromise = null;
      }
    })();
    return loadPromise;
  }

  return { features, loading, loaded, loadSystemFeatures };
}
