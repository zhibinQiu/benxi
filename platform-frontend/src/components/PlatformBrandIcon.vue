<script setup>
import { publicAsset } from "../utils/appBase";

defineProps({
  size: {
    type: Number,
    default: 22,
  },
});
</script>

<template>
  <img
    class="platform-brand-icon"
    :src="publicAsset('icon.svg')"
    alt=""
    :width="size"
    :height="size"
    decoding="async"
  />
</template>

<style scoped>
.platform-brand-icon {
  display: block;
  flex-shrink: 0;
  object-fit: contain;
}
</style>
