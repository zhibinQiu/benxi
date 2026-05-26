<script setup>
defineProps({
  message: { type: String, default: "正在启动知识服务系统" },
});
</script>

<template>
  <div class="ks-startup" role="status" aria-live="polite">
    <div class="ks-startup__visual" aria-hidden="true">
      <div class="ks-startup__orbit">
        <span class="ks-startup__dot ks-startup__dot--1" />
        <span class="ks-startup__dot ks-startup__dot--2" />
        <span class="ks-startup__dot ks-startup__dot--3" />
      </div>
      <div class="ks-startup__core">
        <svg viewBox="0 0 48 48" class="ks-startup__icon">
          <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" stroke-width="2" opacity="0.2" />
          <path
            d="M24 8v8M24 32v8M8 24h8M32 24h8"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
          />
          <circle cx="24" cy="24" r="6" fill="currentColor" opacity="0.85" />
        </svg>
      </div>
    </div>
    <p class="ks-startup__text">
      {{ message }}
      <span class="ks-startup__ellipsis" aria-hidden="true">
        <span /><span /><span />
      </span>
    </p>
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
  gap: 20px;
  padding: 28px 36px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow:
    0 4px 24px rgba(13, 148, 136, 0.12),
    0 2px 8px rgba(15, 23, 42, 0.06);
  animation: ks-startup-fade-in 0.35s ease-out;
}

@keyframes ks-startup-fade-in {
  from {
    opacity: 0;
    transform: translate(-50%, -48%);
  }
  to {
    opacity: 1;
    transform: translate(-50%, -50%);
  }
}

.ks-startup__visual {
  position: relative;
  width: 72px;
  height: 72px;
}

.ks-startup__orbit {
  position: absolute;
  inset: 0;
  animation: ks-orbit-spin 2.4s linear infinite;
}

@keyframes ks-orbit-spin {
  to {
    transform: rotate(360deg);
  }
}

.ks-startup__dot {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #0d9488;
  box-shadow: 0 0 8px rgba(13, 148, 136, 0.45);
}

.ks-startup__dot--1 {
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  animation: ks-dot-pulse-top 1.2s ease-in-out infinite;
}

.ks-startup__dot--2 {
  bottom: 8px;
  left: 4px;
  animation: ks-dot-pulse 1.2s ease-in-out 0.2s infinite;
}

.ks-startup__dot--3 {
  bottom: 8px;
  right: 4px;
  animation: ks-dot-pulse 1.2s ease-in-out 0.4s infinite;
}

@keyframes ks-dot-pulse {
  0%,
  100% {
    transform: scale(0.75);
    opacity: 0.5;
  }
  50% {
    transform: scale(1.15);
    opacity: 1;
  }
}

@keyframes ks-dot-pulse-top {
  0%,
  100% {
    transform: translateX(-50%) scale(0.75);
    opacity: 0.5;
  }
  50% {
    transform: translateX(-50%) scale(1.15);
    opacity: 1;
  }
}

.ks-startup__core {
  position: absolute;
  inset: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0d9488;
  animation: ks-core-breathe 2s ease-in-out infinite;
}

@keyframes ks-core-breathe {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.9;
  }
  50% {
    transform: scale(1.06);
    opacity: 1;
  }
}

.ks-startup__icon {
  width: 44px;
  height: 44px;
}

.ks-startup__text {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  color: #334155;
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  gap: 2px;
}

.ks-startup__ellipsis {
  display: inline-flex;
  align-items: flex-end;
  gap: 3px;
  height: 1em;
  margin-left: 2px;
}

.ks-startup__ellipsis span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #0d9488;
  animation: ks-ellipsis-bounce 1.1s ease-in-out infinite;
}

.ks-startup__ellipsis span:nth-child(2) {
  animation-delay: 0.15s;
}

.ks-startup__ellipsis span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes ks-ellipsis-bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.35;
  }
  40% {
    transform: translateY(-5px);
    opacity: 1;
  }
}
</style>
