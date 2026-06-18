<script setup>
import { DocumentTextOutline, CloudUploadOutline, CheckmarkCircleOutline } from "@vicons/ionicons5";
import { NIcon, NText, NButton } from "naive-ui";
import { computed, ref } from "vue";
import { useI18n } from "../composables/useI18n";

const { t } = useI18n();

const props = defineProps({
  accept: { type: String, default: "*" },
  multiple: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  title: { type: String, required: true },
  hint: { type: String, default: "" },
  fileName: { type: String, default: "" },
  icon: { type: String, default: "upload" },
  compact: { type: Boolean, default: false }});

const emit = defineEmits(["change"]);
const inputRef = ref(null);
const dragging = ref(false);

function pick() {
  if (!props.disabled) inputRef.value?.click();
}

function onChange(e) {
  emit("change", e);
  if (e.target) e.target.value = "";
}

function onDrop(e) {
  e.preventDefault();
  dragging.value = false;
  if (props.disabled) return;
  const files = e.dataTransfer?.files;
  if (!files?.length) return;
  emit("change", { target: { files } });
}

const iconComponent = computed(() => {
  if (props.fileName) return CheckmarkCircleOutline;
  return props.icon === "doc" ? DocumentTextOutline : CloudUploadOutline;
});
</script>

<template>
  <div
    class="drop-zone"
    :class="{ dragging, disabled, filled: !!fileName, compact }"
    @click="pick"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop="onDrop"
  >
    <input
      ref="inputRef"
      type="file"
      class="hidden-input"
      :accept="accept"
      :multiple="multiple"
      :disabled="disabled"
      @change="onChange"
    />
    <div class="drop-icon-wrap" :class="{ filled: !!fileName }">
      <n-icon :size="26" :depth="fileName ? 1 : 2">
        <component :is="iconComponent" />
      </n-icon>
    </div>
    <n-text strong class="drop-title">{{ fileName ? t("common.fileDrop.selectedFile") : title }}</n-text>
    <n-text depth="3" class="drop-hint">{{ fileName ? fileName : hint }}</n-text>
    <n-button
      v-if="!disabled"
      :type="fileName ? 'default' : 'primary'"
      :secondary="!fileName"
      size="small"
      class="drop-btn"
      @click.stop="pick"
    >
      {{ fileName ? t("common.fileDrop.replaceFile") : t("common.fileDrop.selectFile") }}
    </n-button>
  </div>
</template>

<style scoped>
.drop-zone {
  border: 1.5px dashed var(--n-border-color);
  border-radius: 10px;
  padding: 1.35rem 1rem;
  min-height: 148px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  cursor: pointer;
  background: var(--n-color);
  transition:
    border-color 0.2s,
    background 0.2s,
    box-shadow 0.2s;
}
.drop-zone:hover:not(.disabled) {
  border-color: var(--n-text-color-3);
  background: var(--n-action-color);
}
.drop-zone.dragging {
  border-color: #5b8def;
  background: rgba(91, 141, 239, 0.06);
  box-shadow: 0 0 0 3px rgba(91, 141, 239, 0.12);
}
.drop-zone.filled {
  border-style: solid;
  border-color: var(--platform-accent-border);
  background: var(--platform-accent-muted);
}
.drop-zone.filled:hover:not(.disabled) {
  border-color: var(--platform-accent);
  background: var(--platform-accent-soft);
}
.drop-zone.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.hidden-input {
  display: none;
}
.drop-icon-wrap {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.65rem;
  background: var(--n-action-color);
  color: var(--n-text-color-2);
}
.drop-icon-wrap.filled {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
}
.drop-title {
  display: block;
  font-size: 14px;
  margin-bottom: 0.25rem;
}
.drop-hint {
  display: block;
  font-size: 12px;
  line-height: 1.45;
  max-width: 100%;
  word-break: break-all;
}
.drop-btn {
  margin-top: 0.75rem;
}
.drop-zone.compact {
  min-height: 100px;
  padding: 0.85rem 0.75rem;
}
.drop-zone.compact .drop-icon-wrap {
  width: 40px;
  height: 40px;
  margin-bottom: 0.4rem;
}
.drop-zone.compact .drop-title {
  font-size: 13px;
}
.drop-zone.compact .drop-btn {
  margin-top: 0.5rem;
}
</style>
