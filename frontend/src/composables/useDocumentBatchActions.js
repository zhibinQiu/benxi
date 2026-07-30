import { computed, ref } from "vue";
import { ORG_SCOPES } from "../constants/documentScope";
import { batchDeleteDocuments } from "../api/documents.js";
import {
  canBatchSelectDocument,
  canDeleteDocument,
  canModifyDocument,
} from "../utils/documentCaps.js";
import {
  clearDocumentsViewCache,
} from "../utils/documentsViewCache.js";
import { notifyKnowledgeScopeTreeStale } from "../utils/knowledgeScopeRefresh.js";
import { useBatchTableSelection } from "./useBatchTableSelection.js";

/**
 * 文档列表批量选择、移动、发布与删除。
 */
export function useDocumentBatchActions({
  items,
  total,
  showBatchDocActions,
  canShowMoveInList,
  canShowDeleteInList,
  isMainView,
  activeScope,
  activeDeptId,
  load,
  loadKbFolders,
  invalidateDocumentLibrary,
  ui,
  t,
}) {
  const showMoveDoc = ref(false);
  const moveDocTarget = ref(null);
  const batchMoveDocIds = ref([]);

  const showPublishDoc = ref(false);
  const publishDocIds = ref([]);

  const {
    checkedRowKeys,
    selectedRows,
    onCheckedRowKeysChange,
    clearSelection,
  } = useBatchTableSelection(items, { canSelect: canBatchSelectDocument });

  const deletableSelectedRows = computed(() =>
    selectedRows.value.filter((row) => canDeleteDocument(row))
  );

  const canBatchMove = computed(
    () =>
      showBatchDocActions.value &&
      canShowMoveInList.value &&
      selectedRows.value.length > 0 &&
      selectedRows.value.every((row) => canModifyDocument(row))
  );

  const canBatchPublish = computed(
    () =>
      showBatchDocActions.value &&
      selectedRows.value.length > 0 &&
      selectedRows.value.every((row) => canModifyDocument(row))
  );

  const canBatchDelete = computed(
    () =>
      showBatchDocActions.value &&
      canShowDeleteInList.value &&
      deletableSelectedRows.value.length > 0
  );

  const moveFolderScope = computed(() => {
    if (!moveDocTarget.value) return "";
    if (isMainView.value && activeScope.value !== "all") {
      return activeScope.value;
    }
    return moveDocTarget.value.scope || "personal";
  });

  const moveFolderDeptId = computed(() => {
    if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
      return activeDeptId.value;
    }
    return moveDocTarget.value?.dept_id ?? null;
  });

  function onIconCardSelected(row, checked) {
    if (!canBatchSelectDocument(row)) return;
    const id = row.id;
    if (checked) {
      if (!checkedRowKeys.value.includes(id)) {
        checkedRowKeys.value = [...checkedRowKeys.value, id];
      }
    } else {
      checkedRowKeys.value = checkedRowKeys.value.filter((k) => k !== id);
    }
  }

  async function handleBatchDelete() {
    const rows = deletableSelectedRows.value;
    if (!rows.length) return;
    const skipped = selectedRows.value.length - rows.length;
    ui.confirmDelete({
      title: t("common.batchDelete"),
      content:
        skipped > 0
          ? t("documents.confirm.deleteBatchPartial", {
              count: rows.length,
              skipped,
            })
          : t("documents.confirm.deleteBatch", { count: rows.length }),
      onPositive: async () => {
        const res = await batchDeleteDocuments(rows.map((row) => row.id));
        const count = res.deleted_count ?? res.deleted?.length ?? 0;
        const failed = res.failed || [];
        if (failed.length) {
          ui.warning("messages.batchDeletedPartial", {
            success: count,
            failed: failed.length,
          });
        } else {
          ui.success("documents.messages.deletedBatch", { count });
        }
        clearSelection();
        const deletedIds = new Set(res.deleted || []);
        if (deletedIds.size) {
          items.value = items.value.filter((row) => !deletedIds.has(row.id));
          total.value = Math.max(0, total.value - deletedIds.size);
          clearDocumentsViewCache();
          invalidateDocumentLibrary();
          notifyKnowledgeScopeTreeStale();
        }
        void loadKbFolders({ force: true });
        void load({ force: true, background: true });
      },
    });
  }

  function openBatchMove() {
    if (!canBatchMove.value) return;
    batchMoveDocIds.value = selectedRows.value.map((row) => row.id);
    moveDocTarget.value = selectedRows.value[0] || null;
    showMoveDoc.value = true;
  }

  function openBatchPublish() {
    if (!canBatchPublish.value) return;
    publishDocIds.value = selectedRows.value.map((row) => row.id);
    showPublishDoc.value = true;
  }

  function onDocumentPublished() {
    showPublishDoc.value = false;
    publishDocIds.value = [];
    clearSelection();
  }

  function onDocumentMoved() {
    showMoveDoc.value = false;
    moveDocTarget.value = null;
    batchMoveDocIds.value = [];
    clearSelection();
    loadKbFolders({ force: true });
    load({ force: true });
  }

  return {
    checkedRowKeys,
    selectedRows,
    deletableSelectedRows,
    canBatchMove,
    canBatchPublish,
    canBatchDelete,
    showMoveDoc,
    moveDocTarget,
    batchMoveDocIds,
    moveFolderScope,
    moveFolderDeptId,
    showPublishDoc,
    publishDocIds,
    onCheckedRowKeysChange,
    clearSelection,
    onIconCardSelected,
    handleBatchDelete,
    openBatchMove,
    openBatchPublish,
    onDocumentPublished,
    onDocumentMoved,
  };
}
