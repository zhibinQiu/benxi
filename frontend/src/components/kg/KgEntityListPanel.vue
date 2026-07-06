<script setup>
import { computed } from "vue";
import {
  NButton,
  NCheckbox,
  NEmpty,
  NInput,
  NPagination,
  NSelect,
  NSpace,
} from "naive-ui";
import PlatformSpin from "../PlatformSpin.vue";
import { useI18n } from "../../composables/useI18n";

const props = defineProps({
  meta: { type: Object, default: null },
  entityList: { type: Array, default: () => [] },
  paginatedEntityList: { type: Array, default: () => [] },
  listLoading: { type: Boolean, default: false },
  searchQ: { type: String, default: "" },
  filterTypeId: { type: [String, null], default: null },
  selectedId: { type: [String, null], default: null },
  checkedIds: { type: Array, default: () => [] },
  entityPage: { type: Number, default: 1 },
  entityPageCount: { type: Number, default: 1 },
  typeFilterOptions: { type: Array, default: () => [] },
  typeColor: { type: Function, required: true },
  idEq: { type: Function, required: true },
});

const emit = defineEmits([
  "update:searchQ",
  "update:filterTypeId",
  "update:entityPage",
  "update:checkedIds",
  "select",
  "delete-checked",
  "delete-search-results",
  "clear-graph",
]);

const { t } = useI18n();

const pageIds = computed(() => props.paginatedEntityList.map((item) => String(item.id)));

const allPageChecked = computed({
  get() {
    return pageIds.value.length > 0 && pageIds.value.every((id) => props.checkedIds.includes(id));
  },
  set(checked) {
    if (checked) {
      const merged = new Set([...props.checkedIds, ...pageIds.value]);
      emit("update:checkedIds", [...merged]);
      return;
    }
    const pageSet = new Set(pageIds.value);
    emit(
      "update:checkedIds",
      props.checkedIds.filter((id) => !pageSet.has(String(id)))
    );
  },
});

const hasSearchFilter = computed(
  () => Boolean(props.searchQ.trim()) || Boolean(props.filterTypeId)
);

const checkedCount = computed(() => props.checkedIds.length);

function toggleRow(id, checked) {
  const sid = String(id);
  if (checked) {
    if (!props.checkedIds.includes(sid)) {
      emit("update:checkedIds", [...props.checkedIds, sid]);
    }
    return;
  }
  emit(
    "update:checkedIds",
    props.checkedIds.filter((item) => item !== sid)
  );
}

function isRowChecked(id) {
  return props.checkedIds.includes(String(id));
}
</script>

