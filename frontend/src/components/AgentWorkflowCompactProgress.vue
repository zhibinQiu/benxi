<script setup>
import { computed } from "vue";
import RoseLoader from "./RoseLoader.vue";

const props = defineProps({
  workflow: { type: Object, default: null },
});

const running = computed(() => props.workflow?.running ?? false);
const summary = computed(() => {
  const s = props.workflow?.summary || "";
  // 运行时 summary 为空则显示默认提示
  if (!s && running.value) return "";
  return s;
});

const visible = computed(() => {
  if (!props.workflow) return false;
  if (running.value) return true;
  if (props.workflow.failed) return true;
  return Boolean(summary.value);
});
</script>

<template>
  <div v-if="visible" class="aw-c" role="status" aria-live="polite">
    <div class="aw-c__row">
      <RoseLoader v-if="running" class="aw-c__loader" :size="24" :rotation-duration="12000" />
      <span v-else class="aw-c__check" aria-hidden="true">&#x2713;</span>
      <span class="aw-c__text" :class="{ 'aw-c__text--running': running }">
        {{ summary || '执行中' }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.aw-c {
  margin-bottom: 12px;
  font-size: 13px;
}

.aw-c__row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  line-height: 1.5;
}

.aw-c__loader {
  flex-shrink: 0;
  margin-top: -2px;
  line-height: 0;
}

.aw-c__check {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  color: var(--platform-accent);
}

.aw-c__text {
  flex: 1;
  min-width: 0;
  word-break: break-word;
  color: var(--platform-text-secondary, #64748b);
}

.aw-c__text--running {
  color: var(--platform-text, #0f172a);
}
</style>
