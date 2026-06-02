import { computed, ref } from "vue";

/** 表格勾选与批量操作：selection 列 + checkedRowKeys */
export function useBatchTableSelection(sourceRows, options = {}) {
  const getRowKey = options.getRowKey || ((row) => row.id);
  const canSelect = options.canSelect || (() => true);

  const checkedRowKeys = ref([]);

  const selectedRows = computed(() => {
    const keySet = new Set(checkedRowKeys.value);
    return (sourceRows.value || []).filter((row) => keySet.has(getRowKey(row)));
  });

  const selectedCount = computed(() => checkedRowKeys.value.length);

  const hasSelection = computed(() => selectedCount.value > 0);

  function onCheckedRowKeysChange(keys) {
    checkedRowKeys.value = keys;
  }

  function clearSelection() {
    checkedRowKeys.value = [];
  }

  function selectionColumn(extra = {}) {
    return {
      type: "selection",
      disabled: (row) => !canSelect(row),
      ...extra,
    };
  }

  return {
    checkedRowKeys,
    selectedRows,
    selectedCount,
    hasSelection,
    onCheckedRowKeysChange,
    clearSelection,
    selectionColumn,
  };
}
