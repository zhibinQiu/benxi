<script setup>
defineOptions({ name: "DocumentsView" });
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
  NUploadDragger,
  NTabs,
  NTabPane,
  NSelect,
  NTag,
  NEmpty,
  NProgress,
  NText,
  NTooltip,
  NIcon,
  NDropdown } from "naive-ui";
import {
  CreateOutline,
  TrashOutline,
  MoveOutline,
  ArrowBackOutline,
  SearchOutline,
  ShareSocialOutline,
  CloudUploadOutline,
  EyeOutline,
  RefreshOutline } from "@vicons/ionicons5";
import MoveDocumentFolderModal from "../components/MoveDocumentFolderModal.vue";
import KbFolderCard from "../components/KbFolderCard.vue";
import KbFolderCreateCard from "../components/KbFolderCreateCard.vue";
import IconAction from "../components/IconAction.vue";
import BatchTableToolbar from "../components/BatchTableToolbar.vue";
import AdminFormModal from "../components/AdminFormModal.vue";
import FileDropZone from "../components/FileDropZone.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeader } from "../composables/usePageHeader";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { useDocumentLibrary } from "../composables/useDocumentLibrary.js";
import {
  ORG_SCOPES,
  LIBRARY_FOLDER_ORDER } from "../constants/documentScope";
import {
  DOCUMENT_UPLOAD_MAX_FILES,
  formatDocumentFormatLabel,
  getDocumentUploadMaxMb,
  titleFromFileName,
  validateUploadFiles } from "../constants/documentUpload";
import {
  canBatchSelectDocument,
  canDeleteDocument,
  canModifyDocument,
} from "../utils/documentCaps.js";
import {
  clearDocumentsViewCache,
  readDocumentsKbFoldersCache,
  readDocumentsListCache,
  writeDocumentsKbFoldersCache,
  writeDocumentsListCache } from "../utils/documentsViewCache.js";
import { renderIconAction, renderIconActionGroup } from "../utils/tableIconActions";
import { renderKnowledgeIndexTag } from "../utils/knowledgeIndex.js";
import { notifyKnowledgeScopeTreeStale } from "../utils/knowledgeScopeRefresh.js";
import {
  createDocument,
  createKbFolder,
  deleteKbFolder,
  fetchDocuments,
  fetchKbFolders,
  fetchMySharedDocuments,
  prepareUpload,
  uploadDocumentBlob,
  completeUpload,
  batchDeleteDocuments,
  deleteDocument,
  updateKbFolder } from "../api/documents.js";

const route = useRoute();
const { isSystemAdmin, user } = useAuth();
const router = useRouter();
const { t, scopeLabel, locale, docStatusLabel, docLevelLabel } = useI18n();
const ui = usePlatformUi();
const { setHeaderTitle, clearHeaderTitle } = usePageHeader();
const { loadDocumentLibrary, invalidateDocumentLibrary } = useDocumentLibrary();

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
const kbFoldersLoading = ref(false);
const kbCanManageFolders = ref(false);
const refreshing = ref(false);
const { headerExtensionActive } = usePageHeaderExtension();
const uploadMaxMb = computed(() => getDocumentUploadMaxMb());
const activeDeptId = ref(null);
/** 系统管理员在个人级 Tab 下切换查看的账户 */
const activeOwnerId = ref(null);
const personalOwners = ref([]);
/** main | my-shares */
const libraryView = ref("main");
const companies = ref([]);
const departments = ref([]);
const teams = ref([]);
/** 忽略过期的 load / loadKbFolders 结果，避免切换分级时串数据 */
let kbFoldersLoadSeq = 0;
let documentsLoadSeq = 0;
/** openKbFolder 已主动 load 时，跳过 route watch 的重复请求 */
let skipNextRouteLoad = false;
const prefetchingFolderKeys = new Set();

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

const showOwnerPicker = computed(
  () =>
    activeScope.value === "personal" &&
    isSystemAdmin.value &&
    personalOwners.value.length > 1
);

