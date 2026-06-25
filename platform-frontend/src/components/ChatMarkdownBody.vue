<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { renderMarkdown } from "../utils/markdown.js";
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
  content: { type: String, default: "" },
});

const rootRef = ref(null);
const html = computed(() => renderMarkdown(props.content || ""));
const imageFingerprint = computed(() => authImageUrlFingerprint(props.content));

const {
  viewerOpen,
  viewerPayload,
  bindRichMediaViewerOnRoot,
  unbindRichMediaViewerOnRoot,
} = useRichMediaViewer();

let refreshTimer = null;
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

async function refreshImages({ force = false } = {}) {
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
  await hydrateAuthenticatedImagesInElement(rootRef.value);
  if (gen !== refreshGeneration || !rootRef.value) return;
  bindRichMediaViewerOnRoot(rootRef.value);
  lastHydratedFingerprint = fp;
}

function scheduleRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    void refreshImages();
  }, 280);
}

watch(imageFingerprint, scheduleRefresh);
watch(() => props.content, scheduleRefresh);

onMounted(() => {
  void refreshImages({ force: true });
});

onBeforeUnmount(() => {
  refreshGeneration += 1;
  lastHydratedFingerprint = "";
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  unbindRichMediaViewerOnRoot(rootRef.value);
  revokeAuthenticatedImagesInElement(rootRef.value);
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
</style>
