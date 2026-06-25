import { ref } from "vue";
import { fetchKnowledgeScopeTree } from "../api/knowledge.js";
import {
  readKnowledgeScopeTreeCache,
  writeKnowledgeScopeTreeCache,
} from "../utils/knowledgeScopeTreeCache.js";

const initialCached = readKnowledgeScopeTreeCache({ allowStale: true });

const treePayload = ref(initialCached);
const loading = ref(!initialCached);
const loaded = ref(Boolean(initialCached));
let loadPromise = null;

function hasTreeItems(payload) {
  return Array.isArray(payload?.items) && payload.items.length > 0;
}

async function loadKnowledgeScopeTree({
  force = false,
  background = false,
  refresh = false,
} = {}) {
  if (loaded.value && treePayload.value && !force && !refresh && !background) {
    return treePayload.value;
  }
  if (loadPromise && !force && !refresh) return loadPromise;

  if (!force && !refresh && !background) {
    const cached = readKnowledgeScopeTreeCache({ allowStale: true });
    if (cached) {
      treePayload.value = cached;
      loaded.value = true;
      void loadKnowledgeScopeTree({ force: true, background: true, refresh: false }).catch(
        () => {}
      );
      return cached;
    }
  }

  const hadTree = hasTreeItems(treePayload.value);
  if (!background && !hadTree) {
    loading.value = true;
  }

  loadPromise = (async () => {
    try {
      const data = await fetchKnowledgeScopeTree({ refresh: refresh || force });
      treePayload.value = data;
      writeKnowledgeScopeTreeCache(data);
      loaded.value = true;
      return data;
    } catch (e) {
      if (!background && !hasTreeItems(treePayload.value)) {
        loaded.value = false;
      }
      throw e;
    } finally {
      loading.value = false;
      loadPromise = null;
    }
  })();
  return loadPromise;
}

/** 登录后或进入主壳时预取，减少首次点开知识检索/报告生成的等待 */
export function prefetchKnowledgeScopeTree() {
  const cached = readKnowledgeScopeTreeCache({ allowStale: true });
  if (cached) {
    treePayload.value = cached;
    loaded.value = true;
    void loadKnowledgeScopeTree({ force: true, background: true, refresh: false }).catch(
      () => {}
    );
    return;
  }
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
