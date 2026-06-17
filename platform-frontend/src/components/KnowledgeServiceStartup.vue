<script setup>
defineProps({
  message: { type: String, default: "正在启动知识服务系统" },
});
</script>

<template>
  <div class="ks-startup" role="status" aria-live="polite">
    <n-spin size="large" />
    <p class="ks-startup__text">{{ message }}</p>
  </div>
</template>

<style scoped>
.ks-startup {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 2;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 22px 28px;
  border-radius: var(--platform-radius-lg, 12px);
  background: var(--platform-bg-glass-strong);
  border: 1px solid var(--platform-glass-border);
  box-shadow: var(--platform-ui-layer-shadow, var(--platform-shadow-sm));
  backdrop-filter: blur(var(--platform-glass-blur, 22px)) saturate(var(--platform-glass-saturate, 185%));
  -webkit-backdrop-filter: blur(var(--platform-glass-blur, 22px))
    saturate(var(--platform-glass-saturate, 185%));
  animation: ks-startup-in 0.22s var(--platform-ease-smooth, ease-out);
}

@keyframes ks-startup-in {
  from {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
}

.ks-startup__text {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--platform-text-secondary);
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .ks-startup {
    animation: none;
  }
}
</style>
