<script setup>
defineOptions({ name: "DocumentsView" });
import { computed, h, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NSpace,
  NDataTable,
  NInput,
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
  NIcon,
  NCard } from "naive-ui";
import {
  CreateOutline,
  TrashOutline,
  MoveOutline,
  ArrowBackOutline,
  SearchOutline,
  CloudUploadOutline,
  RocketOutline,
  EyeOutline,
  ConstructOutline,
  RefreshOutline } from "@vicons/ionicons5";
import MoveDocumentFolderModal from "../components/MoveDocumentFolderModal.vue";
import BatchPublishModal from "../components/BatchPublishModal.vue";
import DocumentUploadLocationPicker from "../components/DocumentUploadLocationPicker.vue";
import KbFolderCard from "../components/KbFolderCard.vue";
import KbFolderCreateCard from "../components/KbFolderCreateCard.vue";
import IconAction from "../components/IconAction.vue";
import PlatformSpin from "../components/PlatformSpin.vue";
import BatchTableToolbar from "../components/BatchTableToolbar.vue";
import ListTableFooter from "../components/ListTableFooter.vue";
import AdminFormModal from "../components/AdminFormModal.vue";
import FileDropZone from "../components/FileDropZone.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { KNOWLEDGE_INDEX_UPDATED_EVENT } from "../constants/platformEvents.js";
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
  DOCUMENT_UPLOAD_ACCEPT,
  DOCUMENT_UPLOAD_MAX_FILES,
  formatDocumentFormatLabel,
  getDocumentUploadMaxMb,
  titleFromFileName,
  validateUploadFiles } from "../constants/documentUpload.js";
import {
  canBatchSelectDocument,
  canDeleteDocument,
  canModifyDocument,
} from "../utils/documentCaps.js";
import {
  clearDocumentsViewCache,
  invalidateDocumentsKbFoldersCache,
  readDocumentsKbFoldersCache,
  readDocumentsListCache,
  writeDocumentsKbFoldersCache,
  writeDocumentsListCache } from "../utils/documentsViewCache.js";
import { renderIconAction } from "../utils/tableIconActions";
import { renderKnowledgeIndexTag, isDocumentIndexReady } from "../utils/knowledgeIndex.js";
import { notifyKnowledgeScopeTreeStale } from "../utils/knowledgeScopeRefresh.js";
import { isRouteAbortError } from "../api/requestScope.js";
import {
  createDocument,
  createKbFolder,
  deleteKbFolder,
  fetchDocuments,
  fetchKbFolders,
  prepareUpload,
  uploadDocumentBlob,
  completeUpload,
  batchDeleteDocuments,
  deleteDocument,
  updateKbFolder } from "../api/documents.js";
import { fetchReindexUnindexedDocuments as reindexUnindexedDocuments } from "../api/knowledge.js";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";

const route = useRoute();
const { isSystemAdmin, user } = useAuth();
const router = useRouter();
const { t, scopeLabel, locale, docStatusLabel, docLevelLabel } = useI18n();
const ui = usePlatformUi();
const { setHeaderTitle, clearHeaderTitle } = usePageHeader();
const { loadDocumentLibrary, invalidateDocumentLibrary } = useDocumentLibrary();

const loading = ref(false);
const keyword = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);
const appliedSearch = ref("");
const page = ref(1);
const pageSize = ref(LIST_PAGE_SIZE);
const total = ref(0);
const items = ref([]);
const folders = ref([]);
const activeScope = ref("personal");
/** null | __uncategorized__ | folder-uuid */
const activeKbFolderKey = ref(null);
const kbFolders = ref([]);
const kbFoldersLoading = ref(false);
const kbCanManageFolders = ref(false);
const refreshing = ref(false);
const reindexingUnindexed = ref(false);
const { headerExtensionActive } = usePageHeaderExtension();
const headerTeleportReady = ref(false);

onMounted(() => {
  nextTick(() => {
    headerTeleportReady.value = true;
  });
});
const uploadMaxMb = computed(() => getDocumentUploadMaxMb());
const activeDeptId = ref(null);
/** 系统管理员在个人级 Tab 下切换查看的账户 */
const activeOwnerId = ref(null);
const personalOwners = ref([]);
/** main */
const libraryView = ref("main");
const companies = ref([]);
const departments = ref([]);
const teams = ref([]);

