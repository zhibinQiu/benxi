<script setup>
defineOptions({ name: "CarbonQaV2View" });
import { computed, ref } from "vue";
import { ChatbubblesOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { carbonQaChatStream } from "../api/client";
import { useI18n } from "../composables/useI18n.js";

const { t, tm } = useI18n();
const conversationId = ref(null);
const suggestions = computed(() => tm("carbonQa.suggestions") || []);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <AiChatPanel
      chat-scope="carbon-qa"
      v-model:conversation-id="conversationId"
      :streaming="true"
      :rich-markdown="true"
      :show-workflow-progress="true"
      :title="t('carbonQa.title')"
      :description="t('carbonQa.description')"
      :subtitle="t('carbonQa.subtitle')"
      :chat-header-sub="t('carbonQa.chatHeaderSub')"
      :show-citations="true"
      :suggestions="suggestions"
      :icon="ChatbubblesOutline"
      :stream-chat="carbonQaChatStream"
      title-gradient
      :show-chat-header-brand="false"
    />
  </FeatureSubsystemShell>
</template>
