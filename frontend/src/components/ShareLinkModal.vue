<script setup>
/**
 * 公开分享链接弹窗：展示链接，支持复制/打开/重新分享/取消分享。
 */
import { computed } from "vue";
import AdminFormModal from "./AdminFormModal.vue";
import { openExternal } from "../utils/openExternal.js";

const show = defineModel("show", { type: Boolean, default: false });

const props = defineProps({
  title: { type: String, default: "分享链接" },
  url: { type: String, default: "" },
  loading: { type: Boolean, default: false },
  /** 是否已有有效分享（决定展示「生成」还是「重新/取消」） */
  shared: { type: Boolean, default: false },
  hint: {
    type: String,
    default: "链接可公开访问最新内容；重新分享将更新链接，旧链接失效。",
  },
});

const emit = defineEmits(["generate", "reshare", "unshare", "copy"]);

const displayUrl = computed(() => String(props.url || "").trim());
const hasUrl = computed(() => Boolean(displayUrl.value));

function onCopy() {
  emit("copy", displayUrl.value);
}

function onOpen() {
  if (displayUrl.value) openExternal(displayUrl.value);
}
</script>

<template>
  <AdminFormModal v-model:show="show" :title="title" width="480px">
    <p v-if="hint" class="share-link-modal__hint">{{ hint }}</p>

    <div v-if="hasUrl" class="share-link-modal__row">
      <input class="share-link-modal__input" readonly :value="displayUrl" />
      <n-button size="tiny" :disabled="loading" @click="onCopy">复制</n-button>
      <n-button size="tiny" quaternary :disabled="loading" @click="onOpen">打开</n-button>
    </div>
    <p v-else class="share-link-modal__empty">尚未生成分享链接</p>

    <template #footer>
      <n-button size="small" :disabled="loading" @click="show = false">关闭</n-button>
      <template v-if="shared || hasUrl">
        <n-button size="small" :loading="loading" @click="emit('reshare')">
          重新分享
        </n-button>
        <n-button size="small" type="error" secondary :loading="loading" @click="emit('unshare')">
          取消分享
        </n-button>
      </template>
      <n-button
        v-else
        size="small"
        type="primary"
        :loading="loading"
        @click="emit('generate')"
      >
        生成链接
      </n-button>
    </template>
  </AdminFormModal>
</template>

<style scoped>
.share-link-modal__hint {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}

.share-link-modal__row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.share-link-modal__input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--platform-border-strong);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  background: var(--platform-bg);
  color: var(--platform-text);
}

.share-link-modal__empty {
  margin: 0;
  font-size: 13px;
  color: var(--platform-text-tertiary);
}
</style>
