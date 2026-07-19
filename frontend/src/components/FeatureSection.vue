<script setup>
defineProps({
  title: { type: String, default: "" },
  /** 侧栏等紧凑内边距 */
  dense: { type: Boolean, default: false },
});
</script>

<template>
  <section class="feature-section">
    <header v-if="title || $slots.title || $slots.extra" class="feature-section__header">
      <div class="feature-section__title">
        <slot name="title">{{ title }}</slot>
      </div>
      <div v-if="$slots.extra" class="feature-section__extra">
        <slot name="extra" />
      </div>
    </header>
    <div class="feature-section__card" :class="{ 'feature-section__card--dense': dense }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.feature-section {
  --fs-1: 4px;
  --fs-2: 8px;
  --fs-3: 12px;
  --fs-4: 16px;
  display: flex;
  flex-direction: column;
}
.feature-section__header {
  display: flex;
  align-items: center;
  gap: var(--fs-2);
  margin: 0 0 var(--fs-1);
  padding-left: var(--fs-1);
}
.feature-section__title {
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.4;
}
.feature-section__extra {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--fs-2);
}
.feature-section__card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: var(--platform-card-bg, #fcfcfc);
  padding: var(--fs-3) var(--fs-4);
  display: flex;
  flex-direction: column;
  gap: var(--fs-3);
}
.feature-section__card--dense {
  padding: var(--fs-3);
  gap: var(--fs-2);
}
</style>
