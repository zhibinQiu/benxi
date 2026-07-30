<script setup>
import { NButton, NCard, NDataTable, NEmpty, NSpace } from "naive-ui";
import {
  ArrowBackOutline,
  GridOutline,
  ListOutline,
  MoveOutline,
  RocketOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import BatchTableToolbar from "../BatchTableToolbar.vue";
import DocumentIconCard from "../DocumentIconCard.vue";
import IconAction from "../IconAction.vue";
import ListTableFooter from "../ListTableFooter.vue";
import PlatformSpin from "../PlatformSpin.vue";
import { useI18n } from "../../composables/useI18n";
import { canBatchSelectDocument } from "../../utils/documentCaps.js";

defineProps({
  isInsideKbFolder: { type: Boolean, default: false },
  activeKbFolderLabel: { type: String, default: "" },
  folderDocViewMode: { type: String, default: "list" },
  showTopFolderBatchActions: { type: Boolean, default: false },
  showBottomBatchToolbar: { type: Boolean, default: false },
  canBatchPublish: { type: Boolean, default: false },
  canBatchMove: { type: Boolean, default: false },
  canBatchDelete: { type: Boolean, default: false },
  showFolderIconView: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  items: { type: Array, default: () => [] },
  showBatchDocActions: { type: Boolean, default: false },
  checkedRowKeys: { type: Array, default: () => [] },
  deletableSelectedCount: { type: Number, default: 0 },
  columns: { type: Array, default: () => [] },
  documentRowProps: { type: Function, default: () => ({}) },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 6 },
  total: { type: Number, default: 0 },
});

const emit = defineEmits([
  "back-to-folders",
  "set-view-mode",
  "batch-publish",
  "batch-move",
  "batch-delete",
  "update:checked-row-keys",
  "icon-card-selected",
  "open-document",
  "update:page",
]);

const { t } = useI18n();
</script>

<template>
  <div class="documents-list-panel">
    <div v-if="isInsideKbFolder" class="documents-folder-toolbar">
      <IconAction
        :label="t('documents.backToFolders')"
        :icon="ArrowBackOutline"
        @click="emit('back-to-folders')"
      />
      <span class="documents-folder-toolbar__name">{{ activeKbFolderLabel }}</span>
      <div class="folder-view-toggle" role="group" :aria-label="t('documents.viewModeLabel')">
        <IconAction
          :label="t('documents.viewList')"
          :icon="ListOutline"
          :active="folderDocViewMode === 'list'"
          @click="emit('set-view-mode', 'list')"
        />
        <IconAction
          :label="t('documents.viewIcons')"
          :icon="GridOutline"
          :active="folderDocViewMode === 'icons'"
          @click="emit('set-view-mode', 'icons')"
        />
      </div>
      <div v-if="showTopFolderBatchActions" class="folder-action-pills">
        <NButton
          text
          size="tiny"
          class="folder-action-btn"
          :disabled="!canBatchPublish"
          @click="emit('batch-publish')"
        >
          {{ t("documents.detail.publish") }}
        </NButton>
        <NButton
          text
          size="tiny"
          class="folder-action-btn"
          :disabled="!canBatchMove"
          @click="emit('batch-move')"
        >
          {{ t("common.move") }}
        </NButton>
        <NButton
          text
          size="tiny"
          class="folder-action-btn folder-action-btn--danger"
          :disabled="!canBatchDelete"
          @click="emit('batch-delete')"
        >
          {{ t("common.delete") }}
        </NButton>
      </div>
    </div>

    <div v-if="showBottomBatchToolbar" class="doc-list-toolbar page-toolbar">
      <n-space align="center" :size="7">
        <IconAction
          :label="t('documents.detail.publish')"
          :icon="RocketOutline"
          :disabled="!canBatchPublish"
          @click="emit('batch-publish')"
        />
        <IconAction
          :label="t('common.move')"
          :icon="MoveOutline"
          :disabled="!canBatchMove"
          @click="emit('batch-move')"
        />
        <BatchTableToolbar
          :count="deletableSelectedCount || checkedRowKeys.length"
          :disabled="!canBatchDelete"
          :icon="TrashOutline"
          action-type="warning"
          @action="emit('batch-delete')"
        />
      </n-space>
    </div>

    <PlatformSpin
      v-if="showFolderIconView"
      :show="loading && !items.length"
      class="documents-view-spin"
      local
    >
      <n-empty v-if="!items.length && !loading" :description="t('documents.emptyDocs')" />
      <div v-else class="kb-folder-explorer documents-icon-explorer">
        <div
          v-for="(row, docIdx) in items"
          :key="row.id"
          class="kb-folder-explorer__cell"
          :style="{ '--folder-i': docIdx }"
        >
          <DocumentIconCard
            :document="row"
            :selectable="showBatchDocActions"
            :selected="checkedRowKeys.includes(row.id)"
            :select-disabled="!canBatchSelectDocument(row)"
            @open="(doc) => emit('open-document', doc.id)"
            @update:selected="(v) => emit('icon-card-selected', row, v)"
          />
        </div>
      </div>
    </PlatformSpin>

    <n-card v-else class="documents-list-card" :bordered="true">
      <PlatformSpin :show="loading && !items.length" class="documents-view-spin" local>
        <n-data-table
          class="documents-table"
          :columns="columns"
          :data="items"
          :row-key="(row) => row.id"
          :row-props="documentRowProps"
          :checked-row-keys="showBatchDocActions ? checkedRowKeys : undefined"
          @update:checked-row-keys="emit('update:checked-row-keys', $event)"
          :pagination="false"
        />
      </PlatformSpin>
    </n-card>

    <ListTableFooter
      :page="page"
      :page-size="pageSize"
      :item-count="total"
      @update:page="emit('update:page', $event)"
    />
  </div>
