<script setup>
import { computed, h, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NCard,
  NButton,
  NSpace,
  NDataTable,
  NInput,
  NModal,
  NForm,
  NFormItem,
  NUpload,
  NTabs,
  NTabPane,
  NSelect,
  NTag,
  NPopconfirm,
  NEmpty,
  NProgress,
  NText,
  NTooltip,
  NIcon,
  NDropdown,
} from "naive-ui";
import {
  CreateOutline,
  TrashOutline,
  TrashBinOutline,
  ArchiveOutline,
  MoveOutline,
  ArrowBackOutline,
  SearchOutline,
  ShareSocialOutline,
  CloudUploadOutline,
  EyeOutline,
  RefreshOutline,
} from "@vicons/ionicons5";
import MoveDocumentFolderModal from "../components/MoveDocumentFolderModal.vue";
import KbFolderCard from "../components/KbFolderCard.vue";
import KbFolderCreateCard from "../components/KbFolderCreateCard.vue";
import IconAction from "../components/IconAction.vue";
import BatchTableToolbar from "../components/BatchTableToolbar.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeader } from "../composables/usePageHeader";
import {
  ORG_SCOPES,
  LIBRARY_FOLDER_ORDER,
} from "../constants/documentScope";
import {
  DOCUMENT_UPLOAD_MAX_FILES,
  DOCUMENT_UPLOAD_MAX_MB,
  formatDocumentFormatLabel,
  titleFromFileName,
  validateUploadFiles,
} from "../constants/documentUpload";
import { renderIconAction, renderIconActionGroup } from "../utils/tableIconActions";
import {
  createDocument,
  createKbFolder,
  deleteKbFolder,
  fetchDocumentLibrary,
  fetchDocuments,
  fetchKbFolders,
  fetchRecycleDocuments,
  fetchMySharedDocuments,
  prepareUpload,
  completeUpload,
  restoreDocument,
  batchDeleteDocuments,
  permanentlyDeleteDocument,
  emptyRecycleBin,
  updateKbFolder,
} from "../api/client";

const route = useRoute();
const { isSystemAdmin } = useAuth();
const router = useRouter();
const { t, scopeLabel, locale } = useI18n();
const ui = usePlatformUi();
const { setHeaderTitle, clearHeaderTitle } = usePageHeader();

const loading = ref(false);
const keyword = ref("");
const appliedSearch = ref("");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const items = ref([]);
const folders = ref([]);
const activeScope = ref("personal");
/** null | __uncategorized__ | __shared__ | folder-uuid */
const activeKbFolderKey = ref(null);
const kbFolders = ref([]);
const kbCanManageFolders = ref(false);
const activeDeptId = ref(null);
/** main | recycle | my-shares */
const libraryView = ref("main");
const companies = ref([]);
const departments = ref([]);
const teams = ref([]);
/** 忽略过期的 load / loadKbFolders 结果，避免切换分级时串数据 */
let kbFoldersLoadSeq = 0;
let documentsLoadSeq = 0;

const orgUnits = computed(() => {
  if (activeScope.value === "company") return companies.value;
  if (activeScope.value === "team") return teams.value;
  if (activeScope.value === "department") return departments.value;
  return [];
});

const showOrgPicker = computed(
  () =>
    ORG_SCOPES.includes(activeScope.value) &&
    orgUnits.value.length > (isSystemAdmin.value ? 0 : 1)
);

const showCreateFolder = ref(false);
const createFolderName = ref("");
const createFolderDesc = ref("");
const savingFolder = ref(false);
const editFolderTarget = ref(null);
const editFolderName = ref("");
const editFolderDesc = ref("");

const showMoveDoc = ref(false);
const moveDocTarget = ref(null);
const batchMoveDocIds = ref([]);
const checkedRowKeys = ref([]);

const showUploadModal = ref(false);
const uploadMode = ref("batch");
const createTitle = ref("");
const createDesc = ref("");
const createScope = ref("personal");
const createDeptId = ref(null);
const uploadFile = ref(null);
const creating = ref(false);

const batchUploadFiles = ref([]);
const batchUploading = ref(false);
const batchProgress = ref({ done: 0, total: 0 });
const activeFolder = computed(() =>
  folders.value.find((f) => f.scope === activeScope.value)
);

const canCreateInActive = computed(() => activeFolder.value?.can_create ?? false);

const deptOptions = computed(() =>
  orgUnits.value.map((d) => ({ label: d.name, value: d.id }))
);

const scopeTagType = {
  company: "info",
  department: "warning",
  team: "success",
  personal: "default",
  shared: "success",
  all: "primary",
};

const VIRTUAL_UNCATEGORIZED = "__uncategorized__";
const VIRTUAL_SHARED = "__shared__";

function docStatusLabel(key) {
  const label = t(`documents.status.${key}`);
  return label === `documents.status.${key}` ? key : label;
}

function docLevelLabel(key) {
  const label = t(`documents.level.${key}`);
  return label === `documents.level.${key}` ? key : label;
}

