<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import { NIcon, NInput, NSpin } from "naive-ui";
import {
  ArrowUpOutline, AttachOutline, CloseOutline, DocumentTextOutline,
  MicOutline, StopOutline,
} from "@vicons/ionicons5";
import { escapeHtml } from "../utils/markdown.js";

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
  highlightHashtags: { type: Boolean, default: false },
  /** 显示语音输入按钮 */
  showVoiceInput: { type: Boolean, default: false },
  /** 语音正在转写中 */
  voiceProcessing: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "send", "stop", "keydown", "attach", "remove-attachment", "voiceInput"]);

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

/** 将普通文本转为带 #关键词 高亮样式的 HTML。
 * - 隐藏井号（保留占位宽度）
 * - 关键词部分添加字体背景色
 */

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

/* ---- 语音输入 ---- */
const recording = ref(false);
let mediaRecorder = null;
let audioChunks = [];

async function startVoiceRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      // 释放麦克风
      stream.getTracks().forEach((t) => t.stop());
      mediaRecorder = null;
      recording.value = false;
      emit("voiceInput", blob);
    };
    mediaRecorder.onerror = () => {
      stream.getTracks().forEach((t) => t.stop());
      mediaRecorder = null;
      recording.value = false;
    };
    mediaRecorder.start();
    recording.value = true;
  } catch (err) {
    recording.value = false;
    // 权限被拒绝等错误由父组件处理
    emit("voiceInput", null, err.message || "无法访问麦克风");
  }
}

function stopVoiceRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
}

function toggleVoiceRecording() {
  if (props.voiceProcessing) return;
  if (recording.value) {
    stopVoiceRecording();
  } else {
    startVoiceRecording();
  }
}

const micDisabled = computed(() => props.disabled || props.voiceProcessing);
/* ---- 语音输入结束 ---- */

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
      'chat-composer--with-voice': showVoiceInput,
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
        v-if="showVoiceInput"
        type="button"
        class="chat-composer__voice"
        :class="{ 'chat-composer__voice--recording': recording, 'chat-composer__voice--processing': voiceProcessing }"
        :disabled="micDisabled"
        :aria-label="recording ? '停止录音' : '语音输入'"
        @click="toggleVoiceRecording"
      >
        <n-spin v-if="voiceProcessing" :size="17" />
        <n-icon v-else :size="19" :component="MicOutline" />
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
  background: var(--platform-bg-elevated-solid, #fcfcfc);
  transition: border-color var(--platform-duration-smooth) ease, box-shadow var(--platform-duration-smooth) ease;
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
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.3), none;
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

.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--with-voice .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 130px !important;
}

.chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 162px !important;
}

.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--single.chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 82px !important;
}

.chat-composer--single.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--single.chat-composer--with-voice .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--single.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 114px !important;
}

.chat-composer--single.chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-el),
.chat-composer--single.chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__placeholder),
.chat-composer--single.chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-mirror) {
  padding-right: 146px !important;
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

.chat-composer__voice {
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
  transition: color var(--platform-duration-smooth) ease, background var(--platform-duration-smooth) ease, transform 0.18s ease;
  position: relative;
}

.chat-composer__voice:hover:not(:disabled) {
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}

.chat-composer__voice:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* 录音中状态——红色脉冲呼吸 */
.chat-composer__voice--recording {
  color: #e53e3e !important;
  background: rgba(229, 62, 62, 0.1) !important;
  animation: voice-record-pulse 1.4s ease-in-out infinite;
}

.chat-composer__voice--recording:hover {
  background: rgba(229, 62, 62, 0.18) !important;
}

@keyframes voice-record-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(229, 62, 62, 0.35); }
  50% { box-shadow: 0 0 0 8px rgba(229, 62, 62, 0); }
}

/* 转写中状态——使用 accent 色微呼吸 */
.chat-composer__voice--processing {
  color: var(--platform-accent) !important;
  background: var(--platform-accent-soft) !important;
  animation: voice-process-pulse 1s ease-in-out infinite;
}

@keyframes voice-process-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* 当同时显示附件按钮和语音按钮时调整右侧间距 */
.chat-composer--with-attach .chat-composer__voice {
  /* 附件按钮 + 语音按钮按顺序排列 */
}

.chat-composer__toolbar {
  position: absolute;
  left: 10px;
  bottom: 10px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 2px;
  pointer-events: none;
}

.chat-composer__toolbar > * {
  pointer-events: auto;
}

/* ── 移动端紧凑模式 ── */
@media (max-width: 768px) {
  .chat-composer__input :deep(.n-input__textarea-el),
  .chat-composer__input :deep(.n-input__placeholder),
  .chat-composer__input :deep(.n-input__textarea-mirror) {
    font-size: 15px !important;
    padding-right: 52px !important;
  }

  .chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-el),
  .chat-composer--with-attach .chat-composer__input :deep(.n-input__placeholder),
  .chat-composer--with-attach .chat-composer__input :deep(.n-input__textarea-mirror) {
    padding-right: 80px !important;
  }

  .chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-el),
  .chat-composer--with-voice .chat-composer__input :deep(.n-input__placeholder),
  .chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-mirror) {
    padding-right: 108px !important;
  }

  .chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-el),
  .chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__placeholder),
  .chat-composer--with-attach.chat-composer--with-voice .chat-composer__input :deep(.n-input__textarea-mirror) {
    padding-right: 136px !important;
  }

  .chat-composer__send,
  .chat-composer__attach,
  .chat-composer__voice {
    width: 28px;
    height: 28px;
  }
  .chat-composer__send :deep(.n-icon),
  .chat-composer__attach :deep(.n-icon),
  .chat-composer__voice :deep(.n-icon) {
    font-size: 16px !important;
  }

  .chat-composer__actions {
    right: 4px;
    gap: 0;
  }
  .chat-composer:not(.chat-composer--single) .chat-composer__actions {
    bottom: 4px;
  }

  .chat-composer__toolbar {
    left: 4px;
    bottom: 4px;
  }

  .chat-composer__attachment-chip {
    font-size: 12px;
    padding: 2px 6px 2px 8px;
  }
  .chat-composer__attachment-name {
    max-width: 120px;
  }
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

/* 井号在 chip 内不可见，让底层 textarea 的 # 透出（仅 chip 背景色可见） */
.hashtag-chip .hashtag-hash {
  display: inline;
  color: transparent;
}

/* 关键词文本继承 chip 样式 */
.hashtag-chip .hashtag-text {
  display: inline;
}
</style>
