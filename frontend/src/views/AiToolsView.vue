<script setup>
import { computed } from "vue";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { NCard, NGrid, NGi, NText, NTag, NIcon } from "naive-ui";
import {
  ChatbubblesOutline,
  OpenOutline,
  ConstructOutline,
  ImagesOutline,
  ExtensionPuzzleOutline,
  GridOutline,
} from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { openExternal } from "../utils/openExternal.js";

const ui = usePlatformUi();
const { t } = useI18n();

/** @typedef {{ id: string, url?: string, pending?: boolean }} AiToolDef */
/** @typedef {{ id: string, icon: object, tools: AiToolDef[] }} AiToolCategoryDef */

/** @type {AiToolCategoryDef[]} */
const categoryDefs = [
  {
    id: "chat",
    icon: ChatbubblesOutline,
    tools: [
      { id: "doubao", url: "https://www.doubao.com/" },
      { id: "deepseek", url: "https://chat.deepseek.com/" },
      { id: "qwen", url: "https://tongyi.aliyun.com/" },
      { id: "kimi", url: "https://kimi.moonshot.cn/" },
      { id: "chatglm", url: "https://chatglm.cn/" },
      { id: "yiyan", url: "https://yiyan.baidu.com/" },
      { id: "yuanbao", url: "https://yuanbao.tencent.com/" },
      { id: "gemini", url: "https://gemini.google.com/" },
      { id: "chatgpt", url: "https://chatgpt.com/" },
      { id: "claude", url: "https://claude.ai/" },
    ],
  },
  {
    id: "agent",
    icon: ExtensionPuzzleOutline,
    tools: [
      { id: "openclaw", pending: true },
      { id: "hermes", pending: true },
      { id: "coze", url: "https://www.coze.cn/" },
      { id: "dify", url: "https://cloud.dify.ai/" },
    ],
  },
  {
    id: "media",
    icon: ImagesOutline,
    tools: [
      { id: "wanxiang", url: "https://tongyi.aliyun.com/wanxiang/" },
      { id: "jimeng", url: "https://jimeng.jianying.com/" },
      { id: "kling", url: "https://klingai.com/" },
      { id: "hailuo", url: "https://hailuoai.com/" },
      { id: "liblib", url: "https://www.liblib.art/" },
      { id: "designer", url: "https://designer.microsoft.com/image-creator" },
      { id: "ideogram", url: "https://ideogram.ai/" },
      { id: "leonardo", url: "https://leonardo.ai/" },
      { id: "pika", url: "https://pika.art/" },
    ],
  },
  {
    id: "misc",
    icon: GridOutline,
    tools: [
      { id: "figma", url: "https://www.figma.com/" },
      { id: "jsdesign", url: "https://js.design/" },
      { id: "modao", url: "https://modao.cc/" },
      { id: "canva", url: "https://www.canva.com/" },
      { id: "photopea", url: "https://www.photopea.com/" },
      { id: "removebg", url: "https://www.remove.bg/" },
      { id: "squoosh", url: "https://squoosh.app/" },
      { id: "convertio", url: "https://convertio.co/zh/" },
      { id: "fishaudio", url: "https://fish.audio/" },
      {
        id: "azure-tts",
        url: "https://azure.microsoft.com/zh-cn/products/ai-services/text-to-speech",
      },
      { id: "excalidraw", url: "https://excalidraw.com/" },
    ],
  },
];

const categories = computed(() =>
  categoryDefs.map((cat) => ({
    id: cat.id,
    title: t(`aiTools.categories.${cat.id}.title`),
    hint: t(`aiTools.categories.${cat.id}.hint`),
    icon: cat.icon,
    tools: cat.tools.map((tool) => ({
      ...tool,
      title: t(`aiTools.tools.${tool.id}.title`),
      description: t(`aiTools.tools.${tool.id}.description`),
    })),
  }))
);

/**
 * @param {{ pending?: boolean, url?: string }} tool
 */
function openTool(tool) {
  if (tool.pending) {
    ui.info(t("aiTools.pendingMessage"));
    return;
  }
  if (!tool.url) {
    ui.warning(t("aiTools.noUrl"));
    return;
  }
  openExternal(tool.url);
}
</script>

<template>
  <FeatureSubsystemShell>
    <section v-for="cat in categories" :key="cat.id" class="category-section">
      <div class="category-head">
        <n-icon :size="24" class="category-icon">
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
        <n-gi v-for="tool in cat.tools" :key="tool.id" span="1 m:2 l:1">
          <n-card
            size="small"
            class="feature-card"
            :class="{ disabled: tool.pending }"
            hoverable
            @click="openTool(tool)"
          >
            <div class="feature-row">
              <n-icon :size="26" class="feature-icon">
                <ConstructOutline v-if="tool.pending" />
                <component :is="cat.icon" v-else />
              </n-icon>
              <div class="feature-body">
                <n-text strong class="feature-title">{{ tool.title }}</n-text>
                <n-text depth="3" class="feature-desc">{{ tool.description }}</n-text>
              </div>
              <n-icon v-if="!tool.pending" :size="19" class="external-icon" depth="3">
                <OpenOutline />
              </n-icon>
            </div>
            <n-tag
              size="small"
              :bordered="false"
              :type="tool.pending ? 'default' : 'info'"
              class="feature-tag"
            >
              {{ tool.pending ? t("aiTools.tagPending") : t("aiTools.tagExternal") }}
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
  font-size: 16px;
}
.category-section {
  margin-top: 24px;
}
.category-section:first-of-type {
  margin-top: 14px;
}
.category-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
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
  font-size: 18px;
  line-height: 1.35;
}
.category-hint {
  display: block;
  font-size: var(--platform-font-size-base);
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
  gap: 12px;
}
.feature-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--n-text-color);
}
.external-icon {
  flex-shrink: 0;
  margin-top: 5px;
  opacity: 0.55;
}
.feature-body {
  min-width: 0;
  flex: 1;
}
.feature-title {
  display: block;
  font-size: 17px;
  line-height: 1.35;
}
.feature-desc {
  font-size: 11px;
  line-height: 1.4;
  margin-top: 5px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.feature-tag {
  margin-top: 10px;
}
</style>
