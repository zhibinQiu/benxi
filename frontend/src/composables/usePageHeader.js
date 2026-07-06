import { ref } from "vue";

const pageHeaderOverride = ref(null);

/** 子视图可临时覆盖顶栏标题（如文档中心回收站） */
export function usePageHeader() {
  function setHeaderTitle(title) {
    pageHeaderOverride.value = title || null;
  }

  function clearHeaderTitle() {
    pageHeaderOverride.value = null;
  }

  return { setHeaderTitle, clearHeaderTitle };
}

export function getPageHeaderOverride() {
  return pageHeaderOverride;
}