const ownerOptions = computed(() =>
  personalOwners.value.map((o) => ({ label: o.name, value: o.id }))
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
const uploadMode = ref("single");
const createTitle = ref("");
const createDesc = ref("");
const createScope = ref("personal");
const createDeptId = ref(null);
const uploadFile = ref(null);
const creating = ref(false);

const batchUploadFiles = ref([]);
const batchUploadFileList = ref([]);
const batchUploading = ref(false);
const batchProgress = ref({ done: 0, total: 0 });
const batchUploadKey = ref(0);

const batchUploadStats = computed(() => {
  const files = batchUploadFiles.value;
  return {
    count: files.length,
    totalSize: files.reduce((sum, file) => sum + (Number(file?.size) || 0), 0),
  };
});

function formatUploadFileSize(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const uploadTargetLabel = computed(
  () => activeKbFolderLabel.value || activeFolder.value?.label || "未分类"
);

const canSubmitSingleUpload = computed(
  () => Boolean(uploadFile.value) && !creating.value && !batchUploading.value
);
const activeFolder = computed(() =>
  folders.value.find((f) => f.scope === activeScope.value)
);

const canCreateInActive = computed(() => activeFolder.value?.can_create ?? false);

const deptOptions = computed(() =>
  orgUnits.value.map((d) => ({ label: d.name, value: d.id }))
);

function personalOwnerParam() {
  if (activeScope.value !== "personal" || !isSystemAdmin.value) return null;
  return activeOwnerId.value || null;
}

function ensureActivePersonalOwner() {
  if (!isSystemAdmin.value || activeScope.value !== "personal") return;
  const owners = personalOwners.value;
  if (!owners.length) {
    activeOwnerId.value = user.value?.id || null;
    return;
  }
  if (
    activeOwnerId.value &&
    owners.some((o) => String(o.id) === String(activeOwnerId.value))
  ) {
    return;
  }
  const self = owners.find((o) => String(o.id) === String(user.value?.id));
  activeOwnerId.value = self?.id || owners[0].id;
}

const scopeTagType = {
  company: "info",
  department: "warning",
  team: "success",
  personal: "default",
  shared: "success",
  all: "primary"};

const VIRTUAL_UNCATEGORIZED = "__uncategorized__";
const VIRTUAL_SHARED = "__shared__";

/** 内置文件夹 → 用户文件夹（同组内保持 API 原序） */
function sortKbFoldersForDisplay(items) {
  const systemOrder = {
    uncategorized: 0,
    shared: 1,
    normal: 2};
  return [...(items || [])]
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const ar = systemOrder[a.item.kind] ?? 50;
      const br = systemOrder[b.item.kind] ?? 50;
      if (ar !== br) return ar - br;
      return a.index - b.index;
    })
    .map(({ item }) => item);
}

const isMainView = computed(() => libraryView.value === "main");
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
  () => isMainView.value && !isMySharesView.value
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

const canBatchDelete = computed(
  () =>
    showBatchDocActions.value &&
    canShowDeleteInList.value &&
    deletableSelectedRows.value.length > 0
);

