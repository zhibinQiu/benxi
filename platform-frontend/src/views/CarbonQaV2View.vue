<script setup>
import { ref } from "vue";
import { ChatbubblesOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { carbonQaChatStream } from "../api/client";

const conversationId = ref(null);

const suggestions = [
  "全国碳市场纳入行业有哪些？",
  "范围一、二、三排放如何划分？",
  "企业碳中和路径一般包含哪些阶段？",
  "CCER 与绿证在抵消中的区别是什么？",
];
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <AiChatPanel
      v-model:conversation-id="conversationId"
      :streaming="true"
      :rich-markdown="true"
      :show-workflow-progress="true"
      title="双碳问答"
      description="面向双碳政策、碳核算标准、碳市场与减排实践的智能问答，支持多轮追问与专业解读。"
      subtitle="双碳问答 · 知识解读"
      chat-header-sub="多轮对话 · 引用来源 · 图表与 Markdown"
      :show-citations="true"
      :suggestions="suggestions"
      :icon="ChatbubblesOutline"
      :stream-chat="carbonQaChatStream"
    />
  </FeatureSubsystemShell>
</template>
