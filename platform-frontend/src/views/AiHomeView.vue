<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import {
  ChatbubblesOutline,
  LeafOutline,
  SearchOutline,
  StatsChartOutline,
} from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import { aiHomeChatStream } from "../api/client";
import { encodeReturnLocation } from "../utils/navigationReturn";

const route = useRoute();

const suggestions = [
  "请介绍企业碳盘查的一般流程",
  "范围一、二、三温室气体排放如何划分？",
  "制造业常见的减排路径有哪些？",
];

const toolLinks = computed(() => {
  const encoded = encodeReturnLocation(route);
  const returnQuery = encoded ? { return: encoded } : {};
  return [
    { title: "双碳问答", route: { name: "carbon-qa", query: returnQuery }, icon: ChatbubblesOutline },
    {
      title: "智能问数",
      route: { name: "smart-data-query", query: returnQuery },
      icon: StatsChartOutline,
    },
    {
      title: "知识搜索",
      route: { name: "knowledge-search", query: returnQuery },
      icon: SearchOutline,
    },
  ];
});
</script>

<template>
  <AiChatPanel
    chat-scope="ai-home"
    title="双碳智能体"
    description="面向企业碳管理、碳核算与减排路径的专业 AI 助手，助您快速理解政策标准、梳理减排思路与 ESG 实践。"
    subtitle="内置大模型对话"
    :suggestions="suggestions"
    :tool-links="toolLinks"
    :icon="LeafOutline"
    :stream-chat="aiHomeChatStream"
  />
</template>