watch(
  [isMySharesView, locale],
  () => {
    if (isMySharesView.value) setHeaderTitle(t("documents.myShares"));
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
      disabled: (row) => !canBatchSelectDocument(row)});
  }
  base.push({ title: t("documents.columns.title"), key: "title", ellipsis: { tooltip: true } });
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
        : "—"});
  base.push({
    title: t("documents.columns.indexStatus"),
    key: "indexStatus",
    width: 96,
    render: (row) => renderKnowledgeIndexTag(row)});
  if (isMySharesView.value) {
    base.push(
      {
        title: t("documents.columns.scope"),
        key: "scope",
        width: 90,
        render: (row) => scopeLabel(row.scope) || row.scope},
      {
        title: t("documents.columns.shareTo"),
        key: "share_to_summary",
        ellipsis: { tooltip: true },
        render: (row) => row.share_to_summary || "—"},
      {
        title: t("documents.columns.updatedAt"),
        key: "updated_at",
        width: 180,
        render: (row) => new Date(row.updated_at).toLocaleString()},
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
                openDocumentDetail(row.id)},
            { default: () => t("common.view") }
          )}
    );
    return base;
  }
  if (!isSearchMode.value) {
    base.push({
      title: t("documents.columns.status"),
      key: "status",
      width: 90,
      render: (row) => docStatusLabel(row.status) || row.status});
  }
  if (isSearchMode.value || activeScope.value === "all") {
    base.push(
      {
        title: t("documents.columns.scope"),
        key: "scope",
        width: 90,
        render: (row) => scopeLabel(row.scope) || row.scope},
      {
        title: t("documents.columns.folder"),
        key: "folder_name",
        width: 120,
        ellipsis: { tooltip: true },
        render: (row) => row.folder_name || "—"},
      {
        title: t("documents.columns.owner"),
        key: "owner_name",
        width: 120,
        render: (row) => row.owner_name || "未知用户"},
      {
        title: t("documents.columns.dept"),
        key: "dept_name",
        width: 110,
        render: (row) =>
          ORG_SCOPES.includes(row.scope) ? row.dept_name || "—" : "—"},
      {
        title: t("documents.columns.myPermission"),
        key: "effective_level",
        width: 90,
        render: (row) => docLevelLabel(row.effective_level) || row.effective_level || "—"}
    );
  } else if (isSharedScopeTab.value || isSharedFolderView.value) {
    base.push(
      {
        title: t("documents.columns.sharer"),
        key: "owner_name",
        width: 120,
        render: (row) => row.owner_name || "未知用户"},
      {
        title: t("documents.columns.grantedBy"),
        key: "granted_by_name",
        width: 140,
        render: (row) => row.granted_by_name || "—"},
      {
        title: t("documents.columns.myPermission"),
        key: "shared_level",
        width: 90,
        render: (row) => docLevelLabel(row.shared_level) || row.shared_level || "—"}
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
        render: (row) => row.dept_name || "—"},
      {
        title: t("documents.columns.owner"),
        key: "owner_name",
        width: 140,
        render: (row) => row.owner_name || "未知用户"}
    );
  }
  base.push(
    {
      title: t("documents.columns.updatedAt"),
      key: "updated_at",
      width: 180,
      render: (row) => new Date(row.updated_at).toLocaleString()},
    {
      title: t("documents.columns.actions"),
      key: "actions",
      width: 72,
      render: (row) =>
        renderIconAction({
          label: t("common.view"),
          icon: EyeOutline,
          type: "primary",
          onClick: () => openDocumentDetail(row.id)})}
  );
  return base;
});

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
            skipped})
        : t("documents.confirm.deleteBatch", { count: rows.length }),
    onPositive: async () => {
      const res = await batchDeleteDocuments(rows.map((row) => row.id));
      const count = res.deleted_count ?? res.deleted?.length ?? 0;
      const failed = res.failed || [];
      if (failed.length) {
        ui.warning("messages.batchDeletedPartial", {
          success: count,
          failed: failed.length});
      } else {
        ui.success("documents.messages.deletedBatch", { count });
      }
      checkedRowKeys.value = [];
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
    }});
}

function onCheckedRowKeysChange(keys) {
  checkedRowKeys.value = keys;
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
  if (route.query.owner_id) {
    activeOwnerId.value = route.query.owner_id;
  } else if (activeScope.value !== "personal") {
    activeOwnerId.value = null;
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
      folder: activeKbFolderKey.value || VIRTUAL_SHARED}});
}

async function loadFolders({ force = false } = {}) {
  try {
    const lib = await loadDocumentLibrary({ force });
    applyLibraryData(lib);
    await syncLegacySharedScopeRoute();
  } catch (e) {
    if (!folders.value.length) {
      folders.value = [];
      companies.value = [];
      departments.value = [];
      teams.value = [];
    }
    ui.error(e);
  }
}

function applyLibraryData(lib) {
  if (!lib) return;
  folders.value = normalizeFolders(lib.folders);
  companies.value = lib.companies || [];
  departments.value = lib.departments || [];
  teams.value = lib.teams || [];
  personalOwners.value = lib.personal_owners || [];
  ensureActivePersonalOwner();
  const units = orgUnits.value;
  if (
    ORG_SCOPES.includes(activeScope.value) &&
    units.length &&
    !activeDeptId.value
  ) {
    activeDeptId.value = units[0].id;
  }
  applyRouteFromQuery();
  if (
    libraryView.value === "main" &&
    folders.value.length &&
    !folders.value.find((f) => f.scope === activeScope.value)
  ) {
    activeScope.value = folders.value[0].scope;
  }
}

