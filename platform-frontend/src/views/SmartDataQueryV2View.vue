<script setup>
defineOptions({ name: "SmartDataQueryV2View" });
import { ref } from "vue";
import { StatsChartOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { smartDataQueryChatStream } from "../api/client";

const conversationId = ref(null);

const suggestions = [
  "发电企业 2025 年排放了多少碳？",
  "几家公司在2025年的碳排放量占比。",
];
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <AiChatPanel
      chat-scope="smart-data-query"
      v-model:conversation-id="conversationId"
      :streaming="true"
      :rich-markdown="true"
      :show-workflow-progress="true"
      title="智能问数"
      description="用自然语言查询业务数据，自动生成统计图表与分析洞察，支持多轮追问与深度解读。"
      subtitle="智能问数 · 自然语言分析"
      chat-header-sub="多轮对话 · 引用来源 · 图表与 Markdown"
      :show-citations="true"
      :suggestions="suggestions"
      :icon="StatsChartOutline"
      :stream-chat="smartDataQueryChatStream"
      title-gradient
      :show-chat-header-brand="false"
    />
  </FeatureSubsystemShell>
</template>
