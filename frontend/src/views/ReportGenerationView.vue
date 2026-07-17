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
  <div class="knowledge-feature-panel accent-theme">
    <Teleport v-if="headerExtensionActive" to="#header-actions">
      <ChatSessionToolbarActions
        :disabled="historyLoading"
        @history="openHistory"
        @new-chat="startNewChat"
      />
    </Teleport>

    <AiChatPanel
      ref="chatPanelRef"
      v-model:conversation-id="conversationId"
      chat-scope="report-generation"
      class="report-gen-page__panel"
      session-actions-in-toolbar
      :streaming="true"
      :rich-markdown="true"
      :enable-attachments="true"
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

.report-gen-page__panel {
  flex: 1;
  min-height: 0;
  border-radius: 0 !important;
}

/* ── 报告生成页面：仅标题、图标使用蓝色 ── */
.report-gen-page__panel :deep(.ai-home-title.platform-text-gradient) {
  background-image: linear-gradient(135deg, #3b82ff 0%, #0a6bff 100%);
}
.report-gen-page__panel :deep(.ai-home-icon) {
  color: #0a6bff;
}
/* 思考呼吸气泡 + 智能体名称仍使用蓝色主题色 */
.report-gen-page__panel :deep(.ai-std__dot) {
  background: #0a6bff;
}
.report-gen-page__panel :deep(.agent-workflow__agent-tag) {
  color: #0a6bff;
  background: rgba(10, 107, 255, 0.1);
  border: 1px solid rgba(10, 107, 255, 0.18);
}
.report-gen-page__panel :deep(.agent-workflow__checkbox) {
  background: rgba(10, 107, 255, 0.12);
  color: #0a6bff;
}
</style>