const isMainView = computed(() => libraryView.value === "main");
const isRecycleView = computed(() => libraryView.value === "recycle");
const isMySharesView = computed(() => libraryView.value === "my-shares");
const isSearchMode = computed(
  () => isMainView.value && appliedSearch.value.trim().length > 0
);
const isSharedScopeTab = computed(
  () => isMainView.value && activeScope.value === "shared"
);
const usesKbFolders = computed(
  () =>
    isMainView.value &&
    activeScope.value !== "all" &&
    activeScope.value !== "shared"
);
const showKbFolderList = computed(
  () => usesKbFolders.value && !activeKbFolderKey.value && !isSearchMode.value
);
const isSharedFolderView = computed(
  () => activeKbFolderKey.value === VIRTUAL_SHARED
);
const isInsideKbFolder = computed(
  () =>
    isMainView.value &&
    usesKbFolders.value &&
    Boolean(activeKbFolderKey.value) &&
    !isSharedFolderView.value &&
    !isSearchMode.value
);
const activeKbFolder = computed(() =>
  kbFolders.value.find(
    (f) =>
      f.virtual_id === activeKbFolderKey.value ||
      (f.id && String(f.id) === activeKbFolderKey.value)
  )
);
const activeKbFolderLabel = computed(() => activeKbFolder.value?.name || "");
const canManageKbFolders = computed(
  () => kbCanManageFolders.value || activeFolder.value?.can_manage_folders
);

