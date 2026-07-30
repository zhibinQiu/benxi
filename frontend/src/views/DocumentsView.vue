<script setup>
defineOptions({ name: "DocumentsView" });
import { computed, h, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NSpace,
  NInput,
  NForm,
  NFormItem,
  NTabs,
  NTabPane,
  NSelect,
  NTag,
  NText,
} from "naive-ui";
import {
  ArrowBackOutline,
  SearchOutline,
  CloudUploadOutline,
  EyeOutline,
  ConstructOutline,
  RefreshOutline,
} from "@vicons/ionicons5";
import MoveDocumentFolderModal from "../components/MoveDocumentFolderModal.vue";
import BatchPublishModal from "../components/BatchPublishModal.vue";
import DocumentsFolderSection from "../components/documents/DocumentsFolderSection.vue";
import DocumentsTableSection from "../components/documents/DocumentsTableSection.vue";
import DocumentsUploadModal from "../components/documents/DocumentsUploadModal.vue";
import IconAction from "../components/IconAction.vue";
import AdminFormModal from "../components/AdminFormModal.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { KNOWLEDGE_INDEX_UPDATED_EVENT } from "../constants/platformEvents.js";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeader } from "../composables/usePageHeader";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { useDocumentLibrary } from "../composables/useDocumentLibrary.js";
import {
  useDocumentUpload,
  VIRTUAL_UNCATEGORIZED,
} from "../composables/useDocumentUpload.js";
import { useDocumentBatchActions } from "../composables/useDocumentBatchActions.js";
import {
  ORG_SCOPES,
  LIBRARY_FOLDER_ORDER } from "../constants/documentScope";
import { canBatchSelectDocument } from "../utils/documentCaps.js";
import {
  clearDocumentsViewCache,
  invalidateDocumentsKbFoldersCache,
  readDocumentsFolderViewMode,
  readDocumentsKbFoldersCache,
  readDocumentsListCache,
  writeDocumentsFolderViewMode,
  writeDocumentsKbFoldersCache,
  writeDocumentsListCache } from "../utils/documentsViewCache.js";
import DocumentFileIcon from "../components/DocumentFileIcon.vue";
import { renderIconAction } from "../utils/tableIconActions";
import { knowledgeIndexTagProps, isDocumentIndexReady } from "../utils/knowledgeIndex.js";
import { notifyKnowledgeScopeTreeStale } from "../utils/knowledgeScopeRefresh.js";
import {
  createKbFolder,
  deleteKbFolder,
  fetchDocuments,
  fetchKbFolders,
  updateKbFolder } from "../api/documents.js";
import { fetchReindexUnindexedDocuments as reindexUnindexedDocuments } from "../api/knowledge.js";

/** 列表视图每页条数 */
const DOCUMENTS_LIST_PAGE_SIZE = 6;
/** 图标视图：与网格约 6 列对齐，每页最多 2 行 */
const DOCUMENTS_ICON_PAGE_SIZE = 12;

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
const activeDeptId = ref(null);
/** 系统管理员在个人级 Tab 下切换查看的账户 */
const activeOwnerId = ref(null);
const personalOwners = ref([]);
/** main */
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

/** 文件夹内文档展示：list | icons */
const folderDocViewMode = ref(readDocumentsFolderViewMode());
const showFolderIconView = computed(
  () => isInsideKbFolder.value && folderDocViewMode.value === "icons"
);
const pageSize = computed(() =>
  showFolderIconView.value ? DOCUMENTS_ICON_PAGE_SIZE : DOCUMENTS_LIST_PAGE_SIZE
);

function setFolderDocViewMode(mode) {
  const next = mode === "icons" ? "icons" : "list";
  if (next === folderDocViewMode.value) return;
  folderDocViewMode.value = next;
  writeDocumentsFolderViewMode(next);
  page.value = 1;
  void load({ force: true });
}

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
    minWidth: 220,
    render: (row) => {
      const tag = knowledgeIndexTagProps(row);
      return h("div", { class: "documents-doc-title-cell" }, [
        h("span", { class: "documents-doc-icon-wrap" }, [
          h(DocumentFileIcon, { format: row.file_format || "", size: 26 }),
          h(
            "span",
            {
              class: ["doc-index-badge", `doc-index-badge--${tag.type}`],
              title: tag.label,
            },
            tag.label
          ),
        ]),
        h(
          "span",
          { class: "documents-doc-title", title: row.title || "" },
          row.title || "—"
        ),
      ]);
    },
  });
  base.push({
    title: t("documents.columns.uploadedAt"),
    key: "uploaded_at",
    width: 176,
    render: (row) => {
      const ts = row.uploaded_at || row.created_at;
      return ts ? new Date(ts).toLocaleString() : "—";
    }});
  if (!isSearchMode.value && !isInsideKbFolder.value) {
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
    // 进入文件夹后已限定组织单元，无需再显示所属分部/部门/公司
    if (!isInsideKbFolder.value) {
      base.push({
        title:
          activeScope.value === "company"
            ? t("documents.columns.company")
            : activeScope.value === "team"
              ? t("documents.columns.team")
              : t("documents.columns.department"),
        key: "dept_name",
        width: 144,
        render: (row) => row.dept_name || "—"});
    }
    base.push({
      title: t("documents.columns.owner"),
      key: "owner_name",
      width: 202,
      render: (row) => row.owner_name || t("documents.unknownUser")});
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
    content: t(
      isSystemAdmin.value
        ? "documents.reindexUnindexedConfirmAdmin"
        : "documents.reindexUnindexedConfirm"
    ),
    positiveText: t("documents.reindexUnindexedConfirmAction"),
    onPositive: () => {
      reindexingUnindexed.value = true;
      doReindexUnindexed();
    },
  });
}

