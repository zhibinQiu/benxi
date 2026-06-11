<script setup>
import { platformCopyrightText } from "../constants/platform";

defineProps({
  compact: { type: Boolean, default: false }});
</script>

<template>
  <p
    class="platform-copyright"
    :class="{ 'platform-copyright--compact': compact }"
    :title="platformCopyrightText()"
  >
    {{ platformCopyrightText() }}
  </p>
</template>

<style scoped>
.platform-copyright {
  margin: 0;
  padding: 10px 14px 12px;
  font-size: 11px;
  line-height: 1.45;
  text-align: center;
  color: var(--platform-text-quaternary);
  word-break: break-word;
}

.platform-copyright--compact {
  padding: 6px 8px 8px;
  font-size: 10px;
  line-height: 1.35;
}
</style>
