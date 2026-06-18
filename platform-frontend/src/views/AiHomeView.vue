<script setup>
defineOptions({ name: "AiHomeView" });
import { computed } from "vue";
import { useRoute } from "vue-router";
import {
  CreateOutline,
  GitNetworkOutline,
  SearchOutline,
  SparklesOutline,
} from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import { aiHomeChatStream } from "../api/client";
import { useI18n } from "../composables/useI18n.js";
import { encodeReturnLocation } from "../utils/navigationReturn";

const route = useRoute();
const { t, tm } = useI18n();

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
</script>

<template>
  <AiChatPanel
    chat-scope="ai-home"
    :title="t('aiHome.title')"
    :description="t('aiHome.description')"
    :subtitle="t('aiHome.subtitle')"
    :chat-header-sub="t('aiHome.chatHeaderSub')"
    :suggestions="suggestions"
    :tool-links="toolLinks"
    :icon="SparklesOutline"
    :stream-chat="aiHomeChatStream"
    :show-citations="true"
    :show-workflow-progress="true"
    :linkify-citations="true"
    :enable-attachments="true"
    title-gradient
    :show-chat-header-brand="false"
  />
</template>