async function doReindexUnindexed() {
  try {
    const data = await reindexUnindexedDocuments();
    const queued = data?.queued ?? 0;
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
    clearSelection();
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
  clearSelection();
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
  clearSelection();
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

const batchActions = useDocumentBatchActions({
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
});

const {
  checkedRowKeys,
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
} = batchActions;

const upload = useDocumentUpload({
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
});

const {
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
} = upload;

watch(activeScope, () => {
  if (isMainView.value) page.value = 1;
});

watch(libraryView, () => {
  clearSelection();
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
              v-if="!f.can_create && f.scope !== 'shared'"
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
      <DocumentsFolderSection
        v-if="showKbFolderList"
        key="folder-grid"
        :loading="kbFoldersLoading"
        :folders="kbFolders"
        :can-manage-folders="canManageKbFolders"
        @prefetch-folder="prefetchFolderDocuments"
        @open-folder="openKbFolder"
        @menu-select="onFolderMenuSelect"
        @create-folder="openCreateFolder"
      />

      <DocumentsTableSection
        v-else
        key="doc-list"
        :is-inside-kb-folder="isInsideKbFolder"
        :active-kb-folder-label="activeKbFolderLabel"
        :folder-doc-view-mode="folderDocViewMode"
        :show-top-folder-batch-actions="showTopFolderBatchActions"
        :show-bottom-batch-toolbar="showBottomBatchToolbar"
        :can-batch-publish="canBatchPublish"
        :can-batch-move="canBatchMove"
        :can-batch-delete="canBatchDelete"
        :show-folder-icon-view="showFolderIconView"
        :loading="loading"
        :items="items"
        :show-batch-doc-actions="showBatchDocActions"
        :checked-row-keys="checkedRowKeys"
        :deletable-selected-count="deletableSelectedRows.length"
        :columns="columns"
        :document-row-props="documentRowProps"
        :page="page"
        :page-size="pageSize"
        :total="total"
        @back-to-folders="backToKbFolders"
        @set-view-mode="setFolderDocViewMode"
        @batch-publish="openBatchPublish"
        @batch-move="openBatchMove"
        @batch-delete="handleBatchDelete"
        @update:checked-row-keys="onCheckedRowKeysChange"
        @icon-card-selected="onIconCardSelected"
        @open-document="openDocumentDetail"
        @update:page="onPageChange"
      />
    </Transition>
  </div>

  <DocumentsUploadModal
    v-model:show="showUploadModal"
    v-model:upload-mode="uploadMode"
    v-model:create-scope="createScope"
    v-model:create-dept-id="createDeptId"
    v-model:create-owner-id="createOwnerId"
    v-model:create-folder-id="createFolderId"
    v-model:batch-upload-file-list="batchUploadFileList"
    :folders="folders"
    :companies="companies"
    :departments="departments"
    :teams="teams"
    :personal-owners="personalOwners"
    :is-system-admin="isSystemAdmin"
    :upload-file="uploadFile"
    :creating="creating"
    :batch-upload-files="batchUploadFiles"
    :batch-uploading="batchUploading"
    :batch-progress="batchProgress"
    :batch-upload-key="batchUploadKey"
    :upload-max-mb="uploadMaxMb"
    :batch-upload-stats="batchUploadStats"
    :can-submit-single-upload="canSubmitSingleUpload"
    :can-submit-upload-location="canSubmitUploadLocation"
    :format-upload-file-size="formatUploadFileSize"
    @folders-changed="onUploadLocationFoldersChanged"
    @single-file-change="onSingleFileDropChange"
    @batch-file-change="onBatchFileChange"
    @clear-batch-selection="clearBatchUploadSelection"
    @close="closeUploadModal"
    @submit-single="submitCreate"
    @submit-batch="submitBatchUpload"
  />

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

<style src="../styles/pages/documents.css"></style>
<style scoped>
.documents-scope-tabs {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--platform-bg);
}
.documents-scope-tabs :deep(.n-tabs-tab--active) {
  color: var(--platform-accent) !important;
}
.documents-scope-tabs :deep(.n-tabs-tab):hover {
  color: var(--platform-accent) !important;
}
.documents-scope-tabs :deep(.n-tabs-bar) {
  display: none;
}
.documents-scope-tabs :deep(.n-tabs-tab-panes) {
  display: none;
}

.documents-scope-tabs :deep(.n-tabs-nav-scroll-wrapper) {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.documents-scope-tabs :deep(.n-tabs-nav-scroll-wrapper)::-webkit-scrollbar {
  display: none;
}

@media (max-width: 768px) {
  .documents-actions-toolbar {
    gap: 4px !important;
    flex-wrap: wrap;
  }
  .documents-actions-core {
    flex-wrap: wrap;
    gap: 4px !important;
  }

  .documents-search {
    width: 100% !important;
  }

  .documents-org-picker__select {
    width: 100% !important;
    min-width: 0 !important;
  }

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
}
</style>

