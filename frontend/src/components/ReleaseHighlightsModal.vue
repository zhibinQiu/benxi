<script setup>
import { computed } from "vue";
import { NButton } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import { useI18n } from "../composables/useI18n";

const show = defineModel("show", { type: Boolean, default: false });

const props = defineProps({
  highlights: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(["acknowledge"]);

const { t } = useI18n();

const modalTitle = computed(() => t("releaseHighlights.title"));
const modalSubtitle = computed(() => {
  const data = props.highlights;
  if (!data?.version) return "";
  const subtitle = String(data.subtitle || "").trim();
  return subtitle ? `v${data.version} — ${subtitle}` : `v${data.version}`;
});

const features = computed(() => props.highlights?.features || []);
const fixes = computed(() => props.highlights?.fixes || []);

function onAcknowledge() {
  emit("acknowledge");
  show.value = false;
}
</script>

<template>
  <AdminFormModal
    v-model:show="show"
    :title="modalTitle"
    :subtitle="modalSubtitle"
    width="min(560px, calc(100vw - 32px))"
  >
    <div class="release-highlights">
      <section v-if="features.length" class="release-highlights__section">
        <h4 class="release-highlights__heading">{{ t("releaseHighlights.features") }}</h4>
        <ul class="release-highlights__list">
          <li v-for="item in features" :key="`f-${item.title}`" class="release-highlights__item">
            <span class="release-highlights__item-title">{{ item.title }}</span>
            <span v-if="item.summary" class="release-highlights__item-summary">{{ item.summary }}</span>
          </li>
        </ul>
      </section>

      <section v-if="fixes.length" class="release-highlights__section">
        <h4 class="release-highlights__heading">{{ t("releaseHighlights.fixes") }}</h4>
        <ul class="release-highlights__list">
          <li v-for="item in fixes" :key="`x-${item.title}`" class="release-highlights__item">
            <span class="release-highlights__item-title">{{ item.title }}</span>
            <span v-if="item.summary" class="release-highlights__item-summary">{{ item.summary }}</span>
          </li>
        </ul>
      </section>
    </div>

    <template #footer>
      <n-button type="primary" @click="onAcknowledge">
        {{ t("releaseHighlights.acknowledge") }}
      </n-button>
    </template>
  </AdminFormModal>
</template>

<style scoped>
.release-highlights {
  display: flex;
  flex-direction: column;
  gap: 22px;
  max-height: min(58vh, 504px);
  overflow: auto;
  padding-right: 2px;
}

.release-highlights__section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.release-highlights__heading {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--platform-text);
}

.release-highlights__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.release-highlights__item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--platform-ui-glass-fill-subtle, var(--platform-bg-glass-subtle));
  border: 1px solid var(--platform-ui-glass-border, var(--platform-border));
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--liquid-edge-highlight, #fff) 48%, transparent);
  backdrop-filter: saturate(165%) blur(12px);
  -webkit-backdrop-filter: saturate(165%) blur(12px);
}

.release-highlights__item-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--platform-text);
}

.release-highlights__item-summary {
  font-size: 16px;
  line-height: 1.55;
  color: var(--platform-text-muted);
}
</style>