const canShowMoveInList = computed(
  () =>
    isMainView.value &&
    !isRecycleView.value &&
    !isMySharesView.value &&
    !isSharedFolderView.value &&
    !isSharedScopeTab.value &&
    activeScope.value !== "all"
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

const canShowDeleteInList = computed(
  () => isMainView.value && !isRecycleView.value && !isMySharesView.value
);

const showBatchDocActions = computed(
  () =>
    isMainView.value &&
    !isSearchMode.value &&
    !showKbFolderList.value &&
    !isSharedFolderView.value &&
    !isSharedScopeTab.value &&
    activeScope.value !== "all"
);

const showTopFolderBatchActions = computed(
  () => isInsideKbFolder.value && showBatchDocActions.value
);

const showFolderNavInActions = computed(
  () =>
    isMainView.value &&
    !isSearchMode.value &&
    Boolean(activeKbFolderKey.value) &&
    !showKbFolderList.value
);

const showBottomBatchToolbar = computed(
  () => showBatchDocActions.value && !showTopFolderBatchActions.value
);

const selectedRows = computed(() =>
  items.value.filter((row) => checkedRowKeys.value.includes(row.id))
);

const canBatchMove = computed(
  () =>
    showBatchDocActions.value &&
    canShowMoveInList.value &&
    selectedRows.value.length > 0 &&
    selectedRows.value.every((row) => row.can_edit)
);

const canBatchDelete = computed(
  () =>
    showBatchDocActions.value &&
    canShowDeleteInList.value &&
    selectedRows.value.length > 0 &&
    selectedRows.value.every((row) => row.can_delete)
);

watch(
  [isRecycleView, isMySharesView, locale],
  () => {
    if (isRecycleView.value) setHeaderTitle(t("documents.recycle"));
    else if (isMySharesView.value) setHeaderTitle(t("documents.myShares"));
    else clearHeaderTitle();
  },
  { immediate: true }
);

onUnmounted(clearHeaderTitle);

const columns = computed(() => {
  locale.value;
  const base = [];
  if (showBatchDocActions.value) {
    base.push({
      type: "selection",
      disabled: (row) => !row.can_edit && !row.can_delete,
    });
  }
  base.push({ title: t("documents.columns.title"), key: "title", ellipsis: { tooltip: true } });
  if (!isRecycleView.value) {
    base.push({
      title: t("documents.columns.format"),
      key: "file_format",
      width: 88,
      render: (row) =>
        row.file_format
          ? h(
              NTag,
              { size: "small", bordered: false, type: "info" },
              { default: () => formatDocumentFormatLabel(row.file_format) }
            )
          : "—",
    });
  }
  if (isRecycleView.value) {
    base.push(
      {
        title: t("documents.columns.status"),
        key: "status",
        width: 90,
        render: (row) => docStatusLabel(row.status) || row.status,
      },
      {
        title: t("documents.columns.originalScope"),
        key: "scope",
        width: 90,
        render: (row) => scopeLabel(row.scope) || row.scope,
      },
      {
        title: t("documents.columns.deletedAt"),
        key: "deleted_at",
        width: 180,
        render: (row) =>
          row.deleted_at ? new Date(row.deleted_at).toLocaleString() : "—",
      },
      {
        title: t("documents.columns.actions"),
        key: "actions",
        width: 72,
        render: (row) =>
          renderIconAction({
            label: t("common.restore"),
            icon: RefreshOutline,
            type: "primary",
            onClick: () => handleRestore(row.id),
          }),
      }
    );
    return base;
  }
  if (isMySharesView.value) {
    base.push(
      {
        title: t("documents.columns.scope"),
        key: "scope",
        width: 90,
        render: (row) => scopeLabel(row.scope) || row.scope,
      },
      {
        title: t("documents.columns.shareTo"),
        key: "share_to_summary",
        ellipsis: { tooltip: true },
        render: (row) => row.share_to_summary || "—",
      },
      {
        title: t("documents.columns.updatedAt"),
        key: "updated_at",
        width: 180,
        render: (row) => new Date(row.updated_at).toLocaleString(),
      },
      {
        title: t("documents.columns.actions"),
        key: "actions",
        width: 100,
        render: (row) =>
          h(
            NButton,
            {
              text: true,
              type: "primary",
              onClick: () =>
                openDocumentDetail(row.id),
            },
            { default: () => t("common.view") }
          ),
      }
    );
    return base;
  }
  if (!isSearchMode.value) {
    base.push({
      title: t("documents.columns.status"),
      key: "status",
      width: 90,
      render: (row) => docStatusLabel(row.status) || row.status,
    });
  }
  if (isSearchMode.value || activeScope.value === "all") {
    base.push(
      {
        title: t("documents.columns.scope"),
        key: "scope",
        width: 90,
        render: (row) => scopeLabel(row.scope) || row.scope,
      },
      {
        title: t("documents.columns.folder"),
        key: "folder_name",
        width: 120,
        ellipsis: { tooltip: true },
        render: (row) => row.folder_name || "—",
      },
      {
        title: t("documents.columns.owner"),
        key: "owner_name",
        width: 120,
        render: (row) => row.owner_name || "未知用户",
      },
      {
        title: t("documents.columns.dept"),
        key: "dept_name",
        width: 110,
        render: (row) =>
          ORG_SCOPES.includes(row.scope) ? row.dept_name || "—" : "—",
      },
      {
        title: t("documents.columns.myPermission"),
        key: "effective_level",
        width: 90,
        render: (row) => docLevelLabel(row.effective_level) || row.effective_level || "—",
      }
    );
  } else if (isSharedScopeTab.value || isSharedFolderView.value) {
    base.push(
      {
        title: t("documents.columns.sharer"),
        key: "owner_name",
        width: 120,
        render: (row) => row.owner_name || "未知用户",
      },
      {
        title: t("documents.columns.grantedBy"),
        key: "granted_by_name",
        width: 140,
        render: (row) => row.granted_by_name || "—",
      },
      {
        title: t("documents.columns.myPermission"),
        key: "shared_level",
        width: 90,
        render: (row) => docLevelLabel(row.shared_level) || row.shared_level || "—",
      }
    );
  } else if (ORG_SCOPES.includes(activeScope.value)) {
    base.push(
      {
        title:
          activeScope.value === "company"
            ? t("documents.columns.company")
            : activeScope.value === "team"
              ? t("documents.columns.team")
              : t("documents.columns.department"),
        key: "dept_name",
        width: 120,
        render: (row) => row.dept_name || "—",
      },
      {
        title: t("documents.columns.owner"),
        key: "owner_name",
        width: 140,
        render: (row) => row.owner_name || "未知用户",
      }
    );
  }
  base.push(
    {
      title: t("documents.columns.updatedAt"),
      key: "updated_at",
      width: 180,
      render: (row) => new Date(row.updated_at).toLocaleString(),
    },
    {
      title: t("documents.columns.actions"),
      key: "actions",
      width: 72,
      render: (row) =>
        renderIconAction({
          label: t("common.view"),
          icon: EyeOutline,
          type: "primary",
          onClick: () => openDocumentDetail(row.id),
        }),
    }
  );
  return base;
});

async function handleRestore(documentId) {
  try {
    await restoreDocument(documentId);
    ui.success("documents.messages.restored");
    await load();
  } catch (e) {
    ui.error(e);
  }
}

function confirmPurgeDocument(documentId, title, { fromRecycle = false } = {}) {
  ui.confirmDelete({
    title: fromRecycle ? t("common.permanentlyDelete") : t("common.delete"),
    content: fromRecycle
      ? t("documents.confirm.deletePermanent")
      : t("documents.confirm.deleteOne"),
    onPositive: async () => {
      await permanentlyDeleteDocument(documentId);
      ui.success(
        fromRecycle ? "documents.messages.deletedPermanent" : "documents.messages.deleted"
      );
      await load();
    },
  });
}

function handleDeleteDocument(documentId, title) {
  confirmPurgeDocument(documentId, title, { fromRecycle: false });
}

function onCheckedRowKeysChange(keys) {
  checkedRowKeys.value = keys;
}

function handleBatchDelete() {
  const rows = selectedRows.value;
  if (!rows.length) return;
  ui.confirmDelete({
    title: t("common.batchDelete"),
    content: t("documents.confirm.deleteBatch", { count: rows.length }),
    onPositive: async () => {
      const res = await batchDeleteDocuments(
        rows.map((row) => row.id),
        { permanent: false }
      );
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
      checkedRowKeys.value = [];
      await load();
    },
  });
}

function handlePermanentDelete(documentId, title) {
  confirmPurgeDocument(documentId, title, { fromRecycle: true });
}

async function confirmEmptyRecycle() {
  try {
    const res = await emptyRecycleBin();
    ui.success("documents.messages.recycleEmptied");
    page.value = 1;
    await load();
  } catch (e) {
    ui.error(e);
  }
}

function normalizeFolders(list) {
  const byScope = Object.fromEntries((list || []).map((f) => [f.scope, f]));
  return LIBRARY_FOLDER_ORDER.filter((s) => byScope[s]).map((s) => byScope[s]);
}

function resolveScopeFromRouteQuery() {
  const q = route.query.scope;
  if (typeof q === "string" && q && q !== "recycle") {
    return q;
  }
  const deptId = route.query.dept_id;
  if (
    deptId &&
    companies.value.some((c) => String(c.id) === String(deptId))
  ) {
    return "company";
  }
  return null;
}

function applyRouteFromQuery() {
  const view = route.query.view;
  if (view === "recycle" || route.query.scope === "recycle") {
    libraryView.value = "recycle";
    activeKbFolderKey.value = null;
    return;
  }
  if (view === "my-shares") {
    libraryView.value = "my-shares";
    activeKbFolderKey.value = null;
    return;
  }
  libraryView.value = "main";
  const resolvedScope = resolveScopeFromRouteQuery();
  if (resolvedScope === "shared") {
    activeScope.value = "personal";
    activeDeptId.value = null;
    const fk = route.query.folder;
    activeKbFolderKey.value =
      typeof fk === "string" && fk ? fk : VIRTUAL_SHARED;
    return;
  }
  if (resolvedScope) {
    activeScope.value = resolvedScope;
  }
  if (route.query.dept_id) {
    activeDeptId.value = route.query.dept_id;
  } else if (!ORG_SCOPES.includes(activeScope.value)) {
    activeDeptId.value = null;
  }
  const fk = route.query.folder;
  activeKbFolderKey.value =
    typeof fk === "string" && fk ? fk : null;
}

async function syncLegacySharedScopeRoute() {
  if (route.query.scope !== "shared" || libraryView.value !== "main") return;
  await router.replace({
    name: "documents",
    query: {
      scope: "personal",
      folder: activeKbFolderKey.value || VIRTUAL_SHARED,
    },
  });
}

async function loadFolders() {
  try {
    const lib = await fetchDocumentLibrary();
    folders.value = normalizeFolders(lib.folders);
    companies.value = lib.companies || [];
    departments.value = lib.departments || [];
    teams.value = lib.teams || [];
    const units = orgUnits.value;
    if (
      ORG_SCOPES.includes(activeScope.value) &&
      units.length &&
      !activeDeptId.value
    ) {
      activeDeptId.value = units[0].id;
    }
    applyRouteFromQuery();
    await syncLegacySharedScopeRoute();
    if (
      libraryView.value === "main" &&
      folders.value.length &&
      !folders.value.find((f) => f.scope === activeScope.value)
    ) {
      activeScope.value = folders.value[0].scope;
    }
  } catch (e) {
    ui.error(e);
  }
}

async function loadKbFolders() {
  const seq = ++kbFoldersLoadSeq;
  if (!usesKbFolders.value) {
    kbFolders.value = [];
    return;
  }
  try {
    const params = { scope: activeScope.value };
    if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
      params.dept_id = activeDeptId.value;
    }
    const data = await fetchKbFolders(params);
    if (seq !== kbFoldersLoadSeq) return;
    kbFolders.value = data.items || [];
    kbCanManageFolders.value = !!data.can_manage_folders;
  } catch (e) {
    if (seq !== kbFoldersLoadSeq) return;
    kbFolders.value = [];
    ui.error(e);
  }
}

