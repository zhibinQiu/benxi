<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import { NIcon, NInput, NSpin } from "naive-ui";
import { ArrowUpOutline, AttachOutline, CloseOutline, DocumentTextOutline, StopOutline } from "@vicons/ionicons5";

const props = defineProps({
  modelValue: { type: String, default: "" },
  placeholder: { type: String, default: "输入您的问题" },
  disabled: { type: Boolean, default: false },
  /** 智能体正在流式回复 */
  loading: { type: Boolean, default: false },
  /** 流式回复时是否禁用输入（false 时可边生成边编辑，发送需先停止） */
  disableInputWhileLoading: { type: Boolean, default: false },
  minRows: { type: Number, default: 2 },
  maxRows: { type: Number, default: 6 },
  /** 在发送按钮旁展示上传附件（无背板图标按钮） */
  showAttachment: { type: Boolean, default: false },
  attachmentLoading: { type: Boolean, default: false },
  attachmentDisabled: { type: Boolean, default: false },
  /** 已上传附件，名称展示在输入框内 */
  attachments: { type: Array, default: () => [] },
  /** 是否对 #关键词 做行内高亮渲染（隐藏井号，为文字添加背景） */
  highlightHashtags: { type: Boolean, default: true },
});

const emit = defineEmits(["update:modelValue", "send", "stop", "keydown", "attach", "remove-attachment"]);

const hasAttachments = computed(() => props.attachments.length > 0);

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

/**
 * 将普通文本转为带 #关键词 高亮样式的 HTML。
 * - 隐藏井号（保留占位宽度）
 * - 关键词部分添加字体背景色
 */
function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const HASHTAG_REGEX = /(^|\s)(#)([\w\u4e00-\u9fff]+)/g;

/** 当前文本是否包含需高亮的 #关键词（使用非全局 regex 避免 lastIndex 副作用） */
const hasHashtags = computed(
  () => props.highlightHashtags && props.modelValue && /(^|\s)#[\w\u4e00-\u9fff]+/.test(props.modelValue),
);

const highlightedHtml = computed(() => {
  if (!hasHashtags.value) return "";
  const escaped = escapeHtml(props.modelValue);
  const withBreaks = escaped.replace(/\n/g, "<br>");
  return withBreaks.replace(
    HASHTAG_REGEX,
    (_match, before, _hash, keyword) =>
      `${before}<span class="hashtag-chip"><span class="hashtag-hash">#</span><span class="hashtag-text">${keyword}</span></span>`,
  );
});

function onKeydown(e) {
  emit("keydown", e);
}

const inputRef = ref(null);
const mirrorRef = ref(null);
let textareaEl = null;

function syncMirrorScroll() {
  if (mirrorRef.value && textareaEl) {
    mirrorRef.value.scrollTop = textareaEl.scrollTop;
  }
}

function onTextareaScroll() {
  syncMirrorScroll();
}

function syncMirrorPadding() {
  if (!mirrorRef.value || !textareaEl) return;
  const cs = getComputedStyle(textareaEl);
  mirrorRef.value.style.paddingTop = cs.paddingTop;
  mirrorRef.value.style.paddingRight = cs.paddingRight;
  mirrorRef.value.style.paddingBottom = cs.paddingBottom;
  mirrorRef.value.style.paddingLeft = cs.paddingLeft;
}

onMounted(() => {
  nextTick(() => {
    textareaEl = inputRef.value?.$el?.querySelector?.("textarea");
    if (textareaEl) {
      textareaEl.addEventListener("scroll", onTextareaScroll, { passive: true });
      syncMirrorPadding();
    }
  });
});

onBeforeUnmount(() => {
  if (textareaEl) {
    textareaEl.removeEventListener("scroll", onTextareaScroll);
    textareaEl = null;
  }
});

/* 值变化时同步镜像层的 padding（覆盖首次出现及父组件状态切换导致的 padding 变化） */
watch(
  () => props.modelValue,
  () => {
    nextTick(() => {
      if (mirrorRef.value) syncMirrorPadding();
    });
  },
);

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
      'chat-composer--has-files': hasAttachments,
    }"
  >
    <div class="chat-composer__surface">
      <div v-if="hasAttachments" class="chat-composer__attachments">
        <div
          v-for="file in attachments"
          :key="file.file_id"
          class="chat-composer__attachment-chip"
          :title="file.warning || file.file_name"
        >
          <n-icon :size="15" :component="DocumentTextOutline" />
          <span class="chat-composer__attachment-name">{{ file.file_name }}</span>
          <button
            type="button"
            class="chat-composer__attachment-remove"
            :disabled="attachmentDisabled"
            aria-label="移除附件"
            @click="emit('remove-attachment', file.file_id)"
          >
            <n-icon :size="13" :component="CloseOutline" />
          </button>
        </div>
      </div>
      <div class="chat-composer__editor-area">
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
        <div
          v-if="hasHashtags"
          ref="mirrorRef"
          class="chat-composer__hashtag-mirror"
          v-html="highlightedHtml"
        />
      </div>
      <div v-if="$slots.toolbar" class="chat-composer__toolbar">
        <slot name="toolbar" />
      </div>
    </div>
    <div class="chat-composer__actions">
      <button
        v-if="showAttachment"
        type="button"
        class="chat-composer__attach"
        :disabled="attachmentDisabled"
        aria-label="上传附件"
        @click="emit('attach')"
      >
        <n-spin v-if="attachmentLoading" :size="17" />
        <n-icon v-else :size="22" :component="AttachOutline" />
      </button>
      <button
        v-if="loading"
        type="button"
        class="chat-composer__send chat-composer__send--stop"
        aria-label="停止生成"
        @click="emit('stop')"
      >
        <n-icon :size="18" :component="StopOutline" />
      </button>
      <button
        v-else
        type="button"
        class="chat-composer__send"
        :disabled="!canSend"
        aria-label="发送"
        @click="emit('send')"
      >
        <n-icon :size="18" :component="ArrowUpOutline" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-composer {
  position: relative;
  width: 100%;
}

