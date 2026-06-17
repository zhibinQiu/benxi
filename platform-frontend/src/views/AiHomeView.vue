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
import { encodeReturnLocation } from "../utils/navigationReturn";

const route = useRoute();

const suggestions = [
  "如何上传文档并设置分享权限？",
  "PDF 翻译任务提交后在哪里查看进度？",
  "全国碳市场管理办法约束哪些指标？",
  "张三负责哪些减排项目？",
];

const toolLinks = computed(() => {
  const encoded = encodeReturnLocation(route);
  const returnQuery = encoded ? { return: encoded } : {};
  return [
    {
      title: "知识检索",
      route: { name: "knowledge-search", query: returnQuery },
      icon: SearchOutline,
    },
    {
      title: "报告生成",
      route: { name: "report-generation", query: returnQuery },
      icon: CreateOutline,
    },
    {
      title: "本体图谱",
      route: { name: "kg-palantir", query: returnQuery },
      icon: GitNetworkOutline,
    },
  ];
});
</script>

<template>
  <AiChatPanel
    chat-scope="ai-home"
    title="AI 智能体"
    description="企业级智能对话入口，结合权限内文档检索、本体图谱关联与多轮问答。"
    subtitle="内置大模型 · 文档检索 + 本体图谱增强"
    :suggestions="suggestions"
    :tool-links="toolLinks"
    :icon="SparklesOutline"
    :stream-chat="aiHomeChatStream"
    :show-citations="true"
    :linkify-citations="true"
    title-gradient
    :show-chat-header-brand="false"
  />
</template>