const VIRTUAL_UNCATEGORIZED = "__uncategorized__";
/** 忽略过期的 load / loadKbFolders 结果，避免切换分级时串数据 */
let kbFoldersLoadSeq = 0;
let documentsLoadSeq = 0;
/** openKbFolder 已主动 load 时，跳过 route watch 的重复请求 */
let skipNextRouteLoad = false;
const prefetchingFolderKeys = new Set();
/** 列表中存在「解析中」文档时后台刷新索引状态 */
let indexStatusPollTimer = null;
let indexRefreshDebounceTimer = null;
const INDEX_STATUS_POLL_MS = 5000;

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

const showPublishDoc = ref(false);
const publishDocIds = ref([]);

const checkedRowKeys = ref([]);

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
const activeFolder = computed(() =>
  folders.value.find((f) => f.scope === activeScope.value)
);

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
  all: "primary"};

/** 内置文件夹 → 用户文件夹（同组内保持 API 原序） */
function sortKbFoldersForDisplay(items) {
  const systemOrder = {
    uncategorized: 0,
    shared: 1,
    web_favorites: 2,
    normal: 3,
  };
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

function kbFoldersCacheParams() {
  const deptId =
    ORG_SCOPES.includes(activeScope.value) && activeDeptId.value
      ? activeDeptId.value
      : null;
  return { deptId, ownerId: personalOwnerParam() };
}

/** 将新建文件夹合并进列表，避免列表接口缓存尚未失效时 UI 不更新 */
function mergeCreatedKbFolder(items, folder) {
  if (!folder?.id) return items || [];
  const id = String(folder.id);
  const normalized = {
    id: folder.id,
    virtual_id: null,
    name: folder.name,
    description: folder.description || "",
    scope: folder.scope || activeScope.value,
    dept_id: folder.dept_id ?? null,
    kind: folder.kind || "normal",
    is_system: false,
    system_hint: null,
    document_count: folder.document_count ?? 0,
    can_manage: folder.can_manage ?? true,
  };
  const rest = (items || []).filter(
    (item) => item?.id == null || String(item.id) !== id
  );
  return [...rest, normalized];
}

function applyCreatedKbFolderToView(folder) {
  kbFolders.value = sortKbFoldersForDisplay(
    mergeCreatedKbFolder(kbFolders.value, folder)
  );
  const { deptId, ownerId } = kbFoldersCacheParams();
  writeDocumentsKbFoldersCache(activeScope.value, deptId, ownerId, {
    scope: activeScope.value,
    dept_id: deptId,
    can_manage_folders: kbCanManageFolders.value,
    items: kbFolders.value,
  });
}

const isMainView = computed(() => libraryView.value === "main");
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
const isInsideKbFolder = computed(
  () =>
    isMainView.value &&
    usesKbFolders.value &&
    Boolean(activeKbFolderKey.value) &&
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
  () => isMainView.value
);

const showBatchDocActions = computed(
  () =>
    isMainView.value &&
    !isSearchMode.value &&
    !showKbFolderList.value &&
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

const columns = computed(() => {
  locale.value;
  const base = [];
  if (showBatchDocActions.value) {
    base.push({
      type: "selection",
      disabled: (row) => !canBatchSelectDocument(row)});
  }
  base.push({
    title: t("documents.columns.title"),
    key: "title",
    ellipsis: { tooltip: true },
    render: (row) => h("span", { class: "documents-doc-title" }, row.title || "—"),
  });
  base.push({
    title: t("documents.columns.format"),
    key: "file_format",
    width: 106,
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
    width: 115,
    render: (row) => renderKnowledgeIndexTag(row)});
  if (!isSearchMode.value) {
    base.push({
      title: t("documents.columns.status"),
      key: "status",
      width: 108,
      render: (row) => {
        const label = docStatusLabel(row.status) || row.status;
        if (!label || label === "—") return "—";
        return h(NTag, { size: "small", bordered: false }, { default: () => label });
      }});
  }
  if (isSearchMode.value || activeScope.value === "all") {
    base.push(
      {
        title: t("documents.columns.scope"),
        key: "scope",
        width: 108,
        render: (row) => scopeLabel(row.scope) || row.scope},
      {
        title: t("documents.columns.folder"),
        key: "folder_name",
        width: 144,
        ellipsis: { tooltip: true },
        render: (row) => row.folder_name || "—"},
      {
        title: t("documents.columns.owner"),
        key: "owner_name",
        width: 144,
        render: (row) => row.owner_name || t("documents.unknownUser")},
      {
        title: t("documents.columns.dept"),
        key: "dept_name",
        width: 132,
        render: (row) =>
          ORG_SCOPES.includes(row.scope) ? row.dept_name || "—" : "—"},
      {
        title: t("documents.columns.myPermission"),
        key: "effective_level",
        width: 108,
        render: (row) => docLevelLabel(row.effective_level) || row.effective_level || "—"}
    );
  } else if (isSharedScopeTab.value) {
    base.push(
      {
        title: t("documents.columns.sharer"),
        key: "owner_name",
        width: 144,
        render: (row) => row.owner_name || t("documents.unknownUser")},
      {
        title: t("documents.columns.grantedBy"),
        key: "granted_by_name",
        width: 202,
        render: (row) => row.granted_by_name || "—"},
      {
        title: t("documents.columns.myPermission"),
        key: "shared_level",
        width: 108,
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
        width: 144,
        render: (row) => row.dept_name || "—"},
      {
        title: t("documents.columns.owner"),
        key: "owner_name",
        width: 202,
        render: (row) => row.owner_name || t("documents.unknownUser")}
    );
  }
  base.push(
    {
      title: t("documents.columns.updatedAt"),
      key: "updated_at",
      width: 216,
      render: (row) => new Date(row.updated_at).toLocaleString()},
    {
      title: t("documents.columns.actions"),
      key: "actions",
      width: 86,
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
  libraryView.value = "main";
  const resolvedScope = resolveScopeFromRouteQuery();
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

async function loadFolders({ force = false } = {}) {
  try {
    const lib = await loadDocumentLibrary({ force });
    applyLibraryData(lib);
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
  if (
    libraryView.value === "main" &&
    folders.value.length &&
    !folders.value.find((f) => f.scope === activeScope.value)
  ) {
    activeScope.value = folders.value[0].scope;
  }
}

async function loadKbFolders({ force = false, background = false } = {}) {
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
  if (!force && !background) {
    const cached = readDocumentsKbFoldersCache(activeScope.value, deptId, ownerId);
    if (cached) {
      if (seq !== kbFoldersLoadSeq) return;
      kbFolders.value = sortKbFoldersForDisplay(cached.items || []);
      kbCanManageFolders.value = !!cached.can_manage_folders;
      kbFoldersLoading.value = false;
      void loadKbFolders({ force: true, background: true });
      return;
    }
  }
  const hadFolders = kbFolders.value.length > 0;
  if (!background && !hadFolders) kbFoldersLoading.value = true;
  try {
    const params = { scope: activeScope.value };
    if (deptId) params.dept_id = deptId;
    if (ownerId) params.owner_id = ownerId;
    const data = await fetchKbFolders(params);
    if (seq !== kbFoldersLoadSeq) return;
    const nextItems = sortKbFoldersForDisplay(data.items || []);
    if (background && hadFolders && !nextItems.length) return;
    writeDocumentsKbFoldersCache(activeScope.value, deptId, ownerId, data);
    kbFolders.value = nextItems;
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
  if (isSharedScopeTab.value) {
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
    const data = await fetchDocuments(buildFolderDocParams(key, 1));
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
  clearDocumentsViewCache();
  notifyKnowledgeScopeTreeStale();
  try {
    await Promise.all([loadFolders({ force: true }), loadKbFolders({ force: true })]);
    await load({ force: true });
  } catch (e) {
    ui.error(e);
  } finally {
    refreshing.value = false;
  }
}

function handleReindexUnindexed() {
  if (reindexingUnindexed.value) return;
  ui.confirmAction({
    title: t("documents.reindexUnindexedTitle"),
    content: t("documents.reindexUnindexedConfirm"),
    positiveText: t("documents.reindexUnindexedConfirmAction"),
    onPositive: () => {
      reindexingUnindexed.value = true;
      doReindexUnindexed();
    },
  });
}

async function doReindexUnindexed() {
  try {
    const params = { scope: activeScope.value };
    if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
      params.deptId = activeDeptId.value;
    }
    if (activeScope.value === "personal") {
      params.ownerId = activeOwnerId.value || user.value?.id;
    }
    const res = await reindexUnindexedDocuments(params);
    const data = res.data || {};
    const queued = data.queued ?? 0;
    if (queued > 0) {
      ui.success("documents.reindexUnindexedSuccess", { count: queued });
      clearDocumentsViewCache();
      notifyKnowledgeScopeTreeStale();
      void load({ force: true, background: true });
    } else {
      ui.info("documents.reindexUnindexedNone");
    }
  } catch (e) {
    ui.error(e);
  } finally {
    reindexingUnindexed.value = false;
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

function toggleSearch() {
  searchOpen.value = !searchOpen.value;
  if (searchOpen.value) {
    nextTick(() => searchInputRef.value?.focus?.());
  } else {
    keyword.value = "";
    appliedSearch.value = "";
    page.value = 1;
    if (isMainView.value) load();
  }
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
    if (isSharedScopeTab.value) {
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
    const nextItems = data.items || [];
    const nextTotal = data.total ?? 0;
    if (background && hadItems && !nextItems.length && nextTotal === 0) return;
    items.value = nextItems;
    total.value = nextTotal;
    writeDocumentsListCache(listCacheKey, data);
    scheduleIndexStatusPoll();
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
  if (!id) return;
  void navigateWithReturn(
    router,
    { name: "document-detail", params: { id: String(id) } },
    route
  ).catch((err) => {
    if (err?.name === "NavigationDuplicated") return;
    ui.error(err);
  });
}

function listHasIndexingItems(rows = items.value) {
  return (rows || []).some((row) => {
    if (isDocumentIndexReady(row)) return false;
    if (!row?.knowledge_synced) return true;
    const status = row.parse_status || "";
    return !status || status === "解析中" || status === "未解析";
  });
}

function stopIndexStatusPoll() {
  if (indexStatusPollTimer) {
    clearTimeout(indexStatusPollTimer);
    indexStatusPollTimer = null;
  }
}

function scheduleIndexStatusPoll() {
  stopIndexStatusPoll();
  if (!isMainView.value || isSearchMode.value || !listHasIndexingItems()) return;
  indexStatusPollTimer = setTimeout(async () => {
    indexStatusPollTimer = null;
    await load({ force: true, background: true });
    if (listHasIndexingItems()) scheduleIndexStatusPoll();
  }, INDEX_STATUS_POLL_MS);
}

function onKnowledgeIndexUpdated() {
  if (refreshing.value) return;
  if (indexRefreshDebounceTimer) clearTimeout(indexRefreshDebounceTimer);
  indexRefreshDebounceTimer = setTimeout(() => {
    indexRefreshDebounceTimer = null;
    clearDocumentsViewCache();
    void load({ force: true, background: true });
    scheduleIndexStatusPoll();
  }, 400);
}

function documentRowProps(row) {
  return {
    style: "cursor: pointer",
    onClick: (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (
        target.closest(
          ".n-checkbox, .n-button, .table-icon-actions, .n-dropdown, .n-data-table-expand-trigger"
        )
      ) {
        return;
      }
      openDocumentDetail(row.id);
    },
  };
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

async function openKbFolder(folder) {
  const key = folder.virtual_id || (folder.id ? String(folder.id) : null);
  if (!key) return;
  keyword.value = "";
  appliedSearch.value = "";
  activeKbFolderKey.value = key;
  page.value = 1;
  checkedRowKeys.value = [];
  applyCachedListForActiveFolder();
  skipNextRouteLoad = true;
  try {
    await router.replace({ name: "documents", query: buildLibraryQuery() });
  } catch (err) {
    if (err?.name !== "NavigationDuplicated") {
      ui.error(err);
      return;
    }
  }
  void load();
}

async function backToKbFolders() {
  activeKbFolderKey.value = null;
  page.value = 1;
  items.value = [];
  total.value = 0;
  loading.value = false;
  checkedRowKeys.value = [];
  const query = { ...buildLibraryQuery() };
  delete query.folder;
  skipNextRouteLoad = true;
  try {
    await router.replace({ name: "documents", query });
  } catch (err) {
    if (err?.name !== "NavigationDuplicated") ui.error(err);
  }
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
  const { deptId, ownerId } = kbFoldersCacheParams();
  try {
    const payload = {
      name,
      description: createFolderDesc.value.trim(),
      scope: activeScope.value};
    if (ORG_SCOPES.includes(activeScope.value) && activeDeptId.value) {
      payload.dept_id = activeDeptId.value;
    }
    const folder = await createKbFolder(payload);
    applyCreatedKbFolderToView(folder);
    invalidateDocumentsKbFoldersCache(activeScope.value, deptId, ownerId);
    notifyKnowledgeScopeTreeStale();
    ui.success("documents.messages.folderCreated");
    showCreateFolder.value = false;
    await loadKbFolders({ force: true });
    applyCreatedKbFolderToView(folder);
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
  parts.push(t("documents.folderDocCount", { count: folder.document_count ?? 0 }));
  if (folder.is_system && folder.system_hint) parts.push(folder.system_hint);
  return parts.join("\n");
}

function folderMenuOptions(folder) {
  if (!folder.can_manage || !folder.id || folder.is_system) return [];
  return [
    {
      label: t("common.edit"),
      key: "edit",
      icon: () => h(NIcon, null, { default: () => h(CreateOutline) })},
    {
      label: t("common.delete"),
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

function openBatchPublish() {
  if (!canBatchPublish.value) return;
  publishDocIds.value = selectedRows.value.map((row) => row.id);
  showPublishDoc.value = true;
}

function onDocumentPublished() {
  showPublishDoc.value = false;
  publishDocIds.value = [];
  checkedRowKeys.value = [];
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
    ui.confirmAction({
      title: t("common.delete"),
      content: t("documents.confirm.deleteFolder"),
      positiveText: t("common.delete"),
      onPositive: () => onDeleteKbFolder(folder),
    });
  }
}

function backToLibrary() {
  libraryView.value = "main";
  page.value = 1;
  router.replace({ name: "documents", query: buildLibraryQuery() });
}

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
    sameContext &&
    activeKbFolderKey.value
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
    scope: createScope.value};
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
  window.addEventListener(KNOWLEDGE_INDEX_UPDATED_EVENT, onKnowledgeIndexUpdated);
  void loadFolders();
  void loadKbFolders();
  void load();
});

onUnmounted(() => {
  showCreateFolder.value = false;
  showUploadModal.value = false;
  clearHeaderTitle();
  stopIndexStatusPoll();
  if (indexRefreshDebounceTimer) clearTimeout(indexRefreshDebounceTimer);
  window.removeEventListener(KNOWLEDGE_INDEX_UPDATED_EVENT, onKnowledgeIndexUpdated);
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
    void loadKbFolders();
    void load();
  }
);
</script>

<template>
  <div class="documents-page feature-page">
    <Teleport
      v-if="headerTeleportReady && headerExtensionActive"
      to="#header-actions-row"
    >
      <div class="documents-actions-bar">
        <div class="documents-actions-toolbar">
          <!-- 核心操作：上传 / 重新构建 + 搜索 -->
          <div class="documents-actions-core">
            <IconAction
              v-if="isMainView && usesKbFolders && !isSearchMode && hasAnyCreatableScope"
              :label="t('documents.uploadDoc')"
              :icon="CloudUploadOutline"
              @click="openUploadModal('single')"
            />
            <IconAction
              v-if="isMainView && !isSearchMode"
              :label="t('documents.indexAction')"
              :tooltip="t('documents.reindexUnindexedTitle')"
              :icon="ConstructOutline"
              :loading="reindexingUnindexed"
              :disabled="reindexingUnindexed"
              @click="handleReindexUnindexed"
            />
            <IconAction
              :label="t('common.search')"
              :icon="SearchOutline"
              @click="toggleSearch"
            />
            <n-input
              v-show="searchOpen"
              v-model:value="keyword"
              :placeholder="t('documents.searchPlaceholder')"
              clearable
              size="small"
              class="documents-search"
              @keyup.enter="runSearch"
              @clear="clearSearch"
              ref="searchInputRef"
            />
          </div>
          <!-- 导航/后退按钮 -->
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
          <!-- 筛选控件 -->
          <template v-if="isMainView && !isSearchMode">
            <n-select
              v-if="showOwnerPicker"
              :value="activeOwnerId"
              :options="ownerOptions"
              size="small"
              :placeholder="t('documents.ownerSelectPlaceholder')"
              class="documents-org-picker__select"
              @update:value="onOwnerChange"
            />
            <n-select
              v-if="showOrgPicker"
              :value="activeDeptId"
              :options="deptOptions"
              size="small"
              :placeholder="orgUnits.length > 1 ? t('documents.deptSelectPlaceholder') : undefined"
              class="documents-org-picker__select"
              @update:value="onDeptChange"
            />
          </template>
        </div>
      </div>
    </Teleport>
    <Teleport
      v-if="headerTeleportReady && headerExtensionActive"
      to="#header-page-tools"
    >
      <n-button
        quaternary
        circle
        size="tiny"
        class="header-icon-btn"
        :class="{ 'header-icon-btn--spinning': refreshing }"
        :aria-label="t('common.refresh')"
        :disabled="refreshing"
        @click="refreshDocumentsView"
      >
        <n-icon :size="13" :component="RefreshOutline" />
      </n-button>
    </Teleport>

    <div v-if="isSearchMode" class="documents-search-results-head">
      <n-text depth="2">
        {{ t("documents.searchResults", { count: total, keyword: appliedSearch }) }}
      </n-text>
    </div>
    <div
      v-if="isMainView && !isSearchMode"
      class="documents-scope-tabs"
    >
      <n-tabs
        v-model:value="activeScope"
        type="line"
        animated
        @update:value="onTabChange"
      >
        <n-tab-pane
          v-for="f in folders"
          :key="f.scope"
          :name="f.scope"
        >
          <template #tab>
            <span>{{ scopeLabel(f.scope) || f.label }}</span>
            <n-tag
              v-if="!f.can_create"
              size="tiny"
              :bordered="false"
              style="margin-left:4px;flex-shrink:0"
            >
              {{ t("menu.readOnly") }}
            </n-tag>
          </template>
        </n-tab-pane>
      </n-tabs>
    </div>

    <Transition name="doc-view" mode="out-in">
    <PlatformSpin
      v-if="showKbFolderList"
      key="folder-grid"
      :show="kbFoldersLoading"
      class="documents-view-spin"
      local
    >
      <n-empty
        v-if="!kbFolders.length && !canManageKbFolders"
        :description="t('documents.emptyFolders')"
      />
      <div v-else class="kb-folder-explorer">
        <div
          v-for="(folder, folderIdx) in kbFolders"
          :key="folder.virtual_id || folder.id"
          class="kb-folder-explorer__cell"
          :style="{ '--folder-i': folderIdx }"
          @mouseenter="prefetchFolderDocuments(folder)"
        >
          <KbFolderCard
            :folder="folder"
            :title="folderTooltip(folder)"
            :card-key="folder.virtual_id || folder.id || `f-${folderIdx}`"
            :menu-options="folderMenuOptions(folder)"
            @open="openKbFolder"
            @menu-select="onFolderMenuSelect"
          />
        </div>
        <div
          v-if="canManageKbFolders"
          class="kb-folder-explorer__cell"
          :style="{ '--folder-i': kbFolders.length }"
        >
          <KbFolderCreateCard @create="openCreateFolder" />
        </div>
      </div>
    </PlatformSpin>

    <div v-else key="doc-list" class="documents-list-panel">
    <!-- 文件夹内操作栏：在卡片上方显示 -->
    <div v-if="showTopFolderBatchActions" class="documents-folder-toolbar">
      <IconAction :label="t('documents.backToFolders')" :icon="ArrowBackOutline" @click="backToKbFolders" />
      <span class="documents-folder-toolbar__name">{{ activeKbFolderLabel }}</span>
      <div class="folder-action-pills">
        <NButton quaternary size="tiny" class="folder-action-btn" :disabled="!canBatchPublish" @click="openBatchPublish">
          <template #icon><NIcon :component="RocketOutline" /></template>
          {{ t("documents.detail.publishToLibrary") }}
        </NButton>
        <NButton quaternary size="tiny" class="folder-action-btn" :disabled="!canBatchMove" @click="openBatchMove">
          {{ t("common.move") }}
        </NButton>
        <NButton quaternary size="tiny" class="folder-action-btn folder-action-btn--danger" :disabled="!canBatchDelete" @click="handleBatchDelete">
          <template #icon><NIcon :component="TrashOutline" /></template>
          {{ t("common.delete") }}
        </NButton>
      </div>
    </div>
    <div v-if="showBottomBatchToolbar" class="doc-list-toolbar page-toolbar">
      <n-space align="center" :size="7">
        <IconAction
          :label="t('documents.detail.publishToLibrary')"
          :icon="RocketOutline"
          :disabled="!canBatchPublish"
          @click="openBatchPublish"
        />
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

        <n-card class="documents-list-card" :bordered="true">
    <PlatformSpin :show="loading && !items.length" class="documents-view-spin" local>
      <n-data-table
        class="documents-table"
        :columns="columns"
        :data="items"
        :row-key="(row) => row.id"
        :row-props="documentRowProps"
        :checked-row-keys="showBatchDocActions ? checkedRowKeys : undefined"
        @update:checked-row-keys="onCheckedRowKeysChange"
        :pagination="false"
      />
    </PlatformSpin>
    </n-card>
    </div>
    </Transition>

    <ListTableFooter
      v-if="!showKbFolderList"
      :page="page"
      :page-size="pageSize"
      :item-count="total"
      @update:page="onPageChange"
    />
  </div>

  <AdminFormModal
    v-model:show="showUploadModal"
    class="documents-upload-modal"
    :title="t('documents.uploadModalTitle')"
    width="min(480px, 94vw)"
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

    <n-form
      class="documents-upload-modal__form admin-form-modal__form admin-form-modal__form--compact"
      label-placement="top"
      @submit.prevent
    >
      <DocumentUploadLocationPicker
        v-model:scope="createScope"
        v-model:dept-id="createDeptId"
        v-model:owner-id="createOwnerId"
        v-model:folder-id="createFolderId"
        :library-folders="folders"
        :companies="companies"
        :departments="departments"
        :teams="teams"
        :personal-owners="personalOwners"
        :is-system-admin="isSystemAdmin"
        @folders-changed="onUploadLocationFoldersChanged"
      />

      <template v-if="uploadMode === 'single'">
        <n-form-item :label="t('documents.uploadFileLabel')" required>
          <file-drop-zone
            class="documents-upload-modal__file-picker"
            compact
            hide-button
            :accept="DOCUMENT_UPLOAD_ACCEPT"
            :title="t('documents.uploadDropHint')"
            :hint="t('documents.uploadSizeHint', { mb: uploadMaxMb })"
            :file-name="uploadFile?.name || ''"
            :disabled="creating"
            @change="onSingleFileDropChange"
          />
        </n-form-item>
      </template>

      <template v-else>
        <n-form-item :label="t('documents.uploadFileLabel')" required>
          <n-upload
            :key="batchUploadKey"
            v-model:file-list="batchUploadFileList"
            multiple
            :accept="DOCUMENT_UPLOAD_ACCEPT"
            :default-upload="false"
            :show-file-list="false"
            @change="onBatchFileChange"
          >
            <n-upload-dragger
              class="documents-upload-modal__dropzone"
              :class="{ 'documents-upload-modal__dropzone--ready': batchUploadFiles.length }"
            >
              <div class="documents-upload-modal__dropzone-inner">
                <n-icon :size="28" :component="CloudUploadOutline" class="documents-upload-modal__dropzone-icon" />
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
      <n-space justify="end" :size="8">
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
          :disabled="!batchUploadFiles.length || !canSubmitUploadLocation"
          @click="submitBatchUpload"
        >
          {{ t("documents.uploadSubmitBatch", { count: batchUploadFiles.length || 0 }) }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>

  <AdminFormModal
    v-model:show="showCreateFolder"
    :title="t('documents.folderForm.createTitle')"
    :subtitle="t('documents.folderForm.createSubtitle')"
    width="480px"
  >
    <n-form label-placement="top">
      <n-form-item :label="t('documents.folderForm.nameLabel')" required>
        <n-input
          v-model:value="createFolderName"
          :placeholder="t('documents.folderForm.namePlaceholder')"
          @keyup.enter="submitCreateFolder"
        />
      </n-form-item>
      <n-form-item :label="t('documents.folderForm.descLabel')">
        <n-input
          v-model:value="createFolderDesc"
          type="textarea"
          :placeholder="t('documents.folderForm.descPlaceholder')"
          :autosize="{ minRows: 2, maxRows: 5 }"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showCreateFolder = false">{{ t("common.cancel") }}</n-button>
        <n-button type="primary" :loading="savingFolder" @click="submitCreateFolder">
          {{ t("common.create") }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>

  <AdminFormModal
    :show="!!editFolderTarget"
    :title="t('documents.folderForm.editTitle')"
    :subtitle="t('documents.folderForm.editSubtitle')"
    width="576px"
    @update:show="(v) => { if (!v) editFolderTarget = null; }"
  >
    <n-form label-placement="top">
      <n-form-item :label="t('documents.folderForm.nameLabel')" required>
        <n-input v-model:value="editFolderName" @keyup.enter="submitEditFolder" />
      </n-form-item>
      <n-form-item :label="t('documents.folderForm.descLabel')">
        <n-input
          v-model:value="editFolderDesc"
          type="textarea"
          :placeholder="t('documents.folderForm.editDescPlaceholder')"
          :autosize="{ minRows: 2, maxRows: 6 }"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="editFolderTarget = null">{{ t("common.cancel") }}</n-button>
        <n-button type="primary" :loading="savingFolder" @click="submitEditFolder">
          {{ t("common.save") }}
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>

  <BatchPublishModal
    v-if="showPublishDoc && publishDocIds.length"
    v-model:show="showPublishDoc"
    :document-ids="publishDocIds"
    @published="onDocumentPublished"
  />

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

/* ── 文件夹内操作按钮 ── */
.documents-folder-toolbar .folder-action-btn.n-button.n-button--quaternary-type {
  width: auto !important;
  padding: 0 10px !important;
  border-radius: 6px !important;
  font-size: var(--platform-font-size-sm) !important;
  line-height: 1 !important;
  --n-height: 28px;
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-surface);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.documents-folder-toolbar .folder-action-btn.n-button.n-button--quaternary-type:not(:disabled):hover {
  background: var(--platform-bg-tertiary);
  border-color: var(--platform-accent);
}
.documents-folder-toolbar .folder-action-btn--danger.n-button.n-button--quaternary-type:not(:disabled) {
  color: var(--platform-danger);
}
.documents-folder-toolbar .folder-action-btn--danger.n-button.n-button--quaternary-type:not(:disabled):hover {
  color: var(--platform-danger);
  background: var(--platform-danger-soft);
  border-color: var(--platform-danger);
}

.documents-doc-title {
  font-size: 15px;
}

/* 文档表格 — 参照多智能体技能表格样式 */
.documents-table :deep(.n-data-table-thead .n-data-table-th) {
  font-size: 15px !important;
  font-weight: 500 !important;
  color: var(--platform-text) !important;
  border-bottom: 1px solid var(--platform-border-light, #e8e8e8) !important;
}
.documents-table :deep(.n-data-table-tbody .n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-light, #e8e8e8) !important;
  font-size: 13px;
}

.documents-scope-tabs :deep(.n-tabs-tab-panes) {
  display: none;
}

/* ── 文档中心 Tab 滚动容器 ── */
.documents-scope-tabs :deep(.n-tabs-nav-scroll-wrapper) {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.documents-scope-tabs :deep(.n-tabs-nav-scroll-wrapper)::-webkit-scrollbar {
  display: none;
}

/* ── 文件夹内操作按钮在移动端可横向滚动 ── */
.documents-folder-toolbar .folder-action-pills {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  flex-shrink: 0;
}
.documents-folder-toolbar .folder-action-pills::-webkit-scrollbar {
  display: none;
}

/* =============================================
 * 移动端适配
 * ============================================= */
@media (max-width: 768px) {
  /* 1. 表格可水平滚动 */
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

  /* 2. 隐藏非核心列（索引状态、状态、范围、文件夹等） */
  .documents-table :deep(.n-data-table-th):nth-child(3), /* 索引 */
  .documents-table :deep(.n-data-table-td):nth-child(3),
  .documents-table :deep(.n-data-table-th):nth-child(4), /* 状态 */
  .documents-table :deep(.n-data-table-td):nth-child(4) {
    display: none;
  }

  /* 搜索结果或 all 范围模式下显示更多列，但也隐藏一些次要列 */
  .documents-table :deep(.n-data-table-th):nth-child(7), /* 部门 */
  .documents-table :deep(.n-data-table-td):nth-child(7),
  .documents-table :deep(.n-data-table-th):nth-child(8), /* 权限 */
  .documents-table :deep(.n-data-table-td):nth-child(8) {
    display: none;
  }

  /* 3. 文件标题列宽度自适应 */
  .documents-doc-title {
    font-size: 13px !important;
    max-width: 36vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: block;
  }

  /* 4. 文件夹网格紧凑 */
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

  /* 5. 工具栏折叠 */
  .documents-actions-toolbar {
    gap: 4px !important;
    flex-wrap: wrap;
  }
  .documents-actions-core {
    flex-wrap: wrap;
    gap: 4px !important;
  }

  /* 6. 文件夹工具栏紧凑 */
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

  /* 7. 搜索框全宽 */
  .documents-search {
    width: 100% !important;
  }

  /* 8. 分页脚紧凑 */
  .list-table-footer {
    padding: 10px;
  }

  /* 9. 上传弹窗全屏 */
  .documents-upload-modal.n-modal :deep(.n-card) {
    width: 100vw !important;
    max-width: 100vw !important;
    height: 100vh;
    max-height: 100vh;
    border-radius: 0 !important;
    margin: 0;
  }
  .documents-upload-modal.n-modal :deep(.n-card__content) {
    flex: 1;
    overflow-y: auto;
  }

  /* 10. Tab 栏更紧凑 */
  .documents-scope-tabs :deep(.n-tabs-nav) {
    padding: 0 4px;
  }
  .documents-scope-tabs :deep(.n-tabs-tab) {
    font-size: 12px;
    padding: 8px 8px;
  }
  .documents-scope-tabs {
    margin-bottom: 0;
  }

  /* 11. 操作栏筛选控件全宽 */
  .documents-org-picker__select {
    width: 100% !important;
    min-width: 0 !important;
  }

  /* 12. 文件夹创建卡片紧凑 */
  .kb-folder-create-card {
    padding: 8px 6px 10px;
  }

  /* 13. 桌面端的分页脚相对定位 */
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

  .documents-folder-toolbar .folder-action-btn.n-button.n-button--quaternary-type {
    font-size: 11px !important;
    padding: 0 6px !important;
    height: 26px !important;
  }

  .documents-table :deep(.n-data-table-th):nth-child(5), /* scope */
  .documents-table :deep(.n-data-table-td):nth-child(5),
  .documents-table :deep(.n-data-table-th):nth-child(6), /* folder */
  .documents-table :deep(.n-data-table-td):nth-child(6) {
    display: none;
  }
}
</style>

