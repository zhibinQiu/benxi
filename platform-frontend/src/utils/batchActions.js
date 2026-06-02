/** 逐条执行删除类操作，汇总成功/失败（无批量 API 时使用） */
export async function deleteSequentially(items, deleteFn) {
  const failed = [];
  let deleted = 0;
  for (const item of items) {
    try {
      await deleteFn(item);
      deleted += 1;
    } catch (e) {
      failed.push({ item, message: e?.message || "未知错误" });
    }
  }
  return { deleted, failed };
}
