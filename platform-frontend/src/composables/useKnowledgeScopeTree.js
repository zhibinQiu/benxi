import { ref } from "vue";
import { fetchKnowledgeScopeTree } from "../api/knowledge.js";
import { isRouteAbortError } from "../api/client.js";
import {
  hasKnowledgeScopeTreeItems,
  isKnowledgeScopeTreeCacheFresh,
  readKnowledgeScopeTreeCache,
  writeKnowledgeScopeTreeCache,
} from "../utils/knowledgeScopeTreeCache.js";

const initialCached = readKnowledgeScopeTreeCache({ allowStale: true });

const treePayload = ref(initialCached);
const loading = ref(!hasKnowledgeScopeTreeItems(initialCached));
const loaded = ref(hasKnowledgeScopeTreeItems(initialCached));
let loadPromise = null;
let treeLoadSeq = 0;

async function loadKnowledgeScopeTree({
  force = false,
  background = false,
  refresh = false,
} = {}) {
  if (
    loaded.value &&
    hasKnowledgeScopeTreeItems(treePayload.value) &&
    !force &&
    !refresh
  ) {
    return treePayload.value;
  }
  if (loadPromise && !force && !refresh) {
    if (!background && !hasKnowledgeScopeTreeItems(treePayload.value)) {
      loading.value = true;
    }
    return loadPromise;
  }

  if (!force && !refresh) {
    const cached = readKnowledgeScopeTreeCache({ allowStale: true });
    if (cached) {
      treePayload.value = cached;
      loaded.value = true;
      loading.value = false;
      return cached;
    }
  }

  const seq = ++treeLoadSeq;
  const hadTree = hasKnowledgeScopeTreeItems(treePayload.value);
  if (!background && !hadTree) {
    loading.value = true;
  }

  loadPromise = (async () => {
    try {
      const data = await fetchKnowledgeScopeTree({ refresh });
      if (seq !== treeLoadSeq) {
        if (
          hasKnowledgeScopeTreeItems(data) &&
          !hasKnowledgeScopeTreeItems(treePayload.value)
        ) {
          treePayload.value = data;
          writeKnowledgeScopeTreeCache(data);
          loaded.value = true;
        }
        return treePayload.value;
      }
      if ((background || refresh) && hadTree && !hasKnowledgeScopeTreeItems(data)) {
        return treePayload.value;
      }
      treePayload.value = data;
      writeKnowledgeScopeTreeCache(data);
      loaded.value = hasKnowledgeScopeTreeItems(data);
      return data;
    } catch (e) {
      if (seq !== treeLoadSeq) throw e;
      if (isRouteAbortError(e)) {
        return treePayload.value;
      }
      if (!background && !hasKnowledgeScopeTreeItems(treePayload.value)) {
        loaded.value = false;
      }
      throw e;
    } finally {
      if (seq === treeLoadSeq) {
        loading.value = false;
        loadPromise = null;
      }
    }
  })();
  return loadPromise;
}

/** 登录后或进入主壳时预取：有有效缓存则复用，过期或无缓存再后台拉取 */
export function prefetchKnowledgeScopeTree() {
  const cached = readKnowledgeScopeTreeCache({ allowStale: true });
  if (cached) {
    treePayload.value = cached;
    loaded.value = true;
    loading.value = false;
    if (!isKnowledgeScopeTreeCacheFresh() && !loadPromise) {
      void loadKnowledgeScopeTree({ force: true, background: true }).catch(() => {});
    }
    return;
  }
  if (loadPromise || loaded.value) return;
  void loadKnowledgeScopeTree({ background: true, refresh: false }).catch(() => {});
}

export function invalidateKnowledgeScopeTree() {
  treePayload.value = null;
  loaded.value = false;
  loadPromise = null;
  loading.value = false;
}

export function useKnowledgeScopeTree() {
  return {
    treePayload,
    loading,
    loaded,
    loadKnowledgeScopeTree,
    prefetchKnowledgeScopeTree,
  };
}
