<script setup>
import { computed } from "vue";
import { useI18n } from "../../composables/useI18n";

const props = defineProps({
  meta: { type: Object, default: null },
  typeColor: { type: Function, required: true },
});

const { t } = useI18n();

const topTypes = computed(() =>
  [...(props.meta?.entity_types || [])]
    .filter((item) => item.entity_count > 0)
    .sort((a, b) => b.entity_count - a.entity_count)
    .slice(0, 4)
);
</script>

<template>
  <div class="kg-stats">
    <div class="kg-stats__card kg-stats__card--primary">
      <span class="kg-stats__label">{{ t("kgPalantir.stats.entities") }}</span>
      <strong class="kg-stats__value">{{ meta?.entity_total ?? 0 }}</strong>
    </div>
    <div class="kg-stats__card">
      <span class="kg-stats__label">{{ t("kgPalantir.stats.relations") }}</span>
      <strong class="kg-stats__value">{{ meta?.relation_total ?? 0 }}</strong>
    </div>
    <div v-if="topTypes.length" class="kg-stats__types">
      <span
        v-for="item in topTypes"
        :key="item.id"
        class="kg-stats__chip"
      >
        <span class="kg-stats__chip-dot" :style="{ background: typeColor(item.color) }" />
        {{ item.label }}
        <em>{{ item.entity_count }}</em>
      </span>
    </div>
  </div>
</template>

<style scoped>
.kg-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 12px 12px 10px;
  border-bottom: 1px solid var(--platform-border);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--platform-bg-elevated) 92%, transparent),
    var(--platform-bg-secondary)
  );
}

.kg-stats__card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 72px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
}

.kg-stats__card--primary {
  border-color: color-mix(in srgb, var(--platform-primary) 35%, var(--platform-border));
  background: color-mix(in srgb, var(--platform-primary) 8%, var(--platform-bg-elevated));
}

.kg-stats__label {
  font-size: 11px;
  color: var(--platform-text-tertiary);
  letter-spacing: 0.02em;
}

.kg-stats__value {
  font-size: 20px;
  font-weight: 650;
  line-height: 1.1;
  color: var(--platform-text-primary);
  font-variant-numeric: tabular-nums;
}

.kg-stats__types {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.kg-stats__chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--platform-text-secondary);
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
}

.kg-stats__chip em {
  font-style: normal;
  font-weight: 600;
  color: var(--platform-text-primary);
}

.kg-stats__chip-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
