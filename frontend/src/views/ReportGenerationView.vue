<script setup>
defineOptions({ name: "ReportGenerationView" });
import { computed, inject, onActivated, onMounted, ref } from "vue";
import { AddOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import ChatSessionToolbarActions from "../components/ChatSessionToolbarActions.vue";
import { isRouteAbortError } from "../api/client";
import {
  downloadReportDocx,
  fetchReportAgentSkills,
  fetchReportGenerationMeta,
  fetchReportMindmap,
  fetchReportOptimizePresets,
  importReportToLibrary,
  reportGenerationChatStream,
} from "../api/reportGeneration.js";
import { useI18n } from "../composables/useI18n.js";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { KNOWLEDGE_SCOPE_SELECTION_KEY, readKnowledgeScopeSelection } from "../utils/knowledgeScopeSelectionCache.js";

const { t } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();

const selection = inject(
  KNOWLEDGE_SCOPE_SELECTION_KEY,
  ref(readKnowledgeScopeSelection())
);
const chatPanelRef = ref(null);
const conversationId = ref(null);
const optimizePresets = ref([]);
const reportAgentSkills = ref([]);
const reportSkillsLoading = ref(false);
const webSearchAvailable = ref(true);

const selectionHint = computed(() => {
  const sel = selection.value;
  const total = sel?.totalSelected || sel?.documentIds?.length || 0;
  const ready = sel?.indexReadyCount ?? total;
  const parts = [];
  if (total) {
    if (ready < total) {
      parts.push(t("reportGeneration.selectedDocsIndexPendingHint", { total, ready }));
    } else {
      parts.push(t("reportGeneration.selectedDocsHint", { count: total }));
    }
  } else {
    parts.push(t("reportGeneration.noLocalDocsHint"));
  }
  if (!webSearchAvailable.value) {
    parts.push(t("reportGeneration.webSearchUnavailableHint"));
  }
  return parts.join(" · ");
});

const historyLoading = computed(() => Boolean(chatPanelRef.value?.loadingHistory));

function openHistory() {
  chatPanelRef.value?.goToHistory?.();
}

function startNewChat() {
  chatPanelRef.value?.newChat?.();
}

async function handleChatStream(params, callbacks) {
  return reportGenerationChatStream(
    {
      ...params,
      documentIds: selection.value?.documentIds || [],
    },
    callbacks
  );
}

async function loadReportPageData() {
  reportSkillsLoading.value = true;
  try {
    try {
      const meta = await fetchReportGenerationMeta();
      webSearchAvailable.value = Boolean(meta?.web_search_enabled);
    } catch (e) {
      if (!isRouteAbortError(e)) webSearchAvailable.value = true;
    }
    try {
      optimizePresets.value = (await fetchReportOptimizePresets()) || [];
    } catch (e) {
      if (!isRouteAbortError(e)) optimizePresets.value = [];
    }
    try {
      reportAgentSkills.value = (await fetchReportAgentSkills()) || [];
    } catch (e) {
      if (!isRouteAbortError(e)) reportAgentSkills.value = [];
    }
  } finally {
    reportSkillsLoading.value = false;
  }
}

onMounted(loadReportPageData);
onActivated(() => {
  if (!reportAgentSkills.value.length && !reportSkillsLoading.value) {
    void loadReportPageData();
  }
});
</script>

<template>
  <div class="knowledge-feature-panel">
    <Teleport v-if="headerExtensionActive" to="#page-header-extension">
      <div class="subsystem-extra-bar">
        <div class="subsystem-extra-row">
          <div class="report-gen-toolbar">
            <span class="report-gen-toolbar-hint">{{ selectionHint }}</span>
            <ChatSessionToolbarActions
              :disabled="historyLoading"
              @history="openHistory"
              @new-chat="startNewChat"
            />
          </div>
        </div>
      </div>
    </Teleport>

    <AiChatPanel
      ref="chatPanelRef"
      v-model:conversation-id="conversationId"
      chat-scope="report-generation"
      class="report-gen-page__panel"
      session-actions-in-toolbar
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
      :suggestions="[]"
      :icon="AddOutline"
      :stream-chat="handleChatStream"
      :show-report-tools="true"
      :report-mindmap-fetch="fetchReportMindmap"
      :report-word-export="downloadReportDocx"
      :report-library-import="importReportToLibrary"
      :report-optimize-presets="optimizePresets"
      :report-agent-skills="reportAgentSkills"
      :report-agent-skills-loading="reportSkillsLoading"
      title-gradient
      :show-chat-header-brand="false"
      :show-disclaimer="false"
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
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
  min-width: 0;
}

.report-gen-toolbar-hint {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-gen-page__panel {
  flex: 1;
  min-height: 0;
  border-radius: 0 !important;
}
</style>