function runSearch() {
  const q = keyword.value.trim();
  if (!q) {
    clearSearch();
    return;
  }
  appliedSearch.value = q;
  page.value = 1;
  load();
}

function clearSearch() {
  const hadSearch = appliedSearch.value.trim().length > 0;
  keyword.value = "";
  appliedSearch.value = "";
  page.value = 1;
  if (hadSearch && isMainView.value) load();
}

async function load() {
  const seq = ++documentsLoadSeq;
  loading.value = true;
  items.value = [];
  checkedRowKeys.value = [];
  try {
    if (isSearchMode.value) {
      const data = await fetchDocuments({
        page: page.value,
        page_size: pageSize.value,
        scope: "all",
        keyword: appliedSearch.value.trim(),
      });
      if (seq !== documentsLoadSeq) return;
      items.value = data.items || [];
      total.value = data.total ?? 0;
      return;
    }
    if (usesKbFolders.value && !activeKbFolderKey.value) {
      await loadKbFolders();
      if (seq !== documentsLoadSeq) return;
      total.value = 0;
      return;
    }
    const params = {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value.trim() || undefined,
    };
    let data;
    if (isRecycleView.value) {
      data = await fetchRecycleDocuments(params);
    } else if (isMySharesView.value) {
      data = await fetchMySharedDocuments(params);
    } else if (isSharedScopeTab.value || isSharedFolderView.value) {
      data = await fetchDocuments({ ...params, scope: "shared" });
    } else if (usesKbFolders.value && activeKbFolderKey.value) {
      const docParams = { ...params, scope: activeScope.value };
      if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
        docParams.dept_id = activeDeptId.value;
      }
      if (activeKbFolderKey.value === VIRTUAL_UNCATEGORIZED) {
        docParams.uncategorized = true;
      } else {
        docParams.folder_id = activeKbFolderKey.value;
      }
      data = await fetchDocuments(docParams);
    } else {
      const docParams = { ...params, scope: activeScope.value };
      if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
        docParams.dept_id = activeDeptId.value;
      }
      data = await fetchDocuments(docParams);
    }
    if (seq !== documentsLoadSeq) return;
    items.value = data.items || [];
    total.value = data.total ?? 0;
  } catch (e) {
    if (seq !== documentsLoadSeq) return;
    items.value = [];
    total.value = 0;
    ui.error(e);
  } finally {
    if (seq === documentsLoadSeq) {
      loading.value = false;
    }
  }
}

function onPageChange(p) {
  page.value = p;
  load();
}

function buildLibraryQuery() {
  const query = { scope: activeScope.value };
  if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
    query.dept_id = activeDeptId.value;
  }
  if (activeKbFolderKey.value) query.folder = activeKbFolderKey.value;
  return query;
}

function openDocumentDetail(id) {
  navigateWithReturn(
    router,
    { name: "document-detail", params: { id } },
    route
  );
}

