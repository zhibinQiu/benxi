<script setup>
defineProps({
  message: { type: String, default: "正在启动知识服务系统" },
});
</script>

<template>
  <div class="ks-startup" role="status" aria-live="polite">
    <span class="ks-startup__spinner" aria-hidden="true" />
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
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06);
  animation: ks-startup-in 0.18s ease-out;
}

@keyframes ks-startup-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.ks-startup__spinner {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(13, 148, 136, 0.18);
  border-top-color: #0d9488;
  border-radius: 50%;
  animation: ks-startup-spin 0.65s linear infinite;
}

@keyframes ks-startup-spin {
  to {
    transform: rotate(360deg);
  }
}

.ks-startup__text {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .ks-startup {
    animation: none;
  }

  .ks-startup__spinner {
    animation: none;
    border-top-color: rgba(13, 148, 136, 0.35);
  }
}
</style>
