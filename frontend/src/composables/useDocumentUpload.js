import { computed, ref } from "vue";
import { ORG_SCOPES } from "../constants/documentScope";
import {
  DOCUMENT_UPLOAD_MAX_FILES,
  getDocumentUploadMaxMb,
  titleFromFileName,
  validateUploadFiles,
} from "../constants/documentUpload.js";
import {
  completeUpload,
  createDocument,
  deleteDocument,
  prepareUpload,
  uploadDocumentBlob,
} from "../api/documents.js";
import { isRouteAbortError } from "../api/requestScope.js";
import { notifyKnowledgeScopeTreeStale } from "../utils/knowledgeScopeRefresh.js";

export const VIRTUAL_UNCATEGORIZED = "__uncategorized__";

function formatUploadFileSize(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * 文档上传弹窗：单文件 / 批量上传的状态与提交逻辑。
 */
export function useDocumentUpload({
  folders,
  companies,
  departments,
  teams,
  activeScope,
  activeDeptId,
  activeOwnerId,
  activeKbFolderKey,
  isMainView,
  isSharedScopeTab,
  isSearchMode,
  isSystemAdmin,
  user,
  loadKbFolders,
  load,
  openDocumentDetail,
  ui,
  t,
}) {
  const showUploadModal = ref(false);
  const uploadMode = ref("single");
  const createScope = ref("personal");
  const createDeptId = ref(null);
  const createOwnerId = ref(null);
  const createFolderId = ref(VIRTUAL_UNCATEGORIZED);
  const uploadFile = ref(null);
  const creating = ref(false);

  const batchUploadFiles = ref([]);
  const batchUploadFileList = ref([]);
  const batchUploading = ref(false);
  const batchProgress = ref({ done: 0, total: 0 });
  const batchUploadKey = ref(0);

  const uploadMaxMb = computed(() => getDocumentUploadMaxMb());

  const batchUploadStats = computed(() => {
    const files = batchUploadFiles.value;
    return {
      count: files.length,
      totalSize: files.reduce((sum, file) => sum + (Number(file?.size) || 0), 0),
    };
  });

  const hasAnyCreatableScope = computed(() =>
    folders.value.some((f) => f.can_create && f.scope !== "all" && f.scope !== "shared")
  );

  const canSubmitUploadLocation = computed(() => {
    const scopeFolder = folders.value.find((f) => f.scope === createScope.value);
    if (!scopeFolder?.can_create) return false;
    if (ORG_SCOPES.includes(createScope.value) && !createDeptId.value) return false;
    return Boolean(createFolderId.value);
  });

  const canSubmitSingleUpload = computed(
    () =>
      Boolean(uploadFile.value) &&
      !creating.value &&
      !batchUploading.value &&
      canSubmitUploadLocation.value
  );

  function orgUnitsForScope(scope) {
    if (scope === "company") return companies.value;
    if (scope === "team") return teams.value;
    if (scope === "department") return departments.value;
    return [];
  }

  function initUploadLocation() {
    const scope = folders.value.find(
      (f) => f.scope === activeScope.value && f.can_create
    )
      ? activeScope.value
      : folders.value.find((f) => f.can_create)?.scope || "personal";
    createScope.value = scope;
    createDeptId.value = ORG_SCOPES.includes(scope)
      ? (activeScope.value === scope ? activeDeptId.value : null) ||
        orgUnitsForScope(scope)[0]?.id ||
        null
      : null;
    createOwnerId.value =
      scope === "personal" && isSystemAdmin.value
        ? (activeScope.value === "personal" ? activeOwnerId.value : null) ||
          user.value?.id ||
          null
        : null;
    const sameContext = activeScope.value === scope;
    createFolderId.value =
      sameContext && activeKbFolderKey.value
        ? activeKbFolderKey.value
        : VIRTUAL_UNCATEGORIZED;
  }

  function validateUploadLocation() {
    const scopeFolder = folders.value.find((f) => f.scope === createScope.value);
    if (!scopeFolder?.can_create) {
      return { ok: false, message: t("documents.messages.noDocPermission") };
    }
    if (ORG_SCOPES.includes(createScope.value) && !createDeptId.value) {
      return { ok: false, message: t("validation.selectDepartment") };
    }
    if (!createFolderId.value) {
      return { ok: false, message: t("documents.messages.selectUploadFolder") };
    }
    return { ok: true };
  }

  function buildCreatePayload(title, description = "") {
    const payload = {
      title,
      description: description || "",
      scope: createScope.value,
    };
    if (ORG_SCOPES.includes(createScope.value) && createDeptId.value) {
      payload.dept_id = createDeptId.value;
    }
    if (
      createFolderId.value &&
      createFolderId.value !== VIRTUAL_UNCATEGORIZED
    ) {
      payload.folder_id = createFolderId.value;
    }
    return payload;
  }

  async function uploadFileToDocument(docId, file) {
    const prep = await prepareUpload(
      docId,
      file.name,
      file.type || "application/octet-stream"
    );
    await uploadDocumentBlob(prep.upload_url, file);
    await completeUpload(docId, {
      version_id: prep.version_id,
      file_size: file.size,
    });
  }

  function onSingleFileDropChange(e) {
    const file = e.target?.files?.[0] ?? null;
    if (!file) return;
    const check = validateUploadFiles([file], { maxFiles: 1 });
    if (!check.ok) {
      ui.warning(check.message);
      return;
    }
    uploadFile.value = file;
  }

  function clearBatchUploadSelection() {
    batchUploadFiles.value = [];
    batchUploadFileList.value = [];
    batchUploadKey.value += 1;
  }

  function onBatchFileChange(opts) {
    let fileList = opts.fileList;
    const files = fileList.map((f) => f.file).filter(Boolean);
    const check = validateUploadFiles(files);
    if (!check.ok) {
      ui.warning(check.message);
      if (files.length > DOCUMENT_UPLOAD_MAX_FILES) {
        fileList = fileList.slice(0, DOCUMENT_UPLOAD_MAX_FILES);
      }
      batchUploadFileList.value = fileList;
      batchUploadFiles.value = fileList.map((f) => f.file).filter(Boolean);
      return;
    }
    batchUploadFileList.value = fileList;
    batchUploadFiles.value = check.files;
  }

  function ensureCanCreateDocuments() {
    if (
      !isMainView.value ||
      activeScope.value === "all" ||
      isSharedScopeTab.value ||
      isSearchMode.value
    ) {
      ui.warning("documents.messages.enterKbFolder");
      return false;
    }
    if (!hasAnyCreatableScope.value) {
      ui.warning("documents.messages.noDocPermission");
      return false;
    }
    initUploadLocation();
    return true;
  }

  function onUploadLocationFoldersChanged() {
    if (
      activeScope.value === createScope.value &&
      (!ORG_SCOPES.includes(createScope.value) ||
        String(activeDeptId.value) === String(createDeptId.value))
    ) {
      void loadKbFolders({ force: true });
    }
  }

  function openUploadModal(mode = "single") {
    if (!ensureCanCreateDocuments()) return;
    uploadMode.value = mode;
    uploadFile.value = null;
    batchUploadFiles.value = [];
    batchUploadFileList.value = [];
    batchUploadKey.value += 1;
    batchProgress.value = { done: 0, total: 0 };
    showUploadModal.value = true;
  }

  function closeUploadModal() {
    if (batchUploading.value || creating.value) return;
    showUploadModal.value = false;
  }

  async function submitCreate() {
    if (!uploadFile.value) {
      ui.warning("validation.selectFile");
      return;
    }
    const check = validateUploadFiles([uploadFile.value], { maxFiles: 1 });
    if (!check.ok) {
      ui.warning(check.message);
      return;
    }
    const title = titleFromFileName(uploadFile.value.name) || uploadFile.value.name;
    if (!title) {
      ui.warning("validation.titleRequired");
      return;
    }
    const locCheck = validateUploadLocation();
    if (!locCheck.ok) {
      ui.warning(locCheck.message);
      return;
    }
    creating.value = true;
    let createdId = null;
    let uploadCompleted = false;
    try {
      const doc = await createDocument(buildCreatePayload(title, ""));
      createdId = doc.id;
      await uploadFileToDocument(doc.id, uploadFile.value);
      uploadCompleted = true;
      ui.success("documents.messages.docCreated");
      showUploadModal.value = false;
      uploadFile.value = null;
      notifyKnowledgeScopeTreeStale();
      await loadKbFolders({ force: true });
      await load({ force: true });
      openDocumentDetail(doc.id);
    } catch (e) {
      if (createdId && !uploadCompleted) {
        try {
          await deleteDocument(createdId);
        } catch {
          /* 忽略回滚失败 */
        }
      }
      if (!isRouteAbortError(e)) {
        ui.error(e);
      }
    } finally {
      creating.value = false;
    }
  }

  async function submitBatchUpload() {
    const check = validateUploadFiles(batchUploadFiles.value);
    if (!check.ok) {
      ui.warning(check.message);
      return;
    }
    const locCheck = validateUploadLocation();
    if (!locCheck.ok) {
      ui.warning(locCheck.message);
      return;
    }
    batchUploading.value = true;
    batchProgress.value = { done: 0, total: check.files.length };
    const failed = [];
    let success = 0;
    try {
      for (const file of check.files) {
        let createdId = null;
        try {
          const title = titleFromFileName(file.name) || file.name;
          const doc = await createDocument(buildCreatePayload(title, ""));
          createdId = doc.id;
          await uploadFileToDocument(doc.id, file);
          success += 1;
        } catch (e) {
          failed.push({ name: file.name, reason: e.message });
          if (createdId) {
            try {
              await deleteDocument(createdId);
            } catch {
              /* 忽略回滚失败 */
            }
          }
        } finally {
          batchProgress.value = {
            done: batchProgress.value.done + 1,
            total: check.files.length,
          };
        }
      }
      if (success && !failed.length) {
        ui.success("documents.messages.batchUploadSuccess", { count: success });
        showUploadModal.value = false;
        batchUploadFiles.value = [];
      } else if (success) {
        ui.warning("documents.messages.batchUploadPartial", {
          success,
          failed: failed.length,
          names: failed.map((f) => f.name).join("、"),
        });
      } else {
        ui.error("documents.messages.batchUploadFailed");
      }
      await loadKbFolders({ force: true });
      await load({ force: true });
      if (success) notifyKnowledgeScopeTreeStale();
    } finally {
      batchUploading.value = false;
    }
  }

  return {
    showUploadModal,
    uploadMode,
    createScope,
    createDeptId,
    createOwnerId,
    createFolderId,
    uploadFile,
    creating,
    batchUploadFiles,
    batchUploadFileList,
    batchUploading,
    batchProgress,
    batchUploadKey,
    uploadMaxMb,
    batchUploadStats,
    hasAnyCreatableScope,
    canSubmitUploadLocation,
    canSubmitSingleUpload,
    formatUploadFileSize,
    openUploadModal,
    closeUploadModal,
    onSingleFileDropChange,
    clearBatchUploadSelection,
    onBatchFileChange,
    onUploadLocationFoldersChanged,
    submitCreate,
    submitBatchUpload,
  };
}
