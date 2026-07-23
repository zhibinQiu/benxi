<script setup>
import { ref, watch } from "vue";
import { ChevronDownOutline } from "@vicons/ionicons5";

const props = defineProps({
  title: { type: String, default: "" },
  /** 侧栏等紧凑内边距 */
  dense: { type: Boolean, default: false },
  /** 可点击标题折叠/展开内容 */
  collapsible: { type: Boolean, default: false },
  /** 可折叠时是否默认展开 */
  defaultExpanded: { type: Boolean, default: true },
});

const expanded = ref(props.defaultExpanded);

watch(
  () => props.defaultExpanded,
  (v) => {
    if (props.collapsible) expanded.value = v;
  }
);

function toggle() {
  if (!props.collapsible) return;
  expanded.value = !expanded.value;
}
</script>

<template>
  <section class="feature-section" :class="{ 'feature-section--collapsed': collapsible && !expanded }">
    <header
      v-if="title || $slots.title || $slots.extra"
      class="feature-section__header"
      :class="{ 'feature-section__header--clickable': collapsible }"
      @click="toggle"
    >
      <n-icon
        v-if="collapsible"
        class="feature-section__chevron"
        :class="{ 'feature-section__chevron--open': expanded }"
        :component="ChevronDownOutline"
        :size="14"
      />
      <div class="feature-section__title">
        <slot name="title">{{ title }}</slot>
      </div>
      <div v-if="$slots.extra" class="feature-section__extra" @click.stop>
        <slot name="extra" />
      </div>
    </header>
    <div
      v-show="!collapsible || expanded"
      class="feature-section__card"
      :class="{ 'feature-section__card--dense': dense }"
    >
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
.feature-section__header--clickable {
  cursor: pointer;
  user-select: none;
  border-radius: 4px;
  padding: 2px var(--fs-1);
  margin-left: 0;
}
.feature-section__header--clickable:hover {
  background: var(--platform-bg-secondary, rgba(0, 0, 0, 0.03));
}
.feature-section--collapsed .feature-section__header {
  margin-bottom: 0;
}
.feature-section__chevron {
  flex-shrink: 0;
  color: var(--platform-text-tertiary);
  transition: transform 0.15s ease;
  transform: rotate(-90deg);
}
.feature-section__chevron--open {
  transform: rotate(0deg);
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
