<script setup>
import { computed, h, onMounted, ref } from "vue";
import { NButton, NCard, NDataTable, NDivider, NDrawer, NDrawerContent, NInput, NSpace, NTag, NText } from "naive-ui";
import ListRefreshButton from "../ListRefreshButton.vue";
import ListTableFooter from "../ListTableFooter.vue";
import { useClientListPagination } from "../../composables/useClientListPagination.js";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { fetchAgentTools } from "../../api/agentSkills.js";
import {
  hasToolsTabCacheData,
  isToolsTabCacheFresh,
  readToolsTabCache,
  writeToolsTabCache,
} from "../../utils/agentSkillsToolsTabCache.js";

const ui = usePlatformUi();
const { t } = useI18n();

const initialCache = readToolsTabCache({ allowStale: true });
const hydrated = ref(hasToolsTabCacheData(initialCache));

const loading = ref(false);
const tools = ref(initialCache?.tools || []);
const detailOpen = ref(false);
const detail = ref(null);

const {
  page,
  pageSize,
  total,
  pagedItems,
  onPageChange,
} = useClientListPagination(tools);

function toolCategoryLabel(category) {
  return t(`admin.agentSkills.toolCategory.${category}`, category);
}

function openDetail(row) {
  detail.value = row;
  detailOpen.value = true;
}

const columns = computed(() => [
  { title: t("admin.agentSkills.colName"), key: "tool_id", width: 176, ellipsis: { tooltip: true } },
  {
    title: t("admin.agentSkills.colToolType"),
    key: "tool_type",
    width: 132,
    ellipsis: { tooltip: true },
  },
  {
    title: t("admin.agentSkills.colCategory"),
    key: "category",
    width: 128,
    ellipsis: { tooltip: true },
    render: (row) => toolCategoryLabel(row.category),
  },
  {
    title: t("admin.agentSkills.colDescription"),
    key: "description",
    minWidth: 220,
    ellipsis: { tooltip: true },
  },
  {
    title: t("admin.agentSkills.colAvailable"),
    key: "available",
    width: 100,
    render: (row) =>
      h(
        NTag,
        {
          size: "small",
          type: row.available ? "success" : "default",
          bordered: false,
        },
        { default: () => (row.available ? t("admin.agentSkills.availableYes") : t("admin.agentSkills.availableNo")) }
      ),
  },
  {
    title: "",
    key: "actions",
    width: 76,
    render: (row) =>
      h(
        NButton,
        { size: "tiny", quaternary: true, type: "primary", onClick: () => openDetail(row) },
        { default: () => t("common.view") }
      ),
  },
]);

async function load({ background = false, foreground = false } = {}) {
  const showLoading = foreground || (!background && !hydrated.value);
  if (showLoading) loading.value = true;
  try {
    tools.value = (await fetchAgentTools()) || [];
    hydrated.value = true;
    writeToolsTabCache({ tools: tools.value });
  } catch (e) {
    if (!background || !hydrated.value) {
      ui.error(e.message || t("admin.agentSkills.loadFailed"));
    }
  } finally {
    if (showLoading) loading.value = false;
  }
}

onMounted(() => {
  if (hydrated.value) {
    void load({ background: !isToolsTabCacheFresh() });
  } else {
    void load();
  }
});

defineExpose({ load, loading });
</script>

<template>
  <NCard size="small" :title="t('admin.agentSkills.toolsTitle')">
    <template #header-extra>
      <ListRefreshButton :loading="loading" @click="load({ foreground: true })" />
    </template>
    <NText depth="3" style="display: block; margin-bottom: 14px">
      {{ t("admin.agentSkills.toolsHint") }}
    </NText>
    <div class="admin-list-table tools-tab-table">
      <NDataTable
        :loading="loading && !hydrated"
        :columns="columns"
        :data="pagedItems"
        :pagination="false"
      />
      <ListTableFooter
        :page="page"
        :page-size="pageSize"
        :item-count="total"
        @update:page="onPageChange"
      />
    </div>
  </NCard>

  <NDrawer v-if="detailOpen" v-model:show="detailOpen" :width="520" placement="right">
    <NDrawerContent v-if="detail" :title="t('admin.agentSkills.toolDetailTitle')">
      <NSpace vertical :size="12">
        <div><strong>{{ detail.tool_id }}</strong></div>
        <NText depth="3">{{ detail.description }}</NText>
        <NSpace :size="8">
          <NTag size="small" :bordered="false">{{ detail.tool_type }}</NTag>
          <NTag size="small" :bordered="false">{{ toolCategoryLabel(detail.category) }}</NTag>
          <NTag size="small" :bordered="false">{{ detail.tool_version }}</NTag>
          <NTag size="small" :bordered="false">QPS {{ detail.rate_limit?.qps ?? "—" }}</NTag>
        </NSpace>
        <NDivider style="margin: 8px 0" />
        <NText depth="3">{{ t("admin.agentSkills.toolInputSchema") }}</NText>
        <NInput
          type="textarea"
          :rows="8"
          :value="JSON.stringify(detail.input_schema || {}, null, 2)"
          readonly
        />
        <NText depth="3">{{ t("admin.agentSkills.toolOutputSchema") }}</NText>
        <NInput
          type="textarea"
          :rows="5"
          :value="JSON.stringify(detail.output_schema || {}, null, 2)"
          readonly
        />
      </NSpace>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.tools-tab-table :deep(.n-data-table-th),
.tools-tab-table :deep(.n-data-table-td) {
  white-space: nowrap;
}
</style>