async function loadKbFolders({ force = false } = {}) {
  const seq = ++kbFoldersLoadSeq;
  if (!usesKbFolders.value) {
    kbFoldersLoading.value = false;
    kbFolders.value = [];
    return;
  }
  const deptId =
    ORG_SCOPES.includes(activeScope.value) && activeDeptId.value
      ? activeDeptId.value
      : null;
  const ownerId = personalOwnerParam();
  if (!force) {
    const cached = readDocumentsKbFoldersCache(activeScope.value, deptId, ownerId);
    if (cached) {
      if (seq !== kbFoldersLoadSeq) return;
      kbFolders.value = sortKbFoldersForDisplay(cached.items || []);
      kbCanManageFolders.value = !!cached.can_manage_folders;
      kbFoldersLoading.value = false;
      void loadKbFolders({ force: true });
      return;
    }
  }
  const hadFolders = kbFolders.value.length > 0;
  if (!hadFolders) kbFoldersLoading.value = true;
  try {
    const params = { scope: activeScope.value };
    if (deptId) params.dept_id = deptId;
    if (ownerId) params.owner_id = ownerId;
    const data = await fetchKbFolders(params);
    if (seq !== kbFoldersLoadSeq) return;
    writeDocumentsKbFoldersCache(activeScope.value, deptId, ownerId, data);
    kbFolders.value = sortKbFoldersForDisplay(data.items || []);
    kbCanManageFolders.value = !!data.can_manage_folders;
  } catch (e) {
    if (seq !== kbFoldersLoadSeq) return;
    if (!kbFolders.value.length) kbFolders.value = [];
    ui.error(e);
  } finally {
    if (seq === kbFoldersLoadSeq) kbFoldersLoading.value = false;
  }
}

function buildListCacheKey({ folderKey = activeKbFolderKey.value, pageNum = page.value } = {}) {
  if (isSearchMode.value) {
    return `search:${appliedSearch.value.trim()}:${pageNum}:${pageSize.value}`;
  }
  if (isMySharesView.value) {
    return `my-shares:${pageNum}:${pageSize.value}`;
  }
  if (isSharedScopeTab.value || folderKey === VIRTUAL_SHARED) {
    return `shared:${pageNum}:${pageSize.value}`;
  }
  if (usesKbFolders.value && !folderKey) {
    return "folder-list";
  }
  const parts = [
    activeScope.value,
    activeDeptId.value || "",
    activeOwnerId.value || "",
    folderKey || "",
    pageNum,
    pageSize.value,
    keyword.value.trim() || "",
  ];
  return parts.join(":");
}

function buildFolderDocParams(folderKey, pageNum = 1) {
  const docParams = {
    page: pageNum,
    page_size: pageSize.value,
    keyword: keyword.value.trim() || undefined,
    scope: activeScope.value,
  };
  if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
    docParams.dept_id = activeDeptId.value;
  }
  const ownerId = personalOwnerParam();
  if (ownerId) docParams.owner_id = ownerId;
  if (folderKey === VIRTUAL_UNCATEGORIZED) {
    docParams.uncategorized = true;
  } else {
    docParams.folder_id = folderKey;
  }
  return docParams;
}

async function prefetchFolderDocuments(folder) {
  if (!usesKbFolders.value || isSearchMode.value) return;
  const key = folder.virtual_id || (folder.id ? String(folder.id) : null);
  if (!key) return;
  const cacheKey = buildListCacheKey({ folderKey: key, pageNum: 1 });
  if (readDocumentsListCache(cacheKey) || prefetchingFolderKeys.has(cacheKey)) return;
  prefetchingFolderKeys.add(cacheKey);
  try {
    const data =
      key === VIRTUAL_SHARED
        ? await fetchDocuments({ page: 1, page_size: pageSize.value, scope: "shared" })
        : await fetchDocuments(buildFolderDocParams(key, 1));
    writeDocumentsListCache(cacheKey, data);
  } catch {
    /* 预取失败不影响交互 */
  } finally {
    prefetchingFolderKeys.delete(cacheKey);
  }
}

