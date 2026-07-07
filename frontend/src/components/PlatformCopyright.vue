<script setup>
import { platformCopyrightText } from "../constants/platform";

defineProps({
  compact: { type: Boolean, default: false },
});

const emit = defineEmits(["coffeeClick"]);

function onCoffeeClick() {
  emit("coffeeClick");
}
</script>

<template>
  <div
    class="platform-copyright"
    :class="{ 'platform-copyright--compact': compact }"
  >
    <p class="coffee-invite" @click="onCoffeeClick">☕ 请开发者喝咖啡～</p>
    <p :title="platformCopyrightText()">{{ platformCopyrightText() }}</p>
  </div>
</template>

<style scoped>
.platform-copyright {
  margin: 0;
  padding: 12px 17px 14px;
  text-align: center;
  color: var(--platform-text-quaternary);
  word-break: break-word;
}

.platform-copyright p {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
}

.platform-copyright .coffee-invite {
  margin-bottom: 4px;
  font-size: 13px;
  line-height: 1.45;
  cursor: pointer;
  transition: color 0.2s;
}

.platform-copyright .coffee-invite:hover {
  color: var(--platform-text-tertiary);
}

.platform-copyright--compact {
  padding: 7px 10px 10px;
}

.platform-copyright--compact p {
  font-size: 12px;
  line-height: 1.35;
}

.platform-copyright--compact .coffee-invite {
  margin-bottom: 3px;
  font-size: 12px;
  line-height: 1.35;
}
</style>
