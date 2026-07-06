/** 并发执行删除类操作，汇总成功/失败（无批量 API 时使用） */
export async function deleteSequentially(items, deleteFn, { concurrency = 5 } = {}) {
  const failed = [];
  let deleted = 0;
  if (!items.length) {
    return { deleted, failed };
  }

  const queue = [...items];
  const workers = Math.min(Math.max(1, concurrency), queue.length);

  async function worker() {
    while (queue.length) {
      const item = queue.shift();
      try {
        await deleteFn(item);
        deleted += 1;
      } catch (e) {
        failed.push({ item, message: e?.message || "未知错误" });
      }
    }
  }

  await Promise.all(Array.from({ length: workers }, () => worker()));
  return { deleted, failed };
}