function applyCachedListForActiveFolder() {
  const listCacheKey = buildListCacheKey();
  const cached = readDocumentsListCache(listCacheKey);
  if (cached) {
    items.value = cached.items || [];
    total.value = cached.total ?? 0;
    loading.value = false;
    return true;
  }
  items.value = [];
  total.value = 0;
  loading.value = true;
  return false;
}

async function refreshDocumentsView() {
  if (refreshing.value) return;
  refreshing.value = true;
  invalidateDocumentLibrary();
  clearDocumentsViewCache();
  notifyKnowledgeScopeTreeStale();
  try {
    await Promise.all([
      loadFolders({ force: true }),
      loadKbFolders({ force: true }),
    ]);
    await load({ force: true });
  } catch (e) {
    ui.error(e);
  } finally {
    refreshing.value = false;
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
  load({ force: true });
}

function clearSearch() {
  const hadSearch = appliedSearch.value.trim().length > 0;
  keyword.value = "";
  appliedSearch.value = "";
  page.value = 1;
  if (hadSearch && isMainView.value) load();
}

async function load({ force = false, background = false } = {}) {
  const seq = ++documentsLoadSeq;
  const listCacheKey = buildListCacheKey();
  if (!force && !background) {
    const cached = readDocumentsListCache(listCacheKey);
    if (cached) {
      if (seq !== documentsLoadSeq) return;
      items.value = cached.items || [];
      total.value = cached.total ?? 0;
      loading.value = false;
      void load({ force: true, background: true });
      return;
    }
  }
  const hadItems = items.value.length > 0;
  if (!background && !hadItems) {
    loading.value = true;
    checkedRowKeys.value = [];
  }
  try {
    if (isSearchMode.value) {
      const data = await fetchDocuments({
        page: page.value,
        page_size: pageSize.value,
        scope: "all",
        keyword: appliedSearch.value.trim()});
      if (seq !== documentsLoadSeq) return;
      items.value = data.items || [];
      total.value = data.total ?? 0;
      writeDocumentsListCache(listCacheKey, data);
      return;
    }
    if (usesKbFolders.value && !activeKbFolderKey.value) {
      if (seq !== documentsLoadSeq) return;
      items.value = [];
      total.value = 0;
      return;
    }
    const params = {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value.trim() || undefined};
    let data;
    if (isMySharesView.value) {
      data = await fetchMySharedDocuments(params);
    } else if (isSharedScopeTab.value || isSharedFolderView.value) {
      data = await fetchDocuments({ ...params, scope: "shared" });
    } else if (usesKbFolders.value && activeKbFolderKey.value) {
      data = await fetchDocuments(buildFolderDocParams(activeKbFolderKey.value, page.value));
    } else {
      const docParams = { ...params, scope: activeScope.value };
      if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
        docParams.dept_id = activeDeptId.value;
      }
      const ownerId = personalOwnerParam();
      if (ownerId) docParams.owner_id = ownerId;
      data = await fetchDocuments(docParams);
    }
    if (seq !== documentsLoadSeq) return;
    items.value = data.items || [];
    total.value = data.total ?? 0;
    writeDocumentsListCache(listCacheKey, data);
  } catch (e) {
    if (seq !== documentsLoadSeq) return;
    if (!items.value.length) {
      items.value = [];
      total.value = 0;
    }
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
  if (activeScope.value === "personal" && activeOwnerId.value) {
    query.owner_id = activeOwnerId.value;
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
  if (scope === "personal") {
    ensureActivePersonalOwner();
  } else {
    activeOwnerId.value = null;
  }
  await router.replace({ name: "documents", query: buildLibraryQuery() });
}

function openKbFolder(folder) {
  const key = folder.virtual_id || (folder.id ? String(folder.id) : null);
  if (!key) return;
  keyword.value = "";
  appliedSearch.value = "";
  activeKbFolderKey.value = key;
  page.value = 1;
  checkedRowKeys.value = [];
  applyCachedListForActiveFolder();
  skipNextRouteLoad = true;
  void load();
  router.replace({ name: "documents", query: buildLibraryQuery() });
}

function backToKbFolders() {
  activeKbFolderKey.value = null;
  page.value = 1;
  items.value = [];
  total.value = 0;
  loading.value = false;
  checkedRowKeys.value = [];
  const query = { ...buildLibraryQuery() };
  delete query.folder;
  router.replace({ name: "documents", query });
}

function onDeptChange(deptId) {
  activeDeptId.value = deptId;
  activeKbFolderKey.value = null;
  page.value = 1;
  router.replace({ name: "documents", query: buildLibraryQuery() });
}

function onOwnerChange(ownerId) {
  activeOwnerId.value = ownerId;
  activeKbFolderKey.value = null;
  page.value = 1;
  router.replace({ name: "documents", query: buildLibraryQuery() });
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
      scope: activeScope.value};
    if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
      payload.dept_id = activeDeptId.value;
    }
    await createKbFolder(payload);
    ui.success("documents.messages.folderCreated");
    showCreateFolder.value = false;
    await loadKbFolders({ force: true });
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
      description: editFolderDesc.value.trim()});
    ui.success("documents.messages.folderUpdated");
    editFolderTarget.value = null;
    await loadKbFolders({ force: true });
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
      await loadKbFolders({ force: true });
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
      icon: () => h(NIcon, null, { default: () => h(CreateOutline) })},
    {
      label: "删除",
      key: "delete",
      icon: () => h(NIcon, null, { default: () => h(TrashOutline) })},
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
  loadKbFolders({ force: true });
  load({ force: true });
}

