import { fetchKgEntities, fetchKgMeta } from "../api/kg.js";
import {
  isKgPalantirMetaCacheFresh,
  readKgEntityListCache,
  readKgMetaCache,
  writeKgEntityListCache,
  writeKgMetaCache,
} from "../utils/kgPalantirCache.js";

let prefetchPromise = null;

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
}

/** 登录后预取本体元数据与默认实体列表，进入页面时可立即展示 */
export function prefetchKgPalantir() {
  const cachedMeta = readKgMetaCache({ allowStale: true });
  const cachedList = readKgEntityListCache(null, "", { allowStale: true });
  if (cachedMeta && cachedList !== null) {
    if (!isKgPalantirMetaCacheFresh() && !prefetchPromise) {
      prefetchPromise = runKgPalantirPrefetch().finally(() => {
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
