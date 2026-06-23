<script setup>
import { computed, ref } from "vue";
import { NIcon, NInput, NSpin } from "naive-ui";
import { ArrowUpOutline, AttachOutline, StopOutline } from "@vicons/ionicons5";

const props = defineProps({
  modelValue: { type: String, default: "" },
  placeholder: { type: String, default: "输入您的问题" },
  disabled: { type: Boolean, default: false },
  /** 智能体正在流式回复 */
  loading: { type: Boolean, default: false },
  /** 流式回复时是否禁用输入（false 时可边生成边编辑下一条） */
  disableInputWhileLoading: { type: Boolean, default: true },
  minRows: { type: Number, default: 2 },
  maxRows: { type: Number, default: 6 },
  /** 在发送按钮旁展示上传附件（无背板图标按钮） */
  showAttachment: { type: Boolean, default: false },
  attachmentLoading: { type: Boolean, default: false },
  attachmentDisabled: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "send", "stop", "keydown", "attach"]);

const inputDisabled = computed(
  () => props.disabled || (props.disableInputWhileLoading && props.loading)
);

const canSend = computed(
  () => Boolean(props.modelValue?.trim()) && !props.disabled && !props.loading
);

const autosize = computed(() => ({
  minRows: props.minRows,
  maxRows: props.maxRows}));

/** 单行紧凑布局：仅当 maxRows=1；否则允许从 1 行起自动增高 */
const isSingleLine = computed(() => props.maxRows <= 1);

function onKeydown(e) {
  emit("keydown", e);
}

const inputRef = ref(null);

function focus() {
  inputRef.value?.focus?.();
}

defineExpose({ focus });
</script>

<template>
  <div
    class="chat-composer"
    :class="{
      'chat-composer--generating': loading,
      'chat-composer--single': isSingleLine,
      'chat-composer--with-attach': showAttachment,
    }"
  >
    <n-input
      ref="inputRef"
      :value="modelValue"
      class="chat-composer__input ai-chat-textarea"
      type="textarea"
      :autosize="autosize"
      :placeholder="placeholder"
      :disabled="inputDisabled"
      @update:value="emit('update:modelValue', $event)"
      @keydown="onKeydown"
    />
    <div class="chat-composer__actions">
      <button
        v-if="showAttachment"
        type="button"
        class="chat-composer__attach"
        :disabled="attachmentDisabled"
        aria-label="上传附件"
        @click="emit('attach')"
      >
        <n-spin v-if="attachmentLoading" :size="14" />
        <n-icon v-else :size="18" :component="AttachOutline" />
      </button>
      <button
        v-if="loading"
        type="button"
        class="chat-composer__send chat-composer__send--stop"
        aria-label="停止生成"
        @click="emit('stop')"
      >
        <n-icon :size="15" :component="StopOutline" />
      </button>
      <button
        v-else
        type="button"
        class="chat-composer__send"
        :disabled="!canSend"
        aria-label="发送"
        @click="emit('send')"
      >
        <n-icon :size="15" :component="ArrowUpOutline" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-composer {
  position: relative;
  width: 100%;
  border-radius: 16px;
  overflow: hidden;
}

.chat-composer__input :deep(.n-input__border),
.chat-composer__input :deep(.n-input__state-border) {
  border-radius: 16px;
}

.chat-composer__input :deep(.n-input-wrapper) {
  border-radius: 16px;
  box-shadow: none;
  background: #fff;
}

.chat-composer__input :deep(.n-input__textarea-el),
.chat-composer__input :deep(.n-input__placeholder),
.chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 52px !important;
  padding-bottom: 44px !important;
}

.chat-composer--single .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--single .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--single .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-top: 10px !important;
  padding-bottom: 10px !important;
  padding-right: 42px !important;
  min-height: 40px !important;
}

.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--with-attach .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 80px !important;
}

.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 68px !important;
}

.chat-composer__actions {
  position: absolute;
  right: 8px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 2px;
}

.chat-composer--single .chat-composer__actions {
  top: 50%;
  bottom: auto;
  transform: translateY(-50%);
}

.chat-composer:not(.chat-composer--single) .chat-composer__actions {
  bottom: 10px;
}

.chat-composer__attach {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  padding: 0;
  transition: color 0.15s ease;
}

.chat-composer__attach:hover:not(:disabled) {
  color: var(--platform-accent);
}

.chat-composer__attach:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chat-composer__send {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  color: #fff;
  background: var(--platform-accent-gradient);
  box-shadow: 0 2px 6px color-mix(in srgb, var(--platform-accent) 24%, transparent);
  transition:
    transform 0.18s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.18s ease,
    box-shadow 0.18s ease;
}

.chat-composer--single .chat-composer__send:hover {
  transform: translateY(-1px);
  box-shadow: 0 3px 10px color-mix(in srgb, var(--platform-accent) 30%, transparent);
}

.chat-composer--single .chat-composer__send:active {
  transform: scale(0.96);
}

.chat-composer:not(.chat-composer--single) .chat-composer__send:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--platform-accent) 32%, transparent);
}

.chat-composer:not(.chat-composer--single) .chat-composer__send:active:not(:disabled) {
  transform: translateY(0) scale(0.96);
}

.chat-composer__send:disabled {
  cursor: not-allowed;
  opacity: 0.42;
  box-shadow: none;
}

.chat-composer__send--stop {
  background: var(--platform-accent-gradient);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--platform-accent) 28%, transparent);
}

.chat-composer__send--stop:hover {
  background: var(--platform-accent-gradient-hover);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--platform-accent) 32%, transparent);
}
</style>
