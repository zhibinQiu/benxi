/** 有界 Map：超出上限时按插入顺序淘汰最旧项，避免会话内缓存无限增长 */

export function trimBoundedMap(map, maxSize) {
  if (!map || maxSize <= 0 || map.size <= maxSize) return;
  const drop = map.size - maxSize;
  const iter = map.keys();
  for (let i = 0; i < drop; i += 1) {
    const next = iter.next();
    if (next.done) break;
    map.delete(next.value);
  }
}
