<script setup>
import { useI18n } from "../composables/useI18n.js";

const { t } = useI18n();
</script>

<template>
  <p class="chat-disclaimer">{{ t("chat.disclaimer") }}</p>
</template>

<style scoped>
.chat-disclaimer {
  width: 100%;
  margin: 0;
  padding: 2px 4px 0;
  font-size: 12px;
  line-height: 1.45;
  text-align: center;
  color: var(--platform-text-tertiary);
}
</style>