.chat-composer__surface {
  position: relative;
  border-radius: var(--platform-radius);
  overflow: hidden;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
  transition: border-color var(--platform-duration-smooth) ease;
}

/* 镜像层容器，与 textarea 叠放 */
.chat-composer__editor-area {
  position: relative;
}

/* 高亮镜像层——浮在 textarea 上方 */
.chat-composer__hashtag-mirror {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  word-break: break-word;
  overflow: hidden; /* 不产生滚动，跟随 textarea 滚动 */
  color: transparent; /* 非 chip 部分透明，露出 textarea 文字 */
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  /* padding 由 JS 在运行时从 textarea 同步，此处只留默认 fallback */
  padding: 6px 12px;
  -webkit-user-select: none;
  user-select: none;
}

.chat-composer:focus-within .chat-composer__surface {
  border-color: var(--platform-border-strong);
}

.chat-composer__attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px 0;
}

.chat-composer__attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 3px 8px 3px 10px;
  border-radius: var(--platform-radius-pill);
  background: var(--platform-bg-secondary);
  border: 1px solid var(--platform-border);
  color: var(--platform-text-secondary);
  font-size: 13px;
}

.chat-composer__attachment-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.chat-composer__attachment-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--platform-text-tertiary);
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}

.chat-composer__attachment-remove:hover:not(:disabled) {
  color: var(--platform-danger);
  background: var(--platform-danger-soft);
}

.chat-composer__attachment-remove:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chat-composer__input :deep(.n-input__border),
.chat-composer__input :deep(.n-input__state-border) {
  border: none !important;
  box-shadow: none !important;
}

