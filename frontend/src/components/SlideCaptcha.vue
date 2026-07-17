<script setup>
import { onMounted, ref } from "vue";
import { captchaGenerate, captchaVerify } from "../api/auth.js";

const emit = defineEmits(["update:modelValue"]);

const props = defineProps({
  modelValue: { type: String, default: "" },
});

const captchaImage = ref("");
const captchaId = ref("");
const answer = ref("");
const inputRef = ref(null);
const loading = ref(false);
const verifying = ref(false);
const errorMsg = ref("");

async function loadCaptcha() {
  loading.value = true;
  errorMsg.value = "";
  answer.value = "";
  try {
    const res = await captchaGenerate();
    captchaId.value = res.captcha_id;
    captchaImage.value = res.image;
  } catch {
    errorMsg.value = "验证码加载失败";
  } finally {
    loading.value = false;
    inputRef.value?.focus();
  }
}

function sanitize(v) {
  return v.replace(/[^234679ABCDEFGHJKMNPQRTUVWXYZabcdefghjkmnpqrtuvwxyz]/g, "").slice(0, 4);
}

function onInput() {
  answer.value = sanitize(answer.value);
}

function onPaste(e) {
  const text = (e.clipboardData || window.clipboardData).getData("text");
  const clean = sanitize(text);
  if (clean.length > 0) {
    e.preventDefault();
    answer.value = clean;
  }
}

async function onVerify() {
  if (verifying.value) return;
  if (answer.value.length !== 4) {
    errorMsg.value = "请输入验证码";
    throw new Error("请输入验证码");
  }
  verifying.value = true;
  errorMsg.value = "";
  try {
    const res = await captchaVerify(captchaId.value, answer.value);
    emit("update:modelValue", res.token);
  } catch (e) {
    errorMsg.value = e.message || "验证码错误";
    loadCaptcha();
    throw e;
  } finally {
    verifying.value = false;
  }
}

defineExpose({ verify: onVerify });

onMounted(() => {
  loadCaptcha();
});
</script>

<template>
  <div class="text-captcha" @paste="onPaste">
    <!-- 验证码图片 -->
    <div class="text-captcha__image-row">
      <div v-if="loading" class="text-captcha__image-placeholder">
        <span class="text-captcha__spinner" />
        <span>加载中...</span>
      </div>
      <img
        v-else
        :src="captchaImage"
        alt="验证码"
        class="text-captcha__image"
        @click="loadCaptcha"
      />
      <button
        type="button"
        class="text-captcha__refresh"
        title="换一张"
        :disabled="loading"
        @click="loadCaptcha"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      </button>
    </div>

    <!-- 单行输入框 -->
    <input
      ref="inputRef"
      v-model="answer"
      type="text"
      inputmode="text"
      maxlength="4"
      class="text-captcha__input"
      :class="{ 'text-captcha__input--error': errorMsg }"
      :disabled="loading || verifying"
      placeholder="输入验证码"
      autocomplete="off"
      @input="onInput"
    />

    <!-- 错误/提示 -->
    <div v-if="errorMsg" class="text-captcha__error">{{ errorMsg }}</div>

    <!-- 验证中遮罩 -->
    <div v-if="verifying" class="text-captcha__verifying">
      <span class="text-captcha__spinner" />
      <span>验证中...</span>
    </div>

    <div class="text-captcha__hint">点击图片可刷新验证码</div>
  </div>
</template>

<style scoped>
.text-captcha {
  position: relative;
  width: 100%;
  max-width: 260px;
  margin: 0 auto;
  user-select: none;
}

.text-captcha__image-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.text-captcha__image {
  flex: 1;
  height: 60px;
  border-radius: 6px;
  cursor: pointer;
  object-fit: contain;
  background: #f5f6f7;
  border: 1px solid var(--platform-border, rgba(148, 163, 184, 0.28));
  transition: opacity 0.15s;
}

html[data-theme="dark"] .text-captcha__image {
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--platform-accent-border-soft);
}

.text-captcha__image:hover {
  opacity: 0.8;
}

.text-captcha__image-placeholder {
  flex: 1;
  height: 60px;
  border-radius: 6px;
  background: var(--platform-bg-secondary, #f0f2f5);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  color: var(--platform-text-tertiary, #999);
}

html[data-theme="dark"] .text-captcha__image-placeholder {
  background: rgba(255, 255, 255, 0.04);
}

.text-captcha__refresh {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--platform-border, rgba(148, 163, 184, 0.28));
  background: transparent;
  color: var(--platform-text-secondary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s, border-color 0.15s;
}

.text-captcha__refresh:hover:not(:disabled) {
  color: var(--platform-accent);
  border-color: var(--platform-accent);
}

.text-captcha__refresh:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 单行输入框 */
.text-captcha__input {
  display: block;
  width: 100%;
  height: 46px;
  padding: 0 16px;
  text-align: center;
  font-size: 22px;
  font-family: "SF Mono", "Fira Code", "Cascadia Code", monospace;
  letter-spacing: 10px;
  border: 2px solid var(--platform-border, rgba(148, 163, 184, 0.28));
  border-radius: 10px;
  background: transparent;
  color: var(--platform-text);
  outline: none;
  caret-color: var(--platform-accent);
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}

.text-captcha__input:focus {
  border-color: var(--platform-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--platform-accent) 15%, transparent);
}

.text-captcha__input--error {
  border-color: #e74c3c;
  animation: shake 0.3s ease;
}

.text-captcha__input::placeholder {
  font-size: 14px;
  letter-spacing: 1px;
  color: var(--platform-text-tertiary, #bbb);
}

.text-captcha__input:disabled {
  opacity: 0.5;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}

.text-captcha__error {
  margin-top: 6px;
  font-size: 12px;
  color: #e74c3c;
  text-align: center;
}

.text-captcha__verifying {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.75);
  border-radius: 10px;
  font-size: 13px;
  color: #666;
  z-index: 10;
}

html[data-theme="dark"] .text-captcha__verifying {
  background: rgba(15, 15, 22, 0.75);
}

.text-captcha__spinner {
  width: 20px;
  height: 20px;
  border: 2.5px solid #e0e0e0;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.text-captcha__hint {
  margin-top: 6px;
  font-size: 11px;
  text-align: center;
  color: var(--platform-text-tertiary, #aaa);
  opacity: 0.6;
}
</style>
