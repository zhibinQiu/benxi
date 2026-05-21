<script setup>
import { DocumentTextOutline, CloudUploadOutline } from "@vicons/ionicons5";
import { NIcon, NText, NButton } from "naive-ui";
import { computed, ref } from "vue";

const props = defineProps({
  accept: { type: String, default: "*" },
  multiple: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  title: { type: String, required: true },
  hint: { type: String, default: "" },
  fileName: { type: String, default: "" },
  icon: { type: String, default: "upload" },
});

const emit = defineEmits(["change"]);
const inputRef = ref(null);
const dragging = ref(false);

function pick() {
  if (!props.disabled) inputRef.value?.click();
}

function onChange(e) {
  emit("change", e);
}

function onDrop(e) {
  e.preventDefault();
  dragging.value = false;
  if (props.disabled) return;
  const files = e.dataTransfer?.files;
  if (!files?.length) return;
  emit("change", { target: { files } });
}

const iconComponent = computed(() =>
  props.icon === "doc" ? DocumentTextOutline : CloudUploadOutline
);
</script>

<template>
  <div
    class="drop-zone"
    :class="{ dragging, disabled, filled: !!fileName }"
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
    <div class="drop-icon">
      <n-icon :size="24" :depth="2">
        <component :is="iconComponent" />
      </n-icon>
    </div>
    <n-text strong class="drop-title">{{ title }}</n-text>
    <n-text depth="3" class="drop-hint">{{ hint }}</n-text>
    <n-text v-if="fileName" depth="2" class="drop-file">{{ fileName }}</n-text>
    <n-button v-if="!disabled" quaternary size="small" class="drop-btn" @click.stop="pick">
      选择文件
    </n-button>
  </div>
</template>

<style scoped>
.drop-zone {
  border: 1px dashed var(--n-border-color);
  border-radius: 8px;
  padding: 1rem 0.75rem;
  text-align: center;
  cursor: pointer;
  background: var(--n-color);
  transition: border-color 0.2s, background 0.2s;
}
.drop-zone:hover:not(.disabled) {
  border-color: var(--n-text-color-3);
  background: var(--n-action-color);
}
.drop-zone.dragging {
  border-color: var(--n-text-color-2);
  background: var(--n-action-color);
}
.drop-zone.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.hidden-input {
  display: none;
}
.drop-icon {
  margin-bottom: 0.35rem;
}
.drop-title {
  display: block;
  font-size: 14px;
  margin-bottom: 0.2rem;
}
.drop-hint {
  display: block;
  font-size: 12px;
}
.drop-file {
  display: block;
  margin-top: 0.35rem;
  font-size: 12px;
}
.drop-btn {
  margin-top: 0.35rem;
}
</style>
