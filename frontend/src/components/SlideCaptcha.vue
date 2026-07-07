<script setup>
import { ref, watch } from "vue";
import SlideVerify from "vue3-slide-verify";
import "vue3-slide-verify/dist/style.css";
import { captchaIssue } from "../api/auth.js";

const props = defineProps({
  modelValue: { type: String, default: "" },
  width: { type: Number, default: 290 },
  height: { type: Number, default: 160 },
});

const emit = defineEmits(["update:modelValue"]);

const slideRef = ref(null);
const verifying = ref(false);

function refresh() {
  if (slideRef.value) {
    slideRef.value.refresh();
  }
}

async function onSuccess({ timestamp, left }) {
  verifying.value = true;
  try {
    const res = await captchaIssue();
    emit("update:modelValue", res.token);
  } catch {
    // 网络错误时使用前端标记
    emit("update:modelValue", "__verified__");
  } finally {
    verifying.value = false;
  }
}

function onFail() {
  // 自动由组件处理刷新
}

function onRefresh() {
  emit("update:modelValue", "");
}

watch(
  () => props.modelValue,
  (val) => {
    if (!val) {
      // 外部重置时刷新组件
      refresh();
    }
  }
);

defineExpose({ refresh });
</script>

<template>
  <div class="slide-captcha" :class="{ 'slide-captcha--verifying': verifying }">
    <SlideVerify
      ref="slideRef"
      :w="width"
      :h="height"
      :show="true"
      slider-text="向右滑动完成验证"
      @success="onSuccess"
      @fail="onFail"
      @refresh="onRefresh"
    />
    <div v-if="verifying" class="slide-captcha__overlay">
      <span class="slide-captcha__spinner" />
      <span>验证中...</span>
    </div>
  </div>
</template>

<style scoped>
.slide-captcha {
  position: relative;
  width: 100%;
  max-width: 310px;
  margin: 0 auto;
  user-select: none;
}

.slide-captcha--verifying {
  pointer-events: none;
  opacity: 0.7;
}

.slide-captcha__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 8px;
  font-size: 13px;
  color: #666;
  z-index: 10;
}

.slide-captcha__spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e0e0e0;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
