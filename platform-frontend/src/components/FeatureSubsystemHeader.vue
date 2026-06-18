<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "../composables/useI18n";
import HintTooltip from "./HintTooltip.vue";

const props = defineProps({
  description: { type: String, default: "" },
  showIntro: { type: Boolean, default: false },
  /** 标题与返回已放在全局顶栏时，本区仅保留说明 */
  hideTitleRow: { type: Boolean, default: true },
});

const route = useRoute();
const { featureDescription } = useI18n();

const introText = computed(
  () => props.description || featureDescription(String(route.name || "")) || ""
);

const showIntroBlock = computed(() => props.showIntro && Boolean(introText.value));

const showHeader = computed(() => !props.hideTitleRow || showIntroBlock.value);
</script>

<template>
  <header v-if="showHeader" class="subsystem-header feature-local-nav">
    <div v-if="showIntroBlock" class="subsystem-extra-row">
      <HintTooltip :text="introText" />
    </div>
  </header>
</template>

<style scoped>
.subsystem-header {
  flex-shrink: 0;
}

.subsystem-extra-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
