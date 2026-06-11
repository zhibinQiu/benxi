<script setup>
import FeatureSubsystemHeader from "./FeatureSubsystemHeader.vue";

defineProps({
  description: { type: String, default: "" },
  fill: { type: Boolean, default: false },
  showIntro: { type: Boolean, default: false },
  /** 与全局顶栏配合：默认不在页面内重复标题/返回 */
  hideTitleRow: { type: Boolean, default: true }});
</script>

<template>
  <div
    class="subsystem-shell feature-page"
    :class="{ 'subsystem-shell--fill': fill, 'feature-page--fill': fill }"
  >
    <FeatureSubsystemHeader
      :description="description"
      :show-intro="showIntro"
      :hide-title-row="hideTitleRow"
    >
      <template v-if="$slots.extra" #extra>
        <slot name="extra" />
      </template>
    </FeatureSubsystemHeader>
    <div class="subsystem-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.subsystem-shell {
  display: flex;
  flex-direction: column;
  width: 100%;
  box-sizing: border-box;
}

.subsystem-shell--fill {
  flex: 1;
  min-height: 0;
}

.subsystem-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.subsystem-shell:not(.subsystem-shell--fill) .subsystem-body {
  flex: none;
}

.subsystem-body > :deep(.ai-home) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
}
</style>