<template>
  <div class="kg-entity-panel">
    <div class="kg-entity-panel__search">
      <n-input
        :value="searchQ"
        size="small"
        :placeholder="t('kgPalantir.searchPlaceholder')"
        clearable
        @update:value="emit('update:searchQ', $event)"
      />
      <n-select
        :value="filterTypeId"
        size="small"
        :options="typeFilterOptions"
        class="kg-entity-panel__type"
        @update:value="emit('update:filterTypeId', $event)"
      />
    </div>

    <div class="kg-entity-panel__meta">
      <span>
        {{ t("kgPalantir.entityTotal", { count: meta?.entity_total || 0 }) }}
        <template v-if="searchQ.trim() || filterTypeId">
          · {{ t("kgPalantir.searchResults", { count: entityList.length }) }}
        </template>
      </span>
      <label v-if="paginatedEntityList.length" class="kg-entity-panel__select-all">
        <n-checkbox v-model:checked="allPageChecked" size="small" />
        <span>{{ t("kgPalantir.selectPage") }}</span>
      </label>
    </div>

    <div v-if="checkedCount || hasSearchFilter" class="kg-entity-panel__batch">
      <n-space size="small" wrap>
        <n-button
          v-if="checkedCount"
          size="tiny"
          type="error"
          secondary
          @click="emit('delete-checked')"
        >
          {{ t("kgPalantir.deleteSelected", { count: checkedCount }) }}
        </n-button>
        <n-button
          v-if="hasSearchFilter && entityList.length"
          size="tiny"
          type="error"
          quaternary
          @click="emit('delete-search-results')"
        >
          {{ t("kgPalantir.deleteSearchResults", { count: entityList.length }) }}
        </n-button>
        <n-button size="tiny" quaternary @click="emit('clear-graph')">
          {{ t("kgPalantir.clearGraph") }}
        </n-button>
      </n-space>
    </div>

    <PlatformSpin :show="listLoading" class="kg-entity-panel__spin platform-local-spin" local size="small">
      <div v-if="entityList.length" class="kg-entity-panel__list-wrap">
        <div class="kg-entity-panel__list">
          <div
            v-for="item in paginatedEntityList"
            :key="item.id"
            class="kg-entity-row-wrap"
            :class="{ 'is-active': idEq(selectedId, item.id) }"
          >
            <n-checkbox
              class="kg-entity-row-wrap__check"
              :checked="isRowChecked(item.id)"
              size="small"
              @update:checked="(v) => toggleRow(item.id, v)"
              @click.stop
            />
            <button
              type="button"
              class="kg-glass-item kg-entity-row"
              @click="emit('select', item.id)"
            >
              <span
                class="kg-entity-row__dot"
                :style="{ background: typeColor(item.type_color) }"
              />
              <span class="kg-entity-row__body">
                <span class="kg-entity-row__name">{{ item.name }}</span>
                <span class="kg-entity-row__type">{{ item.type_label }}</span>
              </span>
            </button>
          </div>
        </div>
        <div v-if="entityPageCount > 1" class="kg-entity-panel__pagination">
          <n-pagination
            :page="entityPage"
            :page-count="entityPageCount"
            size="small"
            :page-slot="5"
            @update:page="emit('update:entityPage', $event)"
          />
        </div>
      </div>
      <n-empty
        v-else
        size="small"
        :description="t('kgPalantir.noMatchingEntities')"
        class="kg-entity-panel__empty"
      />
    </PlatformSpin>
  </div>
</template>

<style scoped>
.kg-entity-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.kg-entity-panel__search {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 14px 12px;
}

.kg-entity-panel__type {
  width: 100%;
}

.kg-entity-panel__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 14px 10px;
  font-size: 13px;
  color: var(--platform-text-tertiary);
}

.kg-entity-panel :deep(.n-input__input-el),
.kg-entity-panel :deep(.n-input__placeholder),
.kg-entity-panel :deep(.n-base-selection-input),
.kg-entity-panel :deep(.n-base-selection-placeholder) {
  font-size: 14px !important;
}

.kg-entity-panel__select-all {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  user-select: none;
  color: var(--platform-text-secondary);
}

.kg-entity-panel__batch {
  padding: 0 14px 12px;
}

.kg-entity-panel__spin {
  flex: 1;
  min-height: 0;
}

.kg-entity-panel__spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-entity-panel__list-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-entity-panel__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 10px 10px;
}

.kg-entity-panel__pagination {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  padding: 10px 14px 14px;
  border-top: 1px solid var(--platform-border);
}

.kg-entity-panel__empty {
  padding: 29px 14px;
}

.kg-entity-row-wrap {
  display: flex;
  align-items: stretch;
  gap: 5px;
  margin-bottom: 7px;
}

.kg-entity-row-wrap.is-active .kg-entity-row {
  border-color: color-mix(in srgb, var(--platform-accent) 45%, var(--platform-border));
  background: color-mix(in srgb, var(--platform-accent) 10%, var(--platform-bg-elevated));
}

.kg-entity-row-wrap__check {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding-left: 5px;
}

.kg-entity-row {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid transparent;
  background: color-mix(in srgb, var(--platform-bg-elevated) 70%, transparent);
  transition: border-color 0.15s ease, background 0.15s ease;
}

.kg-entity-row:hover {
  border-color: var(--platform-border);
  background: var(--platform-bg-elevated);
}

.kg-entity-row__dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 12%, transparent);
}

.kg-entity-row__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.kg-entity-row__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--platform-text-primary);
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.kg-entity-row__type {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}
</style>
