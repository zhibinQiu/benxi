<script setup>
defineOptions({ name: "ReportGenerationView" });
import { computed, onMounted, ref } from "vue";
import { DocumentTextOutline } from "@vicons/ionicons5";
import { NCheckbox } from "naive-ui";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeScopeTree from "../components/KnowledgeScopeTree.vue";
import {
  downloadReportDocx,
  fetchReportGenerationMeta,
  fetchReportMindmap,
  fetchReportOptimizePresets,
  reportGenerationChatStream,
} from "../api/reportGeneration.js";
import { useI18n } from "../composables/useI18n.js";
import { readKnowledgeScopeSelection } from "../utils/knowledgeScopeSelectionCache.js";

const { t } = useI18n();

const conversationId = ref(null);
const selection = ref(readKnowledgeScopeSelection());
const optimizePresets = ref([]);
const useWebSearch = ref(true);
const webSearchAvailable = ref(true);

const suggestions = [
  "生成一份关于全国碳市场纳入行业与发展趋势的研究报告",
  "撰写 AI 在制造业质检场景的应用调研报告，含摘要与建议",
  "整理企业 ESG 披露框架对比分析报告",
];

const selectionHint = computed(() => {
  const count = selection.value?.documentIds?.length || 0;
  const parts = [];
  if (count) {
    parts.push(t("reportGeneration.selectedDocsHint", { count }));
  } else {
    parts.push(t("reportGeneration.noLocalDocsHint"));
  }
  if (useWebSearch.value && webSearchAvailable.value) {
    parts.push(t("reportGeneration.webSearchOnHint"));
  } else if (!webSearchAvailable.value) {
    parts.push(t("reportGeneration.webSearchUnavailableHint"));
  } else {
    parts.push(t("reportGeneration.webSearchOffHint"));
  }
  return parts.join(" · ");
});

function onSelectionChange(next) {
  selection.value = next;
}

async function handleChatStream(params, callbacks) {
  return reportGenerationChatStream(
    {
      ...params,
      documentIds: selection.value?.documentIds || [],
      useWebSearch: useWebSearch.value,
    },
    callbacks
  );
}

onMounted(async () => {
  try {
    const meta = await fetchReportGenerationMeta();
    webSearchAvailable.value = Boolean(meta?.web_search_enabled);
    if (!webSearchAvailable.value) {
      useWebSearch.value = false;
    }
  } catch {
    webSearchAvailable.value = true;
  }
  try {
    optimizePresets.value = (await fetchReportOptimizePresets()) || [];
  } catch {
    optimizePresets.value = [];
  }
});
</script>

<template>
  <FeatureSubsystemShell fill flush-start flush-end :show-intro="false">
    <template #extra>
      <div class="report-gen-toolbar">
        <n-checkbox
          v-model:checked="useWebSearch"
          class="report-gen-toolbar__web"
          :disabled="!webSearchAvailable"
        >
          {{ t("reportGeneration.useWebSearch") }}
        </n-checkbox>
        <span class="report-gen-toolbar-hint">{{ selectionHint }}</span>
      </div>
    </template>

    <div class="report-gen-page">
      <aside class="report-gen-page__sider">
        <KnowledgeScopeTree @selection-change="onSelectionChange" />
      </aside>

      <main class="report-gen-page__main">
        <AiChatPanel
          v-model:conversation-id="conversationId"
          chat-scope="report-generation"
          class="report-gen-page__panel"
          :streaming="true"
          :rich-markdown="true"
          :show-workflow-progress="true"
          :show-citations="true"
          :linkify-citations="true"
          title="报告生成"
          description="大量召回本地知识片段并扩写整合为长报告；支持联网检索、多轮补充与格式调整。非简短归纳式问答。"
          subtitle="报告生成 · 综合 Agent"
          chat-header-sub="联网检索 · 本地知识 · 多轮修订"
          reply-placeholder="补充章节、调整格式或继续追问…"
          :suggestions="suggestions"
          :icon="DocumentTextOutline"
          :stream-chat="handleChatStream"
          :show-report-tools="true"
          :report-mindmap-fetch="fetchReportMindmap"
          :report-word-export="downloadReportDocx"
          :report-optimize-presets="optimizePresets"
          :composer-input-while-loading="true"
          title-gradient
          :show-chat-header-brand="false"
        />
      </main>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.report-gen-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  width: 100%;
}

.report-gen-toolbar__web {
  font-size: 13px;
  color: var(--platform-text);
  white-space: nowrap;
}

.report-gen-toolbar-hint {
  font-size: 12px;
  color: var(--platform-text-secondary);
}

.report-gen-page {
  display: flex;
  height: 100%;
  min-height: 0;
  gap: 0;
}

.report-gen-page__sider {
  flex: 0 0 280px;
  min-width: 240px;
  max-width: 320px;
  border-right: 1px solid var(--platform-accent-border-soft);
  overflow: auto;
}

.report-gen-page__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.report-gen-page__panel {
  flex: 1;
  min-height: 0;
}

@media (max-width: 960px) {
  .report-gen-page {
    flex-direction: column;
  }

  .report-gen-page__sider {
    flex: 0 0 auto;
    max-width: none;
    max-height: 220px;
    border-right: none;
    border-bottom: 1px solid var(--platform-accent-border-soft);
  }
}
</style>
