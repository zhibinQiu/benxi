/** 搜索按钮 → 展开输入框的切换逻辑（类似文档管理搜索） */

import { nextTick, ref } from "vue";

export function useSearchToggle({ onSearch, onClear } = {}) {
  const searchOpen = ref(false);
  const searchInputRef = ref(null);

  function toggleSearch() {
    searchOpen.value = !searchOpen.value;
    if (searchOpen.value) {
      nextTick(() => searchInputRef.value?.focus?.());
    } else {
      onClear?.();
    }
  }

  function closeSearch() {
    searchOpen.value = false;
  }

  return {
    searchOpen,
    searchInputRef,
    toggleSearch,
    closeSearch,
  };
}