function onFolderMenuSelect(key, folder) {
  if (key === "edit") openEditFolder(folder);
  if (key === "delete") {
    ui.confirmDelete({
      title: t("common.delete"),
      content: t("documents.confirm.deleteFolder"),
      onPositive: () => onDeleteKbFolder(folder)});
  }
}

function openMyShares() {
  libraryView.value = "my-shares";
  page.value = 1;
  router.replace({ name: "documents", query: { view: "my-shares" } });
}

function backToLibrary() {
  libraryView.value = "main";
  page.value = 1;
  router.replace({ name: "documents", query: buildLibraryQuery() });
}

function buildCreatePayload(title, description = "") {
  const payload = {
    title,
    description: description || "",
    scope: createScope.value};
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
  await uploadDocumentBlob(prep.upload_url, file);
  await completeUpload(docId, {
    version_id: prep.version_id,
    file_size: file.size});
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
  if (!createTitle.value.trim()) {
    createTitle.value = titleFromFileName(file.name);
  }
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

function openUploadModal(mode = "single") {
  if (!ensureCanCreateDocuments()) return;
  uploadMode.value = mode;
  createTitle.value = "";
  createDesc.value = "";
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
  let uploadCompleted = false;
  try {
    const doc = await createDocument(buildCreatePayload(title, createDesc.value));
    createdId = doc.id;
    await uploadFileToDocument(doc.id, uploadFile.value);
    uploadCompleted = true;
    ui.success("documents.messages.docCreated");
    showUploadModal.value = false;
    createTitle.value = "";
    createDesc.value = "";
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
            await deleteDocument(createdId);
          } catch {
            /* 忽略回滚失败 */
          }
        }
      } finally {
        batchProgress.value = {
          done: batchProgress.value.done + 1,
          total: check.files.length};
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
        names: failed.map((f) => f.name).join("、")});
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

onMounted(() => {
  applyRouteFromQuery();
  void syncLegacySharedScopeRoute().then(() => {
    void loadFolders();
    void loadKbFolders();
    void load();
  });
});

watch(
  () => [
    route.query.view,
    route.query.scope,
    route.query.folder,
    route.query.dept_id,
    route.query.owner_id,
  ],
  () => {
    applyRouteFromQuery();
    if (skipNextRouteLoad) {
      skipNextRouteLoad = false;
      return;
    }
    page.value = 1;
    void syncLegacySharedScopeRoute().then(() => {
      void loadKbFolders();
      void load();
    });
  }
);
</script>

