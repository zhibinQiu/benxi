import { computed, ref, unref, watch } from "vue";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";

/** 前端分页：配合 ListTableFooter，表格 data 传 pagedItems */
export function useClientListPagination(itemsSource, { pageSize = LIST_PAGE_SIZE } = {}) {
  const page = ref(1);
  const items = computed(() => unref(itemsSource) ?? []);

  const total = computed(() => items.value.length);
  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

  const pagedItems = computed(() => {
    const start = (page.value - 1) * pageSize;
    return items.value.slice(start, start + pageSize);
  });

  watch(pageCount, (count) => {
    if (page.value > count) page.value = count;
  });

  function onPageChange(next) {
    page.value = next;
  }

  function resetPage() {
    page.value = 1;
  }

  return {
    page,
    pageSize,
    total,
    pageCount,
    pagedItems,
    onPageChange,
    resetPage,
  };
}
