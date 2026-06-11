<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { NCard, NGrid, NGi, NText, NTag, NIcon } from "naive-ui";
import {
  ChatbubblesOutline,
  OpenOutline,
  ConstructOutline,
  ImagesOutline,
  ExtensionPuzzleOutline,
  GridOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";

const ui = usePlatformUi();

/** @typedef {{ id: string, title: string, description: string, url?: string, pending?: boolean }} AiTool */
/** @typedef {{ id: string, title: string, hint?: string, icon: object, tools: AiTool[] }} AiToolCategory */

/** @type {AiToolCategory[]} */
const categories = [
  {
    id: "chat",
    title: "AI 对话类",
    hint: "大模型对话与写作助手",
    icon: ChatbubblesOutline,
    tools: [
      { id: "doubao", title: "豆包", description: "字节跳动 AI 对话助手", url: "https://www.doubao.com/" },
      { id: "deepseek", title: "DeepSeek", description: "深度求索大模型对话", url: "https://chat.deepseek.com/" },
      { id: "qwen", title: "通义千问", description: "阿里云大模型助手", url: "https://tongyi.aliyun.com/" },
      { id: "kimi", title: "Kimi", description: "月之暗面长文本对话", url: "https://kimi.moonshot.cn/" },
      { id: "chatglm", title: "智谱清言", description: "智谱 AI 对话助手", url: "https://chatglm.cn/" },
      { id: "yiyan", title: "文心一言", description: "百度大模型对话", url: "https://yiyan.baidu.com/" },
      { id: "yuanbao", title: "腾讯元宝", description: "腾讯混元对话助手", url: "https://yuanbao.tencent.com/" },
      { id: "gemini", title: "Gemini", description: "Google AI 助手", url: "https://gemini.google.com/" },
      { id: "chatgpt", title: "ChatGPT", description: "OpenAI 对话（含免费额度）", url: "https://chatgpt.com/" },
      { id: "claude", title: "Claude", description: "Anthropic 对话（含免费额度）", url: "https://claude.ai/" },
    ]},
  {
    id: "agent",
    title: "Agent",
    hint: "智能体与自动化工作流",
    icon: ExtensionPuzzleOutline,
    tools: [
      { id: "openclaw", title: "OpenClaw", description: "平台集成的 OpenClaw 智能体", pending: true },
      { id: "hermes", title: "Hermes", description: "平台集成的 Hermes 智能体", pending: true },
      { id: "coze", title: "扣子 Coze", description: "字节跳动 Agent 搭建与对话", url: "https://www.coze.cn/" },
      {
        id: "dify",
        title: "Dify",
        description: "LLM 应用与 Agent 平台（设计系统）",
        url: "http://172.19.134.45:40001/apps"},
    ]},
  {
    id: "media",
    title: "生图 / 视频类",
    hint: "文生图、图生视频等创作工具（多数含免费额度）",
    icon: ImagesOutline,
    tools: [
      { id: "wanxiang", title: "通义万相", description: "阿里云文生图创作", url: "https://tongyi.aliyun.com/wanxiang/" },
      { id: "jimeng", title: "即梦 AI", description: "字节跳动图片与视频生成", url: "https://jimeng.jianying.com/" },
      { id: "kling", title: "可灵 AI", description: "快手文生视频与图像", url: "https://klingai.com/" },
      { id: "hailuo", title: "海螺 AI", description: "MiniMax 视频与语音生成", url: "https://hailuoai.com/" },
      { id: "liblib", title: "LiblibAI", description: "国内 AI 绘图模型社区", url: "https://www.liblib.art/" },
      { id: "designer", title: "Designer 图像创建", description: "微软免费 AI 生图", url: "https://designer.microsoft.com/image-creator" },
      { id: "ideogram", title: "Ideogram", description: "英文提示词友好生图", url: "https://ideogram.ai/" },
      { id: "leonardo", title: "Leonardo.Ai", description: "游戏与概念美术生图", url: "https://leonardo.ai/" },
      { id: "pika", title: "Pika", description: "短视频 AI 生成", url: "https://pika.art/" },
    ]},
  {
    id: "misc",
    title: "其他工具",
    hint: "原型设计、图像处理、格式转换、语音合成等",
    icon: GridOutline,
    tools: [
      { id: "figma", title: "Figma", description: "界面原型与协作设计", url: "https://www.figma.com/" },
      { id: "jsdesign", title: "即时设计", description: "国产 UI 原型与设计", url: "https://js.design/" },
      { id: "modao", title: "墨刀", description: "产品原型与交互稿", url: "https://modao.cc/" },
      { id: "canva", title: "Canva", description: "在线海报与视觉设计", url: "https://www.canva.com/" },
      { id: "photopea", title: "Photopea", description: "免费在线 PS 级图像编辑", url: "https://www.photopea.com/" },
      { id: "removebg", title: "Remove.bg", description: "一键 AI 抠图去背景", url: "https://www.remove.bg/" },
      { id: "squoosh", title: "Squoosh", description: "Google 图片压缩与格式转换", url: "https://squoosh.app/" },
      { id: "convertio", title: "Convertio", description: "多格式文件在线转换", url: "https://convertio.co/zh/" },
      { id: "fishaudio", title: "Fish Audio", description: "AI 语音合成与克隆", url: "https://fish.audio/" },
      { id: "azure-tts", title: "Azure 语音试听", description: "微软神经网络语音合成演示", url: "https://azure.microsoft.com/zh-cn/products/ai-services/text-to-speech" },
      { id: "excalidraw", title: "Excalidraw", description: "手绘风格白板与示意图", url: "https://excalidraw.com/" },
    ]},
];

/**
 * @param {AiTool} tool
 */
function openTool(tool) {
  if (tool.pending) {
    ui.info("该工具待开发，敬请期待");
    return;
  }
  if (!tool.url) {
    ui.warning("暂未配置访问地址");
    return;
  }
  window.open(tool.url, "_blank", "noopener,noreferrer");
}
</script>

<template>
  <FeatureSubsystemShell>
    <section
      v-for="cat in categories"
      :key="cat.id"
      class="category-section"
    >
      <div class="category-head">
        <n-icon :size="20" class="category-icon">
          <component :is="cat.icon" />
        </n-icon>
        <div class="category-titles">
          <n-text strong class="category-title">{{ cat.title }}</n-text>
          <n-text v-if="cat.hint" depth="3" class="category-hint">{{ cat.hint }}</n-text>
        </div>
      </div>

      <n-grid
        cols="1 m:4 l:8"
        :x-gap="12"
        :y-gap="12"
        responsive="screen"
        item-responsive
        class="category-grid"
      >
        <n-gi v-for="t in cat.tools" :key="t.id" span="1 m:2 l:1">
          <n-card
            size="small"
            class="feature-card"
            :class="{ disabled: t.pending }"
            hoverable
            @click="openTool(t)"
          >
            <div class="feature-row">
              <n-icon :size="22" class="feature-icon">
                <ConstructOutline v-if="t.pending" />
                <component :is="cat.icon" v-else />
              </n-icon>
              <div class="feature-body">
                <n-text strong class="feature-title">{{ t.title }}</n-text>
                <n-text depth="3" class="feature-desc">{{ t.description }}</n-text>
              </div>
              <n-icon v-if="!t.pending" :size="16" class="external-icon" depth="3">
                <OpenOutline />
              </n-icon>
            </div>
            <n-tag
              size="small"
              :bordered="false"
              :type="t.pending ? 'default' : 'info'"
              class="feature-tag"
            >
              {{ t.pending ? "待开发" : "外链" }}
            </n-tag>
          </n-card>
        </n-gi>
      </n-grid>
    </section>
  </FeatureSubsystemShell>
</template>

<style scoped>
.functions-page {
  width: 100%;
}
.page-hint {
  display: block;
  font-size: 13px;
}
.category-section {
  margin-top: 20px;
}
.category-section:first-of-type {
  margin-top: 12px;
}
.category-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}
.category-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--n-text-color);
}
.category-titles {
  min-width: 0;
}
.category-title {
  display: block;
  font-size: 15px;
  line-height: 1.35;
}
.category-hint {
  display: block;
  font-size: 12px;
  margin-top: 2px;
}
.category-grid {
  margin-top: 0;
}
.feature-card {
  cursor: pointer;
}
.feature-card.disabled {
  cursor: not-allowed;
  opacity: 0.65;
}
.feature-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.feature-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--n-text-color);
}
.external-icon {
  flex-shrink: 0;
  margin-top: 4px;
  opacity: 0.55;
}
.feature-body {
  min-width: 0;
  flex: 1;
}
.feature-title {
  display: block;
  font-size: 14px;
  line-height: 1.35;
}
.feature-desc {
  font-size: 12px;
  line-height: 1.4;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.feature-tag {
  margin-top: 8px;
}
</style>