<template>
  <div class="documents-page feature-page">
    <Teleport to="#page-header-extension" :disabled="!headerExtensionActive">
      <div class="documents-actions-bar">
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
              :count="deletableSelectedRows.length || checkedRowKeys.length"
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
          </template>
        </n-space>
        <n-space align="center" :size="8" class="documents-toolbar documents-toolbar--secondary">
          <n-select
            v-if="isMainView && showOwnerPicker && !isSearchMode"
            :value="activeOwnerId"
            :options="ownerOptions"
            size="small"
            :placeholder="t('documents.ownerSelectPlaceholder')"
            class="documents-org-picker__select"
            @update:value="onOwnerChange"
          />
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
            :label="t('common.refresh')"
            :icon="RefreshOutline"
            :disabled="refreshing"
            @click="refreshDocumentsView"
          />
          <IconAction
            v-if="isMainView && usesKbFolders && activeKbFolderKey && !isSharedFolderView"
            :label="t('documents.uploadDoc')"
            :icon="CloudUploadOutline"
            type="primary"
            :disabled="!canCreateInActive"
            @click="openUploadModal('single')"
          />
        </n-space>
        </div>
      </div>
    </Teleport>

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

    <Transition name="doc-view" mode="out-in">
    <div v-if="showKbFolderList" key="folder-grid" v-loading="kbFoldersLoading">
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
          @mouseenter="prefetchFolderDocuments(folder)"
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

    <div v-else key="doc-list" class="documents-list-panel">
    <div v-if="showBottomBatchToolbar" class="doc-list-toolbar page-toolbar">
      <n-space align="center" :size="6">
        <IconAction
          :label="t('common.move')"
          :icon="MoveOutline"
          :disabled="!canBatchMove"
          @click="openBatchMove"
        />
        <BatchTableToolbar
          :count="deletableSelectedRows.length || checkedRowKeys.length"
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
      :loading="loading && !items.length"
      :row-key="(row) => row.id"
      :checked-row-keys="showBatchDocActions ? checkedRowKeys : undefined"
      @update:checked-row-keys="onCheckedRowKeysChange"
      :pagination="{
        page: page,
        pageSize: pageSize,
        itemCount: total,
        onUpdatePage: onPageChange}"
    />
    </div>
    </Transition>
    </n-card>
  </div>

  <AdminFormModal
    v-model:show="showUploadModal"
    class="documents-upload-modal"
    :title="t('documents.uploadModalTitle', { folder: uploadTargetLabel })"
    :subtitle="t('documents.uploadModalLead')"
    width="min(520px, 94vw)"
  >
    <n-tabs
      v-model:value="uploadMode"
      type="segment"
      size="small"
      class="documents-upload-modal__tabs"
    >
      <n-tab-pane name="single" :tab="t('documents.uploadSingle')" />
      <n-tab-pane name="batch" :tab="t('documents.batchUpload')" />
    </n-tabs>

    <div class="documents-upload-modal__meta">
      <n-text depth="3" class="documents-upload-modal__meta-label">
        {{ t("documents.uploadTargetScope") }}
      </n-text>
      <n-tag size="small" :bordered="false" :type="scopeTagType[createScope] || 'default'">
        {{ folders.find((x) => x.scope === createScope)?.label || createScope }}
      </n-tag>
      <n-text depth="3" class="documents-upload-modal__meta-folder">
        {{ uploadTargetLabel }}
      </n-text>
    </div>

    <n-form
      class="documents-upload-modal__form"
      label-placement="top"
      :show-require-mark="uploadMode === 'single'"
    >
      <n-form-item
        v-if="ORG_SCOPES.includes(createScope)"
        :label="t('documents.uploadDeptLabel')"
        required
      >
        <n-select
          v-model:value="createDeptId"
          :options="deptOptions"
          :placeholder="t('documents.deptSelectPlaceholder')"
        />
      </n-form-item>

      <template v-if="uploadMode === 'single'">
        <n-form-item :label="t('documents.uploadFileLabel')" required>
          <file-drop-zone
            class="documents-upload-modal__file-picker"
            :title="t('documents.uploadDropHint')"
            :hint="t('documents.uploadSizeHint', { mb: uploadMaxMb })"
            :file-name="uploadFile?.name || ''"
            :disabled="creating"
            @change="onSingleFileDropChange"
          />
        </n-form-item>

        <n-form-item :label="t('documents.uploadTitleLabel')" required>
          <n-input
            v-model:value="createTitle"
            :placeholder="t('documents.uploadTitlePlaceholder')"
          />
        </n-form-item>

        <n-form-item :label="t('documents.uploadDescLabel')">
          <n-input
            v-model:value="createDesc"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :placeholder="t('documents.uploadDescPlaceholder')"
          />
        </n-form-item>
      </template>

      <template v-else>
        <n-form-item :label="t('documents.uploadFileLabel')" required>
          <n-upload
            :key="batchUploadKey"
            v-model:file-list="batchUploadFileList"
            multiple
            :default-upload="false"
            :show-file-list="false"
            @change="onBatchFileChange"
          >
            <n-upload-dragger
              class="documents-upload-modal__dropzone"
              :class="{ 'documents-upload-modal__dropzone--ready': batchUploadFiles.length }"
            >
              <div class="documents-upload-modal__dropzone-inner">
                <n-icon :size="34" :component="CloudUploadOutline" class="documents-upload-modal__dropzone-icon" />
                <span class="documents-upload-modal__dropzone-title">
                  {{
                    batchUploadFiles.length
                      ? t("documents.uploadBatchSelected", { count: batchUploadStats.count })
                      : t("documents.uploadBatchDropHint", { max: DOCUMENT_UPLOAD_MAX_FILES })
                  }}
                </span>
                <span class="documents-upload-modal__dropzone-meta">
                  <template v-if="batchUploadFiles.length">
                    {{
                      t("documents.uploadBatchSummary", {
                        size: formatUploadFileSize(batchUploadStats.totalSize),
                      })
                    }}
                    ·
                    <n-button
                      text
                      type="primary"
                      size="tiny"
                      :disabled="batchUploading"
                      @click.stop="clearBatchUploadSelection"
                    >
                      {{ t("documents.uploadReselect") }}
                    </n-button>
                  </template>
                  <template v-else>
                    {{ t("documents.uploadBatchMeta", { mb: uploadMaxMb }) }}
                  </template>
                </span>
              </div>
            </n-upload-dragger>
          </n-upload>
          <n-progress
            v-if="batchUploading && batchProgress.total"
            type="line"
            :percentage="Math.round((batchProgress.done / batchProgress.total) * 100)"
            :show-indicator="true"
            class="documents-upload-modal__batch-progress"
          />
        </n-form-item>
      </template>
    </n-form>

    <p class="documents-upload-modal__footnote">
      {{ t("documents.uploadIndexHint") }}
    </p>

    <template #footer>
      <n-space justify="end" :size="10">
        <n-button :disabled="batchUploading || creating" @click="closeUploadModal">
          {{ t("common.cancel") }}
        </n-button>
        <n-button
          v-if="uploadMode === 'single'"
          type="primary"
          :loading="creating"
          :disabled="!canSubmitSingleUpload"
          @click="submitCreate"
        >
          {{ t("documents.uploadSubmitSingle") }}
        </n-button>
        <n-button
          v-else
          type="primary"
          :loading="batchUploading"
          :disabled="!batchUploadFiles.length"
          @click="submitBatchUpload"
        >
          {{ t("documents.uploadSubmitBatch", { count: batchUploadFiles.length || 0 }) }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>

  <AdminFormModal
    v-model:show="showCreateFolder"
    title="新建知识库文件夹"
    subtitle="在当前分级下创建文档分类文件夹"
    width="400px"
  >
    <n-form label-placement="top">
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
  </AdminFormModal>

  <AdminFormModal
    :show="!!editFolderTarget"
    title="编辑文件夹"
    subtitle="修改文件夹名称与说明"
    width="480px"
    @update:show="(v) => { if (!v) editFolderTarget = null; }"
  >
    <n-form label-placement="top">
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
  </AdminFormModal>

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
