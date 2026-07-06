<script setup>
import { useI18n } from "../composables/useI18n.js";
import { useRouter } from "vue-router";

defineProps({
  started: { type: Boolean, default: false },
});

const { t } = useI18n();
const router = useRouter();

function goAgentkitDocs() {
  router.push({ name: "agentkit-docs" });
}
</script>

<template>
  <p v-if="!started" class="chat-disclaimer">
    {{ t("chat.disclaimer") }}
  </p>
  <p v-else class="chat-disclaimer">
    {{ t("chat.disclaimerArch") }}
    <a class="agentkit-link" @click.prevent="goAgentkitDocs" href="/agentkit-docs">AgentKit</a>
  </p>
</template>

<style scoped>
.chat-disclaimer {
  width: 100%;
  margin: 0;
  padding: 2px 5px 0;
  font-size: 11px;
  line-height: 1.4;
  text-align: center;
  color: var(--platform-text-tertiary);
}

.agentkit-link {
  color: var(--platform-primary);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 1px;
}

.agentkit-link:hover {
  opacity: 0.8;
}
</style>
