<script setup>
defineOptions({ name: "ReportGenerationView" });
import { computed, onMounted, ref } from "vue";
import { CreateOutline } from "@vicons/ionicons5";
import { NCheckbox } from "naive-ui";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import HintTooltip from "../components/HintTooltip.vue";
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

const { t, tm } = useI18n();

const conversationId = ref(null);
const selection = ref(readKnowledgeScopeSelection());
const optimizePresets = ref([]);
const useWebSearch = ref(true);
const useAgentic = ref(true);
const webSearchAvailable = ref(true);

const suggestions = computed(() => tm("reportGeneration.suggestions") || []);

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
      useAgentic: useAgentic.value,
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
        <label class="report-gen-toolbar__agent">
          <n-checkbox v-model:checked="useAgentic" size="small">
            {{ t("reportGeneration.useAgent") }}
          </n-checkbox>
          <HintTooltip
            :text="t('reportGeneration.useAgentTooltip')"
            variant="inline"
            placement="bottom"
          />
        </label>
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
          :title="t('reportGeneration.chatTitle')"
          :description="t('reportGeneration.chatDescription')"
          :subtitle="t('reportGeneration.chatSubtitle')"
          :chat-header-sub="t('reportGeneration.chatHeaderSub')"
          :reply-placeholder="t('reportGeneration.replyPlaceholder')"
          :suggestions="suggestions"
          :icon="CreateOutline"
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

.report-gen-toolbar__agent {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--platform-text);
  cursor: pointer;
  user-select: none;
}

.report-gen-toolbar-hint {
  font-size: 12px;
  color: var(--platform-text-secondary);
}

.report-gen-page {
  display: flex;
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
  box-sizing: border-box;
  border-radius: 0;
  overflow: hidden;
  border: 1px solid var(--platform-border);
  border-left: none;
  border-right: none;
  background: var(--platform-bg-elevated);
}

.report-gen-page__sider {
  flex-shrink: 0;
  width: min(300px, 36vw);
  min-width: 228px;
  border-right: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  display: flex;
  flex-direction: column;
  min-height: 0;
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
  border-radius: 0 !important;
}

@media (max-width: 900px) {
  .report-gen-page {
    flex-direction: column;
  }

  .report-gen-page__sider {
    width: 100%;
    max-height: 38vh;
    border-right: none;
    border-bottom: 1px solid var(--platform-border);
  }
}
</style>