.chat-composer__input :deep(.n-input-wrapper) {
  border-radius: 0;
  box-shadow: none !important;
  background: transparent !important;
}

.chat-composer__input :deep(.n-input:not(.n-input--disabled):hover .n-input__state-border),
.chat-composer__input :deep(.n-input.n-input--focus .n-input__state-border) {
  border: none !important;
  box-shadow: none !important;
}

.chat-composer--has-files .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--has-files .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--has-files .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-top: 8px !important;
}

.chat-composer__input :deep(.n-input__textarea-el),
.chat-composer__input :deep(.n-input__placeholder),
.chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 62px !important;
  padding-bottom: 53px !important;
}

.chat-composer__input :deep(.n-input__textarea-el) {
  color: var(--platform-text);
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.chat-composer__input :deep(.n-input__textarea-el)::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.chat-composer--single .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--single .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--single .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-top: 12px !important;
  padding-bottom: 12px !important;
  padding-right: 50px !important;
  min-height: 48px !important;
}

.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--with-attach .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 96px !important;
}

.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 82px !important;
}

.chat-composer--single.chat-composer--has-files .chat-composer__actions {
  top: auto;
  bottom: 12px;
  transform: none;
}

.chat-composer__actions {
  position: absolute;
  right: 10px;
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
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--platform-text-tertiary);
  cursor: pointer;
  padding: 0;
  transition: color var(--platform-duration-smooth) ease, background var(--platform-duration-smooth) ease;
}

.chat-composer__attach:hover:not(:disabled) {
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}

.chat-composer__attach:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chat-composer__send {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  color: #fff;
  background: var(--platform-accent);
  box-shadow: 0 1px 3px color-mix(in srgb, var(--platform-accent) 20%, transparent);
  transition:
    transform 0.18s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease;
}

.chat-composer--single .chat-composer__send:hover {
  transform: translateY(-1px);
  background: var(--platform-accent-hover);
  box-shadow: 0 3px 8px color-mix(in srgb, var(--platform-accent) 25%, transparent);
}

.chat-composer--single .chat-composer__send:active {
  transform: scale(0.96);
}

.chat-composer:not(.chat-composer--single) .chat-composer__send:hover:not(:disabled) {
  transform: translateY(-1px);
  background: var(--platform-accent-hover);
  box-shadow: 0 3px 8px color-mix(in srgb, var(--platform-accent) 25%, transparent);
}

.chat-composer:not(.chat-composer--single) .chat-composer__send:active:not(:disabled) {
  transform: translateY(0) scale(0.96);
}

.chat-composer__send:disabled {
  cursor: not-allowed;
  opacity: 0.35;
  box-shadow: none;
}

.chat-composer__send--stop {
  background: var(--platform-accent);
  box-shadow: 0 1px 4px color-mix(in srgb, var(--platform-accent) 22%, transparent);
}

.chat-composer__send--stop:hover {
  background: var(--platform-accent-hover);
  box-shadow: 0 3px 10px color-mix(in srgb, var(--platform-accent) 28%, transparent);
}

.chat-composer__toolbar {
  position: absolute;
  left: 10px;
  bottom: 10px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 4px;
  pointer-events: none;
}

.chat-composer__toolbar > * {
  pointer-events: auto;
}
</style>

<!-- hashtag chip 样式必须为非 scoped，因为 v-html 内容不受 scoped 影响 -->
<style>
/* #关键词 高亮 chip——浮在 textarea 上方的覆盖层 */
.hashtag-chip {
  display: inline;
  color: var(--platform-text);
  background: color-mix(in srgb, var(--platform-accent) 14%, transparent);
  border-radius: 4px;
  padding: 0 1px;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}

/* 井号保留在 chip 内（可见，作为 chip 的一部分） */
.hashtag-chip .hashtag-hash {
  display: inline;
}

/* 关键词文本继承 chip 样式 */
.hashtag-chip .hashtag-text {
  display: inline;
}
</style>
