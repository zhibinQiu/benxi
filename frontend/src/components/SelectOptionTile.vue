<script setup>
defineProps({
  active: { type: Boolean, default: false },
  title: { type: String, required: true },
  desc: { type: String, default: "" },
  icon: { type: [Object, Function], default: null },
  iconSize: { type: Number, default: 14 },
});

defineEmits(["select"]);
</script>

<template>
  <button
    type="button"
    class="select-option-tile"
    :class="{ 'select-option-tile--active': active }"
    @click="$emit('select')"
  >
    <span v-if="icon" class="select-option-tile__icon">
      <n-icon :size="iconSize" :component="icon" />
    </span>
    <span class="select-option-tile__body">
      <span class="select-option-tile__title">{{ title }}</span>
      <span v-if="desc" class="select-option-tile__desc">{{ desc }}</span>
    </span>
  </button>
</template>

<style scoped>
.select-option-tile {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-elevated-solid, #fff);
  cursor: pointer;
  text-align: left;
  color: inherit;
  font: inherit;
}
.select-option-tile:hover,
.select-option-tile--active {
  border-color: var(--platform-accent);
  background: var(--platform-accent-soft);
}
.select-option-tile__icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}
.select-option-tile--active .select-option-tile__icon {
  color: var(--platform-bg-elevated-solid, #fff);
  background: var(--platform-accent);
}
.select-option-tile__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.select-option-tile__title {
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.3;
}
.select-option-tile__desc {
  font-size: 11px;
  color: var(--platform-text-tertiary);
  line-height: 1.3;
}
</style>