async function onTabChange(scope) {
  clearSearch();
  activeScope.value = scope;
  activeKbFolderKey.value = null;
  page.value = 1;
  let units = [];
  if (scope === "company") units = companies.value;
  else if (scope === "team") units = teams.value;
  else if (scope === "department") units = departments.value;
  if (ORG_SCOPES.includes(scope) && units.length) {
    activeDeptId.value = units[0].id;
  } else {
    activeDeptId.value = null;
  }
  await router.replace({ name: "documents", query: buildLibraryQuery() });
  await loadKbFolders();
  await load();
}

function openKbFolder(folder) {
  const key = folder.virtual_id || (folder.id ? String(folder.id) : null);
  if (!key) return;
  keyword.value = "";
  appliedSearch.value = "";
  activeKbFolderKey.value = key;
  page.value = 1;
  router.replace({ name: "documents", query: buildLibraryQuery() });
  load();
}

function backToKbFolders() {
  activeKbFolderKey.value = null;
  page.value = 1;
  const query = { ...buildLibraryQuery() };
  delete query.folder;
  router.replace({ name: "documents", query });
  loadKbFolders();
}

function onDeptChange(deptId) {
  activeDeptId.value = deptId;
  activeKbFolderKey.value = null;
  page.value = 1;
  router.replace({ name: "documents", query: buildLibraryQuery() });
  loadKbFolders();
  load();
}

function openCreateFolder() {
  if (!canManageKbFolders.value) {
    ui.warning("documents.messages.noFolderPermission");
    return;
  }
  createFolderName.value = "";
  createFolderDesc.value = "";
  showCreateFolder.value = true;
}

async function submitCreateFolder() {
  const name = createFolderName.value.trim();
  if (!name) {
    ui.warning("validation.folderNameRequired");
    return;
  }
  savingFolder.value = true;
  try {
    const payload = {
      name,
      description: createFolderDesc.value.trim(),
      scope: activeScope.value,
    };
    if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
      payload.dept_id = activeDeptId.value;
    }
    await createKbFolder(payload);
    ui.success("documents.messages.folderCreated");
    showCreateFolder.value = false;
    await loadKbFolders();
  } catch (e) {
    ui.error(e);
  } finally {
    savingFolder.value = false;
  }
}

function openEditFolder(folder) {
  if (!folder?.id || folder.is_system) return;
  editFolderTarget.value = folder;
  editFolderName.value = folder.name;
  editFolderDesc.value = folder.description || "";
}

async function submitEditFolder() {
  const folder = editFolderTarget.value;
  if (!folder?.id) return;
  const name = editFolderName.value.trim();
  if (!name) {
    ui.warning("validation.folderNameRequired");
    return;
  }
  savingFolder.value = true;
  try {
    await updateKbFolder(folder.id, {
      name,
      description: editFolderDesc.value.trim(),
    });
    ui.success("documents.messages.folderUpdated");
    editFolderTarget.value = null;
    await loadKbFolders();
  } catch (e) {
    ui.error(e);
  } finally {
    savingFolder.value = false;
  }
}

async function onDeleteKbFolder(folder) {
  if (!folder?.id) return;
  try {
    await deleteKbFolder(folder.id);
    ui.success("documents.messages.folderDeleted");
    if (activeKbFolderKey.value === String(folder.id)) {
      backToKbFolders();
    } else {
      await loadKbFolders();
    }
  } catch (e) {
    ui.error(e);
  }
}

function folderTooltip(folder) {
  const parts = [];
  if (folder.description) parts.push(folder.description);
  parts.push(`${folder.document_count ?? 0} 篇文档`);
  if (folder.is_system && folder.system_hint) parts.push(folder.system_hint);
  return parts.join("\n");
}

function folderMenuOptions(folder) {
  if (!folder.can_manage || !folder.id || folder.is_system) return [];
  return [
    {
      label: "编辑",
      key: "edit",
      icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
    },
    {
      label: "删除",
      key: "delete",
      icon: () => h(NIcon, null, { default: () => h(TrashOutline) }),
    },
  ];
}

function openBatchMove() {
  if (!canBatchMove.value) return;
  batchMoveDocIds.value = selectedRows.value.map((row) => row.id);
  moveDocTarget.value = selectedRows.value[0] || null;
  showMoveDoc.value = true;
}

function onDocumentMoved() {
  showMoveDoc.value = false;
  moveDocTarget.value = null;
  batchMoveDocIds.value = [];
  checkedRowKeys.value = [];
  load();
}

function onFolderMenuSelect(key, folder) {
  if (key === "edit") openEditFolder(folder);
  if (key === "delete") {
    ui.confirmDelete({
      title: t("common.delete"),
      content: t("documents.confirm.deleteFolder"),
      onPositive: () => onDeleteKbFolder(folder),
    });
  }
}

function openRecycle() {
  libraryView.value = "recycle";
  page.value = 1;
  router.replace({ name: "documents", query: { view: "recycle" } });
  load();
}

function openMyShares() {
  libraryView.value = "my-shares";
  page.value = 1;
  router.replace({ name: "documents", query: { view: "my-shares" } });
  load();
}

function backToLibrary() {
  libraryView.value = "main";
  page.value = 1;
  router.replace({ name: "documents", query: buildLibraryQuery() });
  load();
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
    activeKbFolderKey.value &&
    activeKbFolderKey.value !== VIRTUAL_UNCATEGORIZED &&
    activeKbFolderKey.value !== VIRTUAL_SHARED
  ) {
    payload.folder_id = activeKbFolderKey.value;
  }
  return payload;
}

