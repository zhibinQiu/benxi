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
  padding: 12px 17px 14px;
  font-size: 13px;
  line-height: 1.45;
  text-align: center;
  color: var(--platform-text-quaternary);
  word-break: break-word;
}

.platform-copyright--compact {
  padding: 7px 10px 10px;
  font-size: 12px;
  line-height: 1.35;
}
</style>
