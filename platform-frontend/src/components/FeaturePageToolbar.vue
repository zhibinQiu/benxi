<script setup>
import FeatureSubsystemHeader from "./FeatureSubsystemHeader.vue";

defineProps({
  description: { type: String, default: "" },
  showIntro: { type: Boolean, default: false }});
</script>

<template>
  <FeatureSubsystemHeader :description="description" :show-intro="showIntro">
    <template v-if="$slots.default" #extra>
      <slot />
    </template>
  </FeatureSubsystemHeader>
</template>
