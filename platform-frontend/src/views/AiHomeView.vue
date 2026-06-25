<script setup>
defineOptions({ name: "AiHomeView" });
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import {
  CreateOutline,
  GitNetworkOutline,
  SearchOutline,
  SparklesOutline,
} from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import ChatSessionToolbarActions from "../components/ChatSessionToolbarActions.vue";
import { aiHomeChatStream } from "../api/client";
import { useI18n } from "../composables/useI18n.js";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { encodeReturnLocation } from "../utils/navigationReturn";

const route = useRoute();
const { t, tm } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();

const chatPanelRef = ref(null);

const suggestions = computed(() => tm("aiHome.suggestions") || []);

const toolLinks = computed(() => {
  const encoded = encodeReturnLocation(route);
  const returnQuery = encoded ? { return: encoded } : {};
  return [
    {
      title: t("aiHome.toolLinks.knowledgeSearch"),
      route: { name: "knowledge-search", query: returnQuery },
      icon: SearchOutline,
    },
    {
      title: t("aiHome.toolLinks.reportGeneration"),
      route: { name: "report-generation", query: returnQuery },
      icon: CreateOutline,
    },
    {
      title: t("aiHome.toolLinks.kgPalantir"),
      route: { name: "kg-palantir", query: returnQuery },
      icon: GitNetworkOutline,
    },
  ];
});

const historyLoading = computed(() => Boolean(chatPanelRef.value?.loadingHistory));

function openHistory() {
  chatPanelRef.value?.goToHistory?.();
}

function startNewChat() {
  chatPanelRef.value?.newChat?.();
}
</script>

<template>
  <div class="knowledge-feature-panel">
    <Teleport v-if="headerExtensionActive" to="#page-header-extension">
      <div class="subsystem-extra-bar">
        <div class="subsystem-extra-row">
          <div class="chat-session-toolbar">
            <span class="chat-session-toolbar__hint">{{ t("aiHome.chatHeaderSub") }}</span>
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
      chat-scope="ai-home"
      class="ai-home-page__panel"
      :title="t('aiHome.title')"
      :description="t('aiHome.description')"
      :chat-header-sub="t('aiHome.chatHeaderSub')"
      :suggestions="suggestions"
      :tool-links="toolLinks"
      :icon="SparklesOutline"
      :stream-chat="aiHomeChatStream"
      :rich-markdown="true"
      :show-citations="false"
      :show-workflow-progress="true"
      :linkify-citations="false"
      :enable-attachments="true"
      :enable-agent-skills="true"
      title-gradient
      :show-chat-header-brand="false"
      session-actions-in-toolbar
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

.ai-home-page__panel {
  flex: 1;
  min-height: 0;
  border-radius: 0 !important;
}

.chat-session-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.chat-session-toolbar__hint {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