</template>

<style scoped>
.folder-action-pills {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.documents-folder-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.documents-folder-toolbar__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--platform-font-size-lg);
  font-weight: 500;
  color: var(--platform-text);
  letter-spacing: -0.01em;
}

.folder-view-toggle {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.documents-folder-toolbar .folder-action-btn.n-button {
  width: auto !important;
  padding: 0 6px !important;
  font-size: var(--platform-font-size-xs) !important;
  line-height: 1.2 !important;
  --n-height: 22px;
  font-weight: 400;
  color: var(--platform-text-secondary);
}
.documents-folder-toolbar .folder-action-btn.n-button:not(:disabled):hover {
  color: var(--platform-accent);
}
.documents-folder-toolbar .folder-action-btn--danger.n-button:not(:disabled) {
  color: var(--platform-danger);
}
.documents-folder-toolbar .folder-action-btn--danger.n-button:not(:disabled):hover {
  color: var(--platform-danger);
  opacity: 0.85;
}

.documents-doc-title {
  font-size: 15px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.documents-table :deep(.documents-meta-tag) {
  font-size: var(--platform-font-size-xs) !important;
}

.documents-table :deep(.n-data-table-thead .n-data-table-th) {
  font-size: 15px !important;
  font-weight: 500 !important;
  color: var(--platform-text) !important;
  border-bottom: 1px solid var(--platform-border-light) !important;
}
.documents-table :deep(.n-data-table-tbody .n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-light) !important;
  font-size: 13px;
}

.documents-folder-toolbar .folder-action-pills {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  flex-shrink: 0;
}
.documents-folder-toolbar .folder-action-pills::-webkit-scrollbar {
  display: none;
}

@media (max-width: 768px) {
  .documents-list-card :deep(.n-card__content) {
    padding: 8px 4px !important;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .documents-table :deep(.n-data-table-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    min-width: auto;
  }

  .documents-table :deep(.n-data-table-th):nth-child(3),
  .documents-table :deep(.n-data-table-td):nth-child(3),
  .documents-table :deep(.n-data-table-th):nth-child(4),
  .documents-table :deep(.n-data-table-td):nth-child(4) {
    display: none;
  }

  .documents-table :deep(.n-data-table-th):nth-child(7),
  .documents-table :deep(.n-data-table-td):nth-child(7),
  .documents-table :deep(.n-data-table-th):nth-child(8),
  .documents-table :deep(.n-data-table-td):nth-child(8) {
    display: none;
  }

  .documents-doc-title {
    font-size: 13px !important;
    max-width: 36vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: block;
  }

  .kb-folder-explorer {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)) !important;
    gap: 10px;
    padding: 8px 0 16px;
  }
  .kb-folder-explorer__cell {
    max-width: 100%;
  }
  .kb-folder-explorer__cell > * {
    max-width: 100%;
  }

  .documents-folder-toolbar {
    gap: 6px;
    margin-bottom: 6px;
    flex-wrap: wrap;
  }
  .documents-folder-toolbar__name {
    font-size: 14px;
    min-width: 0;
    max-width: 40vw;
  }
  .folder-view-toggle {
    order: 3;
  }

  .list-table-footer {
    padding: 10px;
  }

  .list-table-footer :deep(.n-pagination) {
    gap: 2px;
  }
  .list-table-footer :deep(.n-pagination .n-pagination-item) {
    min-width: 28px;
    height: 28px;
    font-size: 12px;
  }
}

@media (max-width: 400px) {
  .kb-folder-explorer {
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 8px;
    padding: 6px 0 12px;
  }

  .documents-folder-toolbar .folder-action-btn.n-button {
    font-size: var(--platform-font-size-xs) !important;
    padding: 0 4px !important;
  }

  .documents-table :deep(.n-data-table-th):nth-child(5),
  .documents-table :deep(.n-data-table-td):nth-child(5),
  .documents-table :deep(.n-data-table-th):nth-child(6),
  .documents-table :deep(.n-data-table-td):nth-child(6) {
    display: none;
  }
}
</style>
