<script setup>
import { computed, useSlots } from "vue";
import { useRoute } from "vue-router";
import { getFeatureDescription } from "../constants/featureDescriptions";

const props = defineProps({
  description: { type: String, default: "" },
  showIntro: { type: Boolean, default: true },
  /** 标题与返回已放在全局顶栏时，本区仅保留说明与操作 */
  hideTitleRow: { type: Boolean, default: true },
});

const route = useRoute();
const slots = useSlots();

const introText = computed(
  () => props.description || getFeatureDescription(route.name) || ""
);

const showIntroBlock = computed(() => props.showIntro && Boolean(introText.value));

const showHeader = computed(
  () => !props.hideTitleRow || showIntroBlock.value || Boolean(slots.extra)
);
</script>

<template>
  <header v-if="showHeader" class="subsystem-header">
    <div v-if="$slots.extra" class="subsystem-extra-row">
      <slot name="extra" />
    </div>
    <p v-if="showIntroBlock" class="subsystem-desc">{{ introText }}</p>
  </header>
</template>

<style scoped>
.subsystem-header {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
}

.subsystem-extra-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.subsystem-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--platform-muted, #64748b);
}
</style>
