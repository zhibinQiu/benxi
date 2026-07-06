<script setup>
defineOptions({ name: "SmartDataQueryV2View" });
import { computed, ref } from "vue";
import { StatsChartOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { smartDataQueryChatStream } from "../api/client";
import { useI18n } from "../composables/useI18n.js";

const { t, tm } = useI18n();
const conversationId = ref(null);
const suggestions = computed(() => tm("smartDataQuery.suggestions") || []);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <AiChatPanel
      chat-scope="smart-data-query"
      v-model:conversation-id="conversationId"
      :streaming="true"
      :rich-markdown="true"
      :show-workflow-progress="true"
      :title="t('smartDataQuery.title')"
      :description="t('smartDataQuery.description')"
      :subtitle="t('smartDataQuery.subtitle')"
      :chat-header-sub="t('smartDataQuery.chatHeaderSub')"
      :show-citations="true"
      :suggestions="suggestions"
      :icon="StatsChartOutline"
      :stream-chat="smartDataQueryChatStream"
      title-gradient
      :show-chat-header-brand="false"
    />
  </FeatureSubsystemShell>
</template>
