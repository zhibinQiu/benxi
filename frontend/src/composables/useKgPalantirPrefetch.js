import {
  fetchKgEntities,
  fetchKgGraph,
  fetchKgMeta,
  fetchKgRelations,
} from "../api/kg.js";
import {
  isKgGraphCacheFresh,
  isKgPalantirMetaCacheFresh,
  readKgEntityListCache,
  readKgGraphCache,
  readKgMetaCache,
  writeKgEntityListCache,
  writeKgGraphCache,
  writeKgMetaCache,
} from "../utils/kgPalantirCache.js";

let prefetchPromise = null;

async function prefetchFirstEntityGraph() {
  const list = readKgEntityListCache(null, "", { allowStale: true });
  const firstId = list?.[0]?.id;
  if (!firstId || isKgGraphCacheFresh(firstId, 1)) return;
  if (readKgGraphCache(firstId, 1, { allowStale: true })?.graph) return;

  try {
    const [graph, relations] = await Promise.all([
      fetchKgGraph({ focusEntityId: firstId, depth: 1 }),
      fetchKgRelations({ entityId: firstId }),
    ]);
    writeKgGraphCache(firstId, 1, { graph, relations });
  } catch {
    /* ignore */
  }
}

async function runKgPalantirPrefetch() {
  const tasks = [];
  if (!readKgMetaCache({ allowStale: true }) || !isKgPalantirMetaCacheFresh()) {
    tasks.push(
      fetchKgMeta({ syncSystem: false })
        .then((data) => writeKgMetaCache(data))
        .catch(() => {})
    );
  }
  if (readKgEntityListCache(null, "", { allowStale: true }) === null) {
    tasks.push(
      fetchKgEntities({})
        .then((data) => writeKgEntityListCache(null, "", data))
        .catch(() => {})
    );
  }
  if (tasks.length) await Promise.all(tasks);
  await prefetchFirstEntityGraph();
}

/** 登录后预取本体元数据、实体列表与首个实体子图，进入页面时可立即展示 */
export function prefetchKgPalantir() {
  const cachedMeta = readKgMetaCache({ allowStale: true });
  const cachedList = readKgEntityListCache(null, "", { allowStale: true });
  if (cachedMeta && cachedList !== null) {
    if (!isKgPalantirMetaCacheFresh() && !prefetchPromise) {
      prefetchPromise = runKgPalantirPrefetch().finally(() => {
        prefetchPromise = null;
      });
    } else if (!prefetchPromise) {
      prefetchPromise = prefetchFirstEntityGraph().finally(() => {
        prefetchPromise = null;
      });
    }
    return;
  }
  if (prefetchPromise) return;
  prefetchPromise = runKgPalantirPrefetch().finally(() => {
    prefetchPromise = null;
  });
}
