<script setup>
defineOptions({ name: "AiHomeView" });
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import {
  SparklesOutline,
} from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import { aiHomeChatStream } from "../api/client";
import { useI18n } from "../composables/useI18n.js";
import { useChatTabs } from "../composables/useChatTabs.js";

const route = useRoute();
const { t, tm } = useI18n();

const {
  getSessionKey,
  setTabStreaming,
  setTabHasContent,
  updateTabTitle,
} = useChatTabs();

/**
 * 当前标签页 id：默认 tab-0（/ai-home），多标签从路由参数取。
 * 在 setup 阶段捕获，避免 KeepAlive deactivated 时 useRoute() 跟踪
 * 当前路由导致 tabId/sessionKey 跟随切换而变化。
 */
const tabId = ref(route.params.tabId || "tab-0");

/** 当前标签页的 sessionStorage 持久化 key */
const sessionKey = computed(() => getSessionKey(tabId.value));

/** 对话状态变更时同步到 useChatTabs */
function onChatStateChange({ streaming, hasContent, title }) {
  setTabStreaming(tabId.value, Boolean(streaming));
  setTabHasContent(tabId.value, Boolean(hasContent));
  updateTabTitle(tabId.value, title || "");
}

const suggestions = computed(() => tm("aiHome.suggestions") || []);
</script>

<template>
  <div class="knowledge-feature-panel accent-theme">
    <AiChatPanel
      :key="sessionKey"
      chat-scope="ai-home"
      :session-key="sessionKey"
      :on-chat-state-change="onChatStateChange"
      class="ai-home-page__panel"
      :title="t('aiHome.title')"
      :description="t('aiHome.description')"
      :architecture="tm('aiHome.architecture')"
      :chat-header-sub="t('aiHome.chatHeaderSub')"
      :suggestions="suggestions"
      :icon="SparklesOutline"
      :stream-chat="aiHomeChatStream"
      :rich-markdown="true"
      :show-citations="false"
      :show-workflow-progress="true"
      :linkify-citations="false"
      :enable-attachments="true"
      :enable-agent-skills="true"
      :show-chat-header-brand="false"
      :animated-hero-icon="true"
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

/* ── 本析智能页面：通过 accent-theme CSS 变量实现蓝色主题 ── */
.ai-home-page__panel :deep(.aw-c__agent-tag) {
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
  border: 1px solid var(--platform-accent-border-soft);
}
.ai-home-page__panel :deep(.aw-c__icon) {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
}
.ai-home-page__panel :deep(.aw-c__icon--pulse) {
  background: var(--platform-accent-soft-2);
  box-shadow: 0 0 0 0 rgba(77, 148, 255, 0.2);
}
</style>
