<script setup>
import { computed } from "vue";
import { NButton, NDropdown, NIcon } from "naive-ui";
import { ArrowRedoOutline, ArrowUndoOutline, ChevronDownOutline } from "@vicons/ionicons5";
import { useI18n } from "../../composables/useI18n";
import { PLATFORM_Z } from "../../constants/zIndex.js";
import IconAction from "../IconAction.vue";
import ListRefreshButton from "../ListRefreshButton.vue";

const props = defineProps({
  graphDepth: { type: Number, default: 1 },
  extractingKnowledge: { type: Boolean, default: false },
  extractingPlatform: { type: Boolean, default: false },
  canUndo: { type: Boolean, default: false },
  canRedo: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:graphDepth",
  "create-entity",
  "create-relation",
  "extract",
  "refresh",
  "undo",
  "redo",
]);

const { t } = useI18n();

const extractLoading = computed(() => props.extractingKnowledge || props.extractingPlatform);

function depthLabel(hops) {
  return hops === 1 ? t("kgPalantir.subgraph1Hop") : t("kgPalantir.subgraph2Hop");
}

const viewMenuOptions = computed(() => [
  {
    label: t("kgPalantir.viewSubgraphScope"),
    key: "view-scope",
    children: [1, 2].map((hops) => ({
      label: depthLabel(hops),
      key: `depth:${hops}`,
      props:
        props.graphDepth === hops
          ? { class: "kg-toolbar-dropdown-option--active" }
          : undefined,
    })),
  },
]);

const extractMenuOptions = computed(() => [
  {
    label: t("kgPalantir.extractKnowledge"),
    key: "extract:knowledge",
    disabled: extractLoading.value,
  },
  {
    label: t("kgPalantir.extractPlatform"),
    key: "extract:platform",
    disabled: extractLoading.value,
  },
]);

const createMenuOptions = computed(() => [
  { label: t("kgPalantir.createEntity"), key: "create:entity" },
  { label: t("kgPalantir.addRelation"), key: "create:relation" },
]);

function onViewSelect(key) {
  const match = String(key).match(/^depth:(\d+)$/);
  if (match) {
    emit("update:graphDepth", Number(match[1]));
  }
}

function onExtractSelect(key) {
  if (key === "extract:knowledge") emit("extract", "knowledge");
  if (key === "extract:platform") emit("extract", "platform");
}

function onCreateSelect(key) {
  if (key === "create:entity") emit("create-entity");
  if (key === "create:relation") emit("create-relation");
}
</script>

<template>
  <div class="kg-toolbar">
    <div class="kg-toolbar__menus">
      <n-dropdown
        trigger="click"
        placement="bottom-start"
        to="body"
        :z-index="PLATFORM_Z.dropdown"
        :options="viewMenuOptions"
        @select="onViewSelect"
      >
        <n-button size="small" quaternary class="kg-toolbar__menu-btn">
          {{ t("kgPalantir.toolbarView") }}
          <n-icon :size="17" :component="ChevronDownOutline" class="kg-toolbar__chevron" />
        </n-button>
      </n-dropdown>

      <n-dropdown
        trigger="click"
        placement="bottom-start"
        to="body"
        :z-index="PLATFORM_Z.dropdown"
        :options="extractMenuOptions"
        @select="onExtractSelect"
      >
        <n-button
          size="small"
          quaternary
          class="kg-toolbar__menu-btn"
          :loading="extractLoading"
        >
          {{ t("kgPalantir.toolbarExtract") }}
          <n-icon :size="17" :component="ChevronDownOutline" class="kg-toolbar__chevron" />
        </n-button>
      </n-dropdown>

      <n-dropdown
        trigger="click"
        placement="bottom-start"
        to="body"
        :z-index="PLATFORM_Z.dropdown"
        :options="createMenuOptions"
        @select="onCreateSelect"
      >
        <n-button size="small" quaternary class="kg-toolbar__menu-btn">
          {{ t("kgPalantir.toolbarCreate") }}
          <n-icon :size="17" :component="ChevronDownOutline" class="kg-toolbar__chevron" />
        </n-button>
      </n-dropdown>
    </div>

    <div class="kg-toolbar__actions">
      <IconAction
        class="kg-toolbar__history-btn"
        size="small"
        :icon="ArrowUndoOutline"
        :label="t('kgPalantir.undo')"
        :tooltip="t('kgPalantir.undoTooltip')"
        :disabled="!canUndo"
        @click="emit('undo')"
      />
      <IconAction
        class="kg-toolbar__history-btn"
        size="small"
        :icon="ArrowRedoOutline"
        :label="t('kgPalantir.redo')"
        :tooltip="t('kgPalantir.redoTooltip')"
        :disabled="!canRedo"
        @click="emit('redo')"
      />
      <ListRefreshButton class="kg-toolbar__refresh" @click="emit('refresh')" />
    </div>
  </div>
</template>

<style scoped>
.kg-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
  min-width: 0;
}

.kg-toolbar__menus {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  min-width: 0;
}

.kg-toolbar__menu-btn {
  color: var(--platform-accent) !important;
}

.kg-toolbar__menu-btn:not(.n-button--disabled):hover {
  color: var(--platform-accent-hover, var(--platform-accent)) !important;
  background: var(--platform-accent-soft) !important;
}

.kg-toolbar__menu-btn :deep(.n-button__content) {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.kg-toolbar__chevron {
  opacity: 0.72;
  margin-left: 1px;
}

.kg-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  margin-left: auto;
}

.kg-toolbar__refresh {
  flex-shrink: 0;
}

.kg-toolbar__actions :deep(.kg-toolbar__history-btn .icon-action.icon-action--theme:not(.n-button--disabled)) {
  color: var(--platform-accent);
}

.kg-toolbar__actions :deep(.kg-toolbar__history-btn .icon-action.icon-action--theme:not(.n-button--disabled):hover) {
  color: var(--platform-accent-hover, var(--platform-accent));
  background: var(--platform-accent-soft) !important;
}
</style>

<style>
.kg-toolbar-dropdown-option--active .n-dropdown-option-body__label {
  color: var(--platform-accent);
  font-weight: 600;
}
</style>
