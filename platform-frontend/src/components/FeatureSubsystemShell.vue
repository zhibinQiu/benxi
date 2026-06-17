<script setup>
import { nextTick, onMounted, ref } from "vue";
import FeatureSubsystemHeader from "./FeatureSubsystemHeader.vue";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";

defineProps({
  description: { type: String, default: "" },
  fill: { type: Boolean, default: false },
  showIntro: { type: Boolean, default: false },
  /** 与全局顶栏配合：默认不在页面内重复标题/返回 */
  hideTitleRow: { type: Boolean, default: true },
  /** 内容区左侧贴齐主布局（如知识检索文档树贴侧栏） */
  flushStart: { type: Boolean, default: false },
  /** 内容区右侧贴齐主布局窗口 */
  flushEnd: { type: Boolean, default: false },
});

const { headerExtensionActive } = usePageHeaderExtension();
const teleportReady = ref(false);

onMounted(() => {
  nextTick(() => {
    teleportReady.value = true;
  });
});
</script>

<template>
  <div
    class="subsystem-shell feature-page"
    :class="{
      'subsystem-shell--fill': fill,
      'feature-page--fill': fill,
      'subsystem-shell--flush-start': flushStart,
      'subsystem-shell--flush-end': flushEnd,
    }"
  >
    <Teleport
      v-if="$slots.extra && teleportReady && headerExtensionActive"
      to="#page-header-extension"
    >
      <div class="subsystem-extra-bar">
        <div class="subsystem-extra-row">
          <slot name="extra" />
        </div>
      </div>
    </Teleport>

    <FeatureSubsystemHeader
      :description="description"
      :show-intro="showIntro"
      :hide-title-row="hideTitleRow"
    />

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

.subsystem-shell--fill .subsystem-body {
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
  box-sizing: border-box;
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
