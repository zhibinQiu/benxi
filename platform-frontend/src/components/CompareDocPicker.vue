<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { h, ref, watch } from "vue";
import {
  NButton,
  NDataTable,
  NInput,
  NModal,
  NSpace } from "naive-ui";
import { fetchCompareDocuments } from "../api/client";

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: "选择文档" },
  excludeId: { type: String, default: null },
  excludeIds: { type: Array, default: () => [] }});

const emit = defineEmits(["update:show", "select"]);

const ui = usePlatformUi();
const keyword = ref("");
const page = ref(1);
const items = ref([]);
const loading = ref(false);

function isRowDisabled(row) {
  if (props.excludeId && row.id === props.excludeId) return true;
  return props.excludeIds.includes(row.id);
}

const columns = [
  { title: "标题", key: "title", ellipsis: { tooltip: true } },
  { title: "文件名", key: "file_name", width: 200, ellipsis: { tooltip: true } },
  {
    title: "操作",
    key: "actions",
    width: 72,
    render: (row) =>
      h(
        NButton,
        {
          text: true,
          type: "primary",
          size: "small",
          disabled: isRowDisabled(row),
          onClick: () => onSelect(row)},
        () => (isRowDisabled(row) ? "已选" : "选择")
      )},
];

async function loadDocs() {
  loading.value = true;
  try {
    const data = await fetchCompareDocuments({
      page: page.value,
      page_size: 20,
      keyword: keyword.value || undefined});
    items.value = data.items || [];
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

function onSelect(row) {
  if (isRowDisabled(row)) return;
  emit("select", row);
  emit("update:show", false);
}

function onSearch() {
  page.value = 1;
  loadDocs();
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      page.value = 1;
      loadDocs();
    }
  }
);
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="title"
    style="width: min(720px, 92vw)"
    @update:show="emit('update:show', $event)"
  >
    <n-space :size="10" style="margin-bottom: 12px">
      <n-input
        v-model:value="keyword"
        placeholder="搜索标题或文件名"
        clearable
        style="flex: 1"
        @keyup.enter="onSearch"
      />
      <n-button type="primary" @click="onSearch">搜索</n-button>
    </n-space>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :bordered="false"
      size="small"
    />
  </n-modal>
</template>