async function uploadFileToDocument(docId, file) {
  const prep = await prepareUpload(
    docId,
    file.name,
    file.type || "application/octet-stream"
  );
  const putRes = await fetch(prep.upload_url, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": file.type || "application/octet-stream" },
  });
  if (!putRes.ok) throw new Error("上传到存储失败");
  await completeUpload(docId, {
    version_id: prep.version_id,
    file_size: file.size,
  });
}

function onCreateFileChange(opts) {
  const file = opts.fileList[0]?.file ?? null;
  if (file) {
    const check = validateUploadFiles([file], { maxFiles: 1 });
    if (!check.ok) {
      ui.warning(check.message);
      uploadFile.value = null;
      return;
    }
  }
  uploadFile.value = file;
  if (file && !createTitle.value.trim()) {
    createTitle.value = titleFromFileName(file.name);
  }
}

function onBatchFileChange(opts) {
  const files = opts.fileList.map((f) => f.file).filter(Boolean);
  const check = validateUploadFiles(files);
  if (!check.ok) {
    ui.warning(check.message);
    batchUploadFiles.value = check.ok ? check.files : files.slice(0, DOCUMENT_UPLOAD_MAX_FILES);
    return;
  }
  batchUploadFiles.value = check.files;
}

function ensureCanCreateDocuments() {
  if (
    !isMainView.value ||
    activeScope.value === "all" ||
    isSharedScopeTab.value ||
    isSharedFolderView.value
  ) {
    ui.warning("documents.messages.enterKbFolder");
    return false;
  }
  if (!activeKbFolderKey.value) {
    ui.warning("documents.messages.enterFolderFirst");
    return false;
  }
  if (!canCreateInActive.value) {
    ui.warning("documents.messages.noDocPermission");
    return false;
  }
  createScope.value = activeScope.value;
  createDeptId.value =
    ORG_SCOPES.includes(activeScope.value)
      ? activeDeptId.value || orgUnits.value[0]?.id
      : null;
  return true;
}

function openUploadModal(mode = "batch") {
  if (!ensureCanCreateDocuments()) return;
  uploadMode.value = mode;
  createTitle.value = "";
  createDesc.value = "";
  uploadFile.value = null;
  batchUploadFiles.value = [];
  batchProgress.value = { done: 0, total: 0 };
  showUploadModal.value = true;
}

