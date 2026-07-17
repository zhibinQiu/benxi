<script setup>
import { computed } from "vue";
import {
  collectScreenshotAttachmentCandidates,
  stripAuthScreenshotMarkdown,
} from "../utils/authenticatedImage.js";
import AuthenticatedScreenshot from "./AuthenticatedScreenshot.vue";
import ChatMarkdownBody from "./ChatMarkdownBody.vue";
import MarkdownRichContent from "./MarkdownRichContent.vue";

const props = defineProps({
  content: { type: String, default: "" },
  richMarkdown: { type: Boolean, default: false },
  browserScreenshots: { type: Array, default: () => [] },
  /** gallery-only：仅展示截图区，正文由父级其它组件渲染 */
  textMode: { type: String, default: "full" },
});

const shots = computed(() => {
  const fromProps = (props.browserScreenshots || []).map((shot) => ({
    type: "image",
    url: shot.url,
    title: shot.title,
  }));
  return collectScreenshotAttachmentCandidates(props.content || "", fromProps);
});

const markdownContent = computed(() =>
  stripAuthScreenshotMarkdown(props.content || "", shots.value)
);

const showScreenshotGallery = computed(() => shots.value.length > 0);
</script>

<template>
  <div class="assistant-conclusion">
    <template v-if="textMode !== 'gallery-only'">
      <MarkdownRichContent
        v-if="richMarkdown && markdownContent"
        :content="markdownContent"
      />
      <ChatMarkdownBody v-else-if="markdownContent" :content="markdownContent" />
    </template>
    <div v-if="showScreenshotGallery" class="assistant-conclusion__screenshots">
      <div v-if="markdownContent || shots.length" class="assistant-conclusion__screenshot-label">
        页面截图
      </div>
      <AuthenticatedScreenshot
        v-for="(shot, idx) in shots"
        :key="`${shot.url}-${idx}`"
        :url="shot.url"
        :title="shot.title"
      />
    </div>
  </div>
</template>

<style scoped>
.assistant-conclusion__screenshots {
  margin-top: 14px;
}

.assistant-conclusion__screenshot-label {
  margin-bottom: 10px;
  font-size: 14px;
  color: var(--platform-text, #1e293b);
}
</style>
