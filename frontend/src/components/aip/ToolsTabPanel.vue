<script setup>
import { computed, h, nextTick, onMounted, ref, watch } from "vue";
import { NButton, NDataTable, NDivider, NDrawer, NDrawerContent, NIcon, NInput, NPagination, NSpace, NTag, NText } from "naive-ui";
import { EyeOutline, RefreshOutline, SearchOutline } from "@vicons/ionicons5";
import IconAction from "../IconAction.vue";
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

const props = defineProps({
  refreshing: { type: Boolean, default: false },
  onRefresh: { type: Function, default: null },
});

const initialCache = readToolsTabCache({ allowStale: true });
const hydrated = ref(hasToolsTabCacheData(initialCache));

const loading = ref(false);
const tools = ref(initialCache?.tools || []);
const keyword = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);
const detailOpen = ref(false);
const detail = ref(null);

function toggleSearch() {
  searchOpen.value = !searchOpen.value;
  if (searchOpen.value) {
    nextTick(() => searchInputRef.value?.focus?.());
  } else {
    keyword.value = "";
  }
}

const filteredTools = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  if (!q) return tools.value;
  return tools.value.filter((t) => {
    const hay = [t.tool_id, t.tool_type, t.category, t.description].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(q);
  });
});

const {
  page,
  pageSize,
  total,
  pagedItems,
  onPageChange,
} = useClientListPagination(filteredTools);

const displayInfo = computed(() => {
  if (!total.value) return "";
  const start = (page.value - 1) * pageSize + 1;
  const end = Math.min(page.value * pageSize, total.value);
  return `${total.value}条数据中的 ${start}-${end} 条`;
});

watch(keyword, () => {
  onPageChange(1);
});

function toolCategoryLabel(category) {
  return t(`admin.agentSkills.toolCategory.${category}`, category);
}

function openDetail(row) {
  detail.value = row;
  detailOpen.value = true;
}

const columns = computed(() => [
  {
    title: t("admin.agentSkills.colName"),
    key: "tool_id",
    minWidth: 220,
    ellipsis: { tooltip: true },
    render: (row) =>
      h("div", { style: "display:flex;flex-direction:column;gap:2px;padding:2px 0;" }, [
        h("div", { style: "font-size:var(--platform-font-size-sm);font-weight:500;color:var(--platform-text);line-height:1.4;" }, row.tool_id),
        h("div", { style: "font-size:var(--platform-font-size-sm);color:var(--platform-text-tertiary);line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, row.description || ""),
      ]),
  },
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
    width: 56,
    render: (row) =>
      h(
        NButton,
        { size: "tiny", quaternary: true, circle: true, onClick: () => openDetail(row) },
        { default: () => h(NIcon, null, { default: () => h(EyeOutline) }) }
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

defineExpose({ load, toggleSearch, loading });
</script>

<template>
    <div class="tools-card__header">
      <div class="tools-card__title-row">
        <div class="tools-card__title">{{ t('admin.agentSkills.tabTools') }}</div>
        <div class="tools-card__actions">
          <IconAction
            :label="t('common.search')"
            :icon="SearchOutline"
            :active="searchOpen"
            @click="toggleSearch"
          />
          <IconAction
            v-if="onRefresh"
            :label="t('common.refresh')"
            :icon="RefreshOutline"
            :loading="refreshing"
            @click="onRefresh"
          />
          <NInput
            v-show="searchOpen"
            ref="searchInputRef"
            v-model:value="keyword"
            clearable
            :placeholder="t('admin.agentSkills.searchPlaceholder')"
            style="width: 240px"
          />
        </div>
      </div>
      <div class="tools-card__hint">{{ t('admin.agentSkills.toolbarHint.tools') }}</div>
    </div>
    <div class="tools-card">
      <div class="admin-list-table tools-tab-table">
        <NDataTable
          :loading="loading && !hydrated"
          :columns="columns"
          :data="pagedItems"
          :pagination="false"
        />
      </div>
      <div class="tools-table-footer">
        <span class="tools-table-footer__info">{{ displayInfo }}</span>
        <div class="tools-table-footer__pages">
          <NPagination
            :page="page"
            :page-size="pageSize"
            :item-count="total"
            :page-slot="7"
            @update:page="onPageChange"
          />
        </div>
      </div>
    </div>

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

        <template v-if="detail.doc_text">
          <NDivider style="margin: 8px 0" />
          <NText depth="3" style="margin-bottom: 4px">{{ t("admin.agentSkills.toolUsageGuide") }}</NText>
          <NInput
            type="textarea"
            :rows="12"
            :value="detail.doc_text"
            readonly
            :autosize="{ minRows: 8, maxRows: 30 }"
          />
        </template>

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

.tools-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.tools-card__header {
  margin: 0 0 8px;
  padding-left: 16px;
}

.tools-card__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tools-card__title {
  font-size: var(--platform-font-size-sm);
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.4;
  flex-shrink: 0;
}

.tools-card__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.tools-card__hint {
  margin-top: 2px;
  font-size: var(--platform-font-size-sm);
  font-weight: 400;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}

.tools-card :deep(.n-data-table-th),
.tools-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.tools-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.tools-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}


.tools-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-top: 1px solid var(--platform-border-strong);
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
}

.tools-table-footer__pages :deep(.n-pagination) {
  justify-content: flex-end;
}

.tools-table-footer__pages :deep(.n-pagination-item) {
  font-size: var(--platform-font-size-sm);
}
</style>
