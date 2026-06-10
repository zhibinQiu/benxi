<script setup>
import { computed } from "vue";
import { splitPlatformBrandTitle } from "../constants/platform";

defineOptions({ inheritAttrs: false });

const props = defineProps({
  title: { type: String, default: "" },
  tag: { type: String, default: "span" },
  strong: { type: Boolean, default: false },
});

const parts = computed(() => splitPlatformBrandTitle(props.title));
</script>

<template>
  <component
    :is="tag"
    v-bind="$attrs"
    class="platform-brand-title"
    :class="{ 'platform-brand-title--strong': strong }"
  >
    <template v-if="parts.highlight">
      <span v-if="parts.prefix" class="platform-brand-title__plain">{{ parts.prefix }}</span
      ><span class="platform-text-gradient">{{ parts.highlight }}</span
      ><span v-if="parts.suffix" class="platform-brand-title__plain">{{ parts.suffix }}</span>
    </template>
    <span v-else class="platform-brand-title__plain">{{ title }}</span>
  </component>
</template>

<style scoped>
.platform-brand-title {
  display: inline;
  line-height: inherit;
}

.platform-brand-title--strong {
  font-weight: 600;
}

.platform-brand-title__plain {
  color: var(--platform-text);
}
</style>
