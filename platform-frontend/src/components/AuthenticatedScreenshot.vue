<script setup>
import { onBeforeUnmount, ref, watch } from "vue";
import {
  fetchAuthenticatedImageBlob,
  normalizeChatAttachmentUrl,
  revokeObjectUrlIfBlob,
} from "../utils/authenticatedImage.js";

const props = defineProps({
  url: { type: String, required: true },
  title: { type: String, default: "浏览器截图" },
});

const objectUrl = ref("");
const failed = ref(false);
let abortController = null;

async function loadScreenshot() {
  const src = normalizeChatAttachmentUrl(props.url);
  if (!src) {
    failed.value = true;
    return;
  }
  abortController?.abort();
  abortController = new AbortController();
  failed.value = false;
  revokeObjectUrlIfBlob(objectUrl.value);
  objectUrl.value = "";
  try {
    const blob = await fetchAuthenticatedImageBlob(src, { signal: abortController.signal });
    if (abortController.signal.aborted) return;
    objectUrl.value = URL.createObjectURL(blob);
  } catch {
    if (!abortController.signal.aborted) failed.value = true;
  }
}

watch(
  () => props.url,
  () => {
    void loadScreenshot();
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  abortController?.abort();
  revokeObjectUrlIfBlob(objectUrl.value);
});
</script>

<template>
  <figure class="auth-screenshot">
    <img
      v-if="objectUrl"
      :src="objectUrl"
      :alt="title"
      loading="lazy"
      draggable="false"
    />
    <div v-else-if="failed" class="auth-screenshot__placeholder auth-screenshot__placeholder--error">
      {{ title }}加载失败
    </div>
    <div v-else class="auth-screenshot__placeholder">
      {{ title }}加载中…
    </div>
  </figure>
</template>

<style scoped>
.auth-screenshot {
  margin: 8px 0;
}

.auth-screenshot img {
  display: block;
  max-width: 100%;
  width: auto;
  height: auto;
  max-height: min(320px, 48vh);
  object-fit: contain;
  border-radius: 8px;
  cursor: zoom-in;
}

.auth-screenshot__placeholder {
  padding: 24px 16px;
  border-radius: 8px;
  text-align: center;
  font-size: 13px;
  color: var(--platform-text-secondary, #64748b);
  background: color-mix(in srgb, var(--platform-bg, #fff) 90%, #94a3b8 10%);
  border: 1px dashed color-mix(in srgb, var(--platform-border, #e2e8f0) 80%, transparent);
}

.auth-screenshot__placeholder--error {
  color: #b91c1c;
  border-color: color-mix(in srgb, #ef4444 35%, var(--platform-border, #e2e8f0));
}
</style>
