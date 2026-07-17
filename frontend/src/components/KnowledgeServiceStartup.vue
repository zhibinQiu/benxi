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
  gap: 17px;
  padding: 26px 34px;
  border-radius: var(--platform-radius-lg, 14px);
  background: var(--platform-bg-elevated);
  border: 1px solid var(--platform-border);
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
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
  font-size: 16px;
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
