<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n.js";
import { computed, h, ref, watch } from "vue";
import {
  NButton,
  NDataTable,
  NInput,
  NSpace,
  NSpin,
  NTag,
} from "naive-ui";
import { fetchCompareDocuments } from "../api/client";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import {
  fileFormatLabel,
  formatDocumentFormatLabel,
} from "../constants/documentUpload.js";
import AdminFormModal from "./AdminFormModal.vue";
import ListRefreshButton from "./ListRefreshButton.vue";
import ListTableFooter from "./ListTableFooter.vue";

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
function isRowDisabled(row) {
  if (props.excludeId && row.id === props.excludeId) return true;
  return props.excludeIds.includes(row.id);
}

const columns = computed(() => [
  {
    title: t("documents.columns.title"),
    key: "title",
    ellipsis: { tooltip: true },
    render: (row) => row.title || "—",
  },
  {
    title: t("documents.columns.format"),
    key: "file_format",
    width: 115,
    render: (row) => {
      const label = formatDocumentFormatLabel(
        fileFormatLabel(row.file_name, row.mime_type)
      );
      if (label === "—") return "—";
      return h(
        NTag,
        { size: "small", bordered: false, type: "info" },
        { default: () => label }
      );
    },
  },
  {
    title: t("compare.pickerAction"),
    key: "actions",
    width: 86,
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
  <AdminFormModal
    :show="show"
    :title="modalTitle"
    width="min(864px, 92vw)"
    @update:show="emit('update:show', $event)"
  >
    <n-space :size="12" style="margin-bottom: 14px">
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
    <n-spin :show="loading" class="compare-select-spin platform-local-spin" local>
      <div class="admin-list-table">
        <n-data-table
          :columns="columns"
          :data="items"
          :bordered="false"
          size="small"
          :pagination="false"
        />
        <ListTableFooter
          :page="page"
          :page-size="LIST_PAGE_SIZE"
          :item-count="total"
          @update:page="onPageChange"
        />
      </div>
    </n-spin>
  </AdminFormModal>
</template>
