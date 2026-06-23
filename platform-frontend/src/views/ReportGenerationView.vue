<script setup>
defineOptions({ name: "ReportGenerationView" });
import { computed, inject, onMounted, ref } from "vue";
import { CreateOutline } from "@vicons/ionicons5";
import { NCheckbox } from "naive-ui";
import AiChatPanel from "../components/AiChatPanel.vue";
import HintTooltip from "../components/HintTooltip.vue";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import {
  downloadReportDocx,
  fetchReportGenerationMeta,
  fetchReportMindmap,
  fetchReportOptimizePresets,
  importReportToLibrary,
  reportGenerationChatStream,
} from "../api/reportGeneration.js";
import { useI18n } from "../composables/useI18n.js";
import { KNOWLEDGE_SCOPE_SELECTION_KEY, readKnowledgeScopeSelection } from "../utils/knowledgeScopeSelectionCache.js";

const { t, tm } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();

const selection = inject(
  KNOWLEDGE_SCOPE_SELECTION_KEY,
  ref(readKnowledgeScopeSelection())
);
const conversationId = ref(null);
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
  <div class="knowledge-feature-panel">
    <Teleport v-if="headerExtensionActive" to="#page-header-extension">
    <div class="subsystem-extra-bar">
      <div class="subsystem-extra-row">
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
      </div>
    </div>
  </Teleport>

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
    :report-library-import="importReportToLibrary"
    :report-optimize-presets="optimizePresets"
    :composer-input-while-loading="true"
    title-gradient
    :show-chat-header-brand="false"
  />
  </div>
</template>

<style scoped>
.knowledge-feature-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

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

.report-gen-page__panel {
  flex: 1;
  min-height: 0;
  border-radius: 0 !important;
}
</style>
