<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import {
  bindEchartsResize,
  disposeEchartsInElement,
  mountRichMediaInElement,
  renderRichMarkdown,
  unbindEchartsResize } from "../utils/richMarkdown";
import { unmountMermaidInElement } from "../utils/mermaidRender.js";
import {
  authImageUrlFingerprint,
  hydrateAuthenticatedImagesInElement,
  isAuthenticatedApiImageUrl,
  normalizeAuthImageSrc,
  revokeAuthenticatedImagesInElement,
} from "../utils/authenticatedImage.js";
import { useRichMediaViewer } from "../composables/useRichMediaViewer.js";
import RichMediaViewerModal from "./RichMediaViewerModal.vue";

const props = defineProps({
  content: { type: String, default: "" }});

const rootRef = ref(null);
/** KeepAlive 失活时不渲染 v-html，避免大量 DOM 常驻内存 */
const domActive = ref(true);
const html = computed(() => (domActive.value ? renderRichMarkdown(props.content) : ""));
const imageFingerprint = computed(() => authImageUrlFingerprint(props.content));

const {
  viewerOpen,
  viewerPayload,
  bindRichMediaViewerOnRoot,
  unbindRichMediaViewerOnRoot,
} = useRichMediaViewer();

let refreshChartsTimer = null;
let refreshGeneration = 0;
let lastHydratedFingerprint = "";

function authImagesHydrated(root) {
  if (!root) return false;
  const imgs = [...root.querySelectorAll("img[src]")].filter((img) => {
    const src = normalizeAuthImageSrc(img.getAttribute("src") || "");
    return src && isAuthenticatedApiImageUrl(src);
  });
  if (!imgs.length) return false;
  return imgs.every((img) => img.dataset.authHydrated === "1" && img.src.startsWith("blob:"));
}

async function refreshCharts({ force = false } = {}) {
  if (!domActive.value) return;
  const fp = imageFingerprint.value;
  const root = rootRef.value;
  if (!force && fp && fp === lastHydratedFingerprint && authImagesHydrated(root)) {
    return;
  }
  const gen = ++refreshGeneration;
  if (root) {
    unbindRichMediaViewerOnRoot(root);
    revokeAuthenticatedImagesInElement(root);
  }
  await nextTick();
  if (gen !== refreshGeneration || !rootRef.value) return;
  disposeEchartsInElement(rootRef.value);
  unmountMermaidInElement(rootRef.value);
  await mountRichMediaInElement(rootRef.value);
  if (gen !== refreshGeneration || !rootRef.value) return;
  await hydrateAuthenticatedImagesInElement(rootRef.value);
  if (gen !== refreshGeneration || !rootRef.value) return;
  bindRichMediaViewerOnRoot(rootRef.value);
  lastHydratedFingerprint = fp;
}

function scheduleRefreshCharts() {
  if (refreshChartsTimer) clearTimeout(refreshChartsTimer);
  refreshChartsTimer = setTimeout(() => {
    refreshChartsTimer = null;
    void refreshCharts();
  }, 280);
}

function releaseDom() {
  const root = rootRef.value;
  if (root) {
    unbindRichMediaViewerOnRoot(root);
    revokeAuthenticatedImagesInElement(root);
    disposeEchartsInElement(root);
    unmountMermaidInElement(root);
  }
  domActive.value = false;
}

watch(imageFingerprint, scheduleRefreshCharts);
watch(() => props.content, scheduleRefreshCharts);

onMounted(() => {
  bindEchartsResize();
  refreshCharts({ force: true });
});

onActivated(() => {
  domActive.value = true;
  refreshCharts();
});

onDeactivated(releaseDom);

onBeforeUnmount(() => {
  refreshGeneration += 1;
  lastHydratedFingerprint = "";
  if (refreshChartsTimer) {
    clearTimeout(refreshChartsTimer);
    refreshChartsTimer = null;
  }
  releaseDom();
  unbindEchartsResize();
});
</script>

<template>
  <div ref="rootRef" class="md-rich" v-html="html" />
  <RichMediaViewerModal v-model:show="viewerOpen" :payload="viewerPayload" />
</template>

<style scoped>
.md-rich :deep(p) {
  margin: 0 0 0.5em;
}

.md-rich :deep(p:last-child) {
  margin-bottom: 0;
}

.md-rich :deep(ul),
.md-rich :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.25em;
}

.md-rich :deep(code) {
  font-size: 0.9em;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.06);
}

.md-rich :deep(pre) {
  margin: 0.5em 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.05);
  overflow-x: auto;
}

.md-rich :deep(pre code) {
  padding: 0;
  background: transparent;
}

.md-rich :deep(.md-echart-wrap) {
  margin: 12px 0;
  width: 100%;
}

.md-rich :deep(.md-echart-error) {
  margin: 0;
  padding: 8px;
  font-size: 12px;
  color: #b91c1c;
}
</style>
