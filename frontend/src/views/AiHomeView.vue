<script setup>
defineOptions({ name: "AiHomeView" });
import { computed, onMounted, ref } from "vue";
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
 * 使用 ref + onMounted 捕获，避免 KeepAlive deactivated 时 useRoute() 跟踪
 * 当前路由导致 tabId/sessionKey 跟随切换而变化，触发 AiChatPanel 的 :key
 * 变更而销毁重建、中止后台流式请求。
 */
const tabId = ref("tab-0");
onMounted(() => {
  tabId.value = route.params.tabId || "tab-0";
});

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
  <div class="knowledge-feature-panel">
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
</style>