function closeUploadModal() {
  if (batchUploading.value) return;
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
  let title = createTitle.value.trim();
  if (!title) {
    title = titleFromFileName(uploadFile.value.name);
  }
  if (!title) {
    ui.warning("validation.titleRequired");
    return;
  }
  creating.value = true;
  let createdId = null;
  try {
    const doc = await createDocument(buildCreatePayload(title, createDesc.value));
    createdId = doc.id;
    await uploadFileToDocument(doc.id, uploadFile.value);
    ui.success("documents.messages.docCreated");
    showUploadModal.value = false;
    createTitle.value = "";
    createDesc.value = "";
    uploadFile.value = null;
    await load();
    openDocumentDetail(doc.id);
  } catch (e) {
    if (createdId) {
      try {
        await permanentlyDeleteDocument(createdId);
      } catch {
        /* 忽略回滚失败 */
      }
    }
    ui.error(e);
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
  if (ORG_SCOPES.includes(createScope.value) && !createDeptId.value) {
    ui.warning("validation.selectDepartment");
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
            await permanentlyDeleteDocument(createdId);
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
    await load();
  } finally {
    batchUploading.value = false;
  }
}

watch(activeScope, () => {
  if (isMainView.value) page.value = 1;
});

watch(libraryView, () => {
  checkedRowKeys.value = [];
  if (!isMainView.value) {
    keyword.value = "";
    appliedSearch.value = "";
  }
});

onMounted(async () => {
  applyRouteFromQuery();
  await syncLegacySharedScopeRoute();
  await loadFolders();
  await loadKbFolders();
  await load();
});

watch(
  () => [route.query.view, route.query.scope, route.query.folder, route.query.dept_id],
  async () => {
    applyRouteFromQuery();
    await syncLegacySharedScopeRoute();
    page.value = 1;
    await loadKbFolders();
    load();
  }
);
</script>

<template>
  <div class="documents-page feature-page">
    <n-card class="documents-actions-card" size="small">
      <div class="documents-actions-toolbar">
        <n-space align="center" :size="4" class="documents-toolbar documents-toolbar--primary">
          <IconAction
            v-if="!isMainView"
            :label="t('common.backToList')"
            :icon="ArrowBackOutline"
            @click="backToLibrary"
          />
          <template v-if="isSearchMode">
            <IconAction
              :label="t('documents.backFromSearch')"
              :icon="ArrowBackOutline"
              @click="clearSearch"
            />
            <span class="documents-folder-title documents-search-keyword" :title="appliedSearch">
              {{ appliedSearch }}
            </span>
          </template>
          <template v-else-if="showFolderNavInActions">
            <IconAction
              :label="t('documents.backToFolders')"
              :icon="ArrowBackOutline"
              @click="backToKbFolders"
            />
            <span
              v-if="activeKbFolderLabel"
              class="documents-folder-title"
              :title="activeKbFolderLabel"
            >
              {{ activeKbFolderLabel }}
            </span>
          </template>
          <template v-if="showTopFolderBatchActions">
            <IconAction
              :label="t('common.move')"
              :icon="MoveOutline"
              :disabled="!canBatchMove"
              @click="openBatchMove"
            />
            <BatchTableToolbar
              :count="checkedRowKeys.length"
              :disabled="!canBatchDelete"
              :icon="TrashOutline"
              action-type="warning"
              @action="handleBatchDelete"
            />
          </template>
          <template v-else-if="!isSearchMode">
            <IconAction
              :label="t('documents.mySharesAction')"
              :tooltip="isMySharesView ? t('documents.hints.myShares') : t('documents.mySharesAction')"
              :icon="ShareSocialOutline"
              :active="isMySharesView"
              @click="openMyShares"
            />
            <IconAction
              :label="t('documents.recycleAction')"
              :tooltip="isRecycleView ? t('documents.hints.recycle') : t('documents.recycleAction')"
              :icon="ArchiveOutline"
              :active="isRecycleView"
              @click="openRecycle"
            />
          </template>
          <n-popconfirm
            v-if="isRecycleView"
            :disabled="!total"
            @positive-click="confirmEmptyRecycle"
          >
            <template #trigger>
              <span>
                <IconAction
                  :label="t('documents.emptyRecycle')"
                  :icon="TrashBinOutline"
                  type="error"
                  :disabled="!total"
                />
              </span>
            </template>
            {{ t("documents.confirm.emptyRecycle", { count: total }) }}
          </n-popconfirm>
        </n-space>
        <n-space align="center" :size="8" class="documents-toolbar documents-toolbar--secondary">
          <n-select
            v-if="isMainView && showOrgPicker && !isSearchMode"
            :value="activeDeptId"
            :options="deptOptions"
            size="small"
            :placeholder="orgUnits.length > 1 ? t('documents.deptSelectPlaceholder') : undefined"
            class="documents-org-picker__select"
            @update:value="onDeptChange"
          />
          <n-input
            v-model:value="keyword"
            :placeholder="t('documents.searchPlaceholder')"
            clearable
            size="small"
            class="documents-search"
            @keyup.enter="runSearch"
            @clear="clearSearch"
          />
          <IconAction
            :label="t('common.search')"
            :icon="SearchOutline"
            @click="runSearch"
          />
          <IconAction
            v-if="isMainView && usesKbFolders && activeKbFolderKey && !isSharedFolderView"
            :label="t('documents.batchUpload')"
            :icon="CloudUploadOutline"
            type="primary"
            :disabled="!canCreateInActive"
            @click="openUploadModal('batch')"
          />
        </n-space>
      </div>
    </n-card>

    <n-card class="documents-list-card" size="small">
    <div v-if="isSearchMode" class="documents-search-results-head">
      <n-text depth="2">
        {{ t("documents.searchResults", { count: total, keyword: appliedSearch }) }}
      </n-text>
    </div>
    <div
      v-if="isMainView && !isSearchMode"
      class="documents-scope-bookmarks"
      role="tablist"
      :aria-label="t('documents.scopeSwitchLabel')"
    >
      <button
        v-for="f in folders"
        :key="f.scope"
        type="button"
        role="tab"
        class="documents-scope-bookmarks__tab"
        :class="{ 'documents-scope-bookmarks__tab--active': activeScope === f.scope }"
        :aria-selected="activeScope === f.scope"
        @click="onTabChange(f.scope)"
      >
        <span class="documents-scope-bookmarks__label">{{ f.label }}</span>
        <n-tag
          v-if="!f.can_create"
          size="tiny"
          :bordered="false"
          class="documents-scope-bookmarks__tag"
        >
          {{ t("menu.readOnly") }}
        </n-tag>
      </button>
    </div>

    <div v-if="showKbFolderList" v-loading="loading">
      <n-empty
        v-if="!kbFolders.length && !canManageKbFolders"
        description="暂无文件夹"
      />
      <div v-else class="kb-folder-explorer">
        <div
          v-for="(folder, folderIdx) in kbFolders"
          :key="folder.virtual_id || folder.id"
          class="kb-folder-explorer__cell"
          :style="{ '--folder-i': folderIdx }"
        >
          <n-tooltip trigger="hover" :delay="400">
            <template #trigger>
              <KbFolderCard
                :folder="folder"
                :card-key="folder.virtual_id || folder.id || `f-${folderIdx}`"
                :menu-options="folderMenuOptions(folder)"
                @open="openKbFolder"
                @menu-select="onFolderMenuSelect"
              />
            </template>
            {{ folderTooltip(folder) }}
          </n-tooltip>
        </div>
        <div
          v-if="canManageKbFolders"
          class="kb-folder-explorer__cell"
          :style="{ '--folder-i': kbFolders.length }"
        >
          <KbFolderCreateCard @create="openCreateFolder" />
        </div>
      </div>
    </div>

    <template v-else>
    <div v-if="showBottomBatchToolbar" class="doc-list-toolbar page-toolbar">
      <n-space align="center" :size="6">
        <IconAction
          :label="t('common.move')"
          :icon="MoveOutline"
          :disabled="!canBatchMove"
          @click="openBatchMove"
        />
        <BatchTableToolbar
          :count="checkedRowKeys.length"
          :disabled="!canBatchDelete"
          :icon="TrashOutline"
          action-type="warning"
          @action="handleBatchDelete"
        />
      </n-space>
    </div>

    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :row-key="(row) => row.id"
      :checked-row-keys="showBatchDocActions ? checkedRowKeys : undefined"
      @update:checked-row-keys="onCheckedRowKeysChange"
      :pagination="{
        page: page,
        pageSize: pageSize,
        itemCount: total,
        onUpdatePage: onPageChange,
      }"
    />
    </template>
    </n-card>
  </div>

  <n-modal
    v-model:show="showUploadModal"
    preset="card"
    :title="t('documents.uploadModalTitle', { folder: activeKbFolderLabel || activeFolder?.label || '' })"
    class="documents-upload-modal"
    style="width: 520px"
    :mask-closable="false"
  >
    <n-tabs v-model:value="uploadMode" type="segment" size="small" class="documents-upload-modal__tabs">
      <n-tab-pane name="single" :tab="t('documents.createDoc')" />
      <n-tab-pane name="batch" :tab="t('documents.batchUpload')" />
    </n-tabs>
    <n-form class="documents-upload-modal__form">
      <n-form-item label="分级">
        <n-tag :type="scopeTagType[createScope] || 'default'">
          {{ folders.find((x) => x.scope === createScope)?.label || createScope }}
        </n-tag>
      </n-form-item>
      <n-form-item
        v-if="ORG_SCOPES.includes(createScope)"
        label="所属部门"
        required
      >
        <n-select
          v-model:value="createDeptId"
          :options="deptOptions"
          placeholder="选择部门"
        />
      </n-form-item>
      <template v-if="uploadMode === 'single'">
        <n-form-item label="标题" required>
          <n-input
            v-model:value="createTitle"
            placeholder="选择文件后将自动填入文件名，也可手动修改"
          />
        </n-form-item>
        <n-form-item label="说明">
          <n-input v-model:value="createDesc" type="textarea" placeholder="可选" />
        </n-form-item>
        <n-form-item label="文件" required>
          <n-upload
            :max="1"
            :default-upload="false"
            @change="onCreateFileChange"
          >
            <n-button>选择文件</n-button>
          </n-upload>
          <n-text depth="3" style="display: block; margin-top: 6px; font-size: 12px">
            单文件不超过 {{ DOCUMENT_UPLOAD_MAX_MB }}MB
          </n-text>
        </n-form-item>
      </template>
      <template v-else>
        <n-form-item label="文件" required>
          <n-upload
            multiple
            :max="DOCUMENT_UPLOAD_MAX_FILES"
            :default-upload="false"
            @change="onBatchFileChange"
          >
            <n-button>选择文件（最多 {{ DOCUMENT_UPLOAD_MAX_FILES }} 个）</n-button>
          </n-upload>
          <n-text depth="3" style="display: block; margin-top: 6px; font-size: 12px">
            每个文件不超过 {{ DOCUMENT_UPLOAD_MAX_MB }}MB；文档名默认为文件名，说明留空
          </n-text>
          <n-text
            v-if="batchUploadFiles.length"
            depth="3"
            style="display: block; margin-top: 4px; font-size: 12px"
          >
            已选 {{ batchUploadFiles.length }} 个文件
          </n-text>
        </n-form-item>
        <n-progress
          v-if="batchUploading && batchProgress.total"
          type="line"
          :percentage="Math.round((batchProgress.done / batchProgress.total) * 100)"
          :show-indicator="true"
          style="margin-top: 8px"
        />
      </template>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="batchUploading || creating" @click="closeUploadModal">
          取消
        </n-button>
        <n-button
          v-if="uploadMode === 'single'"
          type="primary"
          :loading="creating"
          @click="submitCreate"
        >
          创建
        </n-button>
        <n-button
          v-else
          type="primary"
          :loading="batchUploading"
          :disabled="!batchUploadFiles.length"
          @click="submitBatchUpload"
        >
          开始上传
        </n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal
    v-model:show="showCreateFolder"
    preset="card"
    title="新建知识库文件夹"
    style="width: 400px"
    :mask-closable="false"
  >
    <n-form>
      <n-form-item label="名称" required>
        <n-input
          v-model:value="createFolderName"
          placeholder="例如：技术规范、政策汇编"
          @keyup.enter="submitCreateFolder"
        />
      </n-form-item>
      <n-form-item label="介绍">
        <n-input
          v-model:value="createFolderDesc"
          type="textarea"
          placeholder="可选，说明该知识库的用途"
          :autosize="{ minRows: 2, maxRows: 5 }"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showCreateFolder = false">取消</n-button>
        <n-button type="primary" :loading="savingFolder" @click="submitCreateFolder">
          创建
        </n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal
    :show="!!editFolderTarget"
    preset="card"
    title="编辑文件夹"
    style="width: 480px"
    :mask-closable="false"
    @update:show="(v) => { if (!v) editFolderTarget = null; }"
  >
    <n-form>
      <n-form-item label="名称" required>
        <n-input v-model:value="editFolderName" @keyup.enter="submitEditFolder" />
      </n-form-item>
      <n-form-item label="介绍">
        <n-input
          v-model:value="editFolderDesc"
          type="textarea"
          placeholder="说明该知识库的用途、适用范围等"
          :autosize="{ minRows: 2, maxRows: 6 }"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="editFolderTarget = null">取消</n-button>
        <n-button type="primary" :loading="savingFolder" @click="submitEditFolder">
          保存
        </n-button>
      </n-space>
    </template>
  </n-modal>

  <MoveDocumentFolderModal
    v-if="showMoveDoc && moveDocTarget"
    v-model:show="showMoveDoc"
    :document-id="moveDocTarget.id"
    :document-ids="batchMoveDocIds"
    :document-title="moveDocTarget.title"
    :scope="moveDocTarget.scope"
    :folder-scope="moveFolderScope"
    :dept-id="moveDocTarget.dept_id"
    :folder-dept-id="moveFolderDeptId"
    :current-folder-id="moveDocTarget.folder_id"
    @moved="onDocumentMoved"
  />
</template>
