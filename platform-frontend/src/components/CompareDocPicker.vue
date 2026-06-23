<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n.js";
import { computed, h, ref, watch } from "vue";
import {
  NButton,
  NDataTable,
  NInput,
  NModal,
  NPagination,
  NSpace } from "naive-ui";
import { fetchCompareDocuments } from "../api/client";
import { PLATFORM_Z } from "../constants/zIndex.js";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import ListRefreshButton from "./ListRefreshButton.vue";

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: "" },
  excludeId: { type: String, default: null },
  excludeIds: { type: Array, default: () => [] }});

const emit = defineEmits(["update:show", "select"]);

const ui = usePlatformUi();
const { t } = useI18n();
const keyword = ref("");
const page = ref(1);
const total = ref(0);
const items = ref([]);
const loading = ref(false);

const modalTitle = computed(() => props.title || t("compare.pickerDefaultTitle"));
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / LIST_PAGE_SIZE)));
const showPager = computed(() => total.value > LIST_PAGE_SIZE);

function isRowDisabled(row) {
  if (props.excludeId && row.id === props.excludeId) return true;
  return props.excludeIds.includes(row.id);
}

const columns = computed(() => [
  { title: t("compare.pickerTitle"), key: "title", ellipsis: { tooltip: true } },
  {
    title: t("compare.pickerFileName"),
    key: "file_name",
    width: 200,
    ellipsis: { tooltip: true },
  },
  {
    title: t("compare.pickerAction"),
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
        () => (isRowDisabled(row) ? t("compare.pickerSelected") : t("compare.pickerSelect"))
      )},
]);

async function loadDocs() {
  loading.value = true;
  try {
    const data = await fetchCompareDocuments({
      page: page.value,
      page_size: LIST_PAGE_SIZE,
      keyword: keyword.value || undefined});
    items.value = data.items || [];
    total.value = data.total ?? 0;
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

function onPageChange(nextPage) {
  page.value = nextPage;
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
    :title="modalTitle"
    :z-index="PLATFORM_Z.featureModal"
    style="width: min(720px, 92vw)"
    @update:show="emit('update:show', $event)"
  >
    <n-space :size="10" style="margin-bottom: 12px">
      <n-input
        v-model:value="keyword"
        :placeholder="t('compare.searchDocPlaceholder')"
        clearable
        style="flex: 1"
        @keyup.enter="onSearch"
      />
      <n-button type="primary" @click="onSearch">{{ t("compare.searchBtn") }}</n-button>
      <ListRefreshButton :loading="loading" @click="loadDocs" />
    </n-space>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :bordered="false"
      size="small"
    />
    <n-space v-if="showPager" justify="center" style="margin-top: 12px">
      <n-pagination
        :page="page"
        :page-count="pageCount"
        :page-slot="7"
        @update:page="onPageChange"
      />
    </n-space>
  </n-modal>
</template>
