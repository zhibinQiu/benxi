<script setup>
import { computed, h, onMounted, ref, watch } from "vue";
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
  useMessage,
  useDialog,
} from "naive-ui";
import {
  CreateOutline,
  TrashOutline,
  ArrowBackOutline,
} from "@vicons/ionicons5";
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
import MoveDocumentFolderModal from "../components/MoveDocumentFolderModal.vue";
import KbFolderCard from "../components/KbFolderCard.vue";
import KbFolderCreateCard from "../components/KbFolderCreateCard.vue";
import { navigateWithReturn } from "../utils/navigationReturn";
import { useAuth } from "../composables/useAuth";
import {
  ORG_SCOPES,
  LIBRARY_FOLDER_ORDER,
  SCOPE_LABELS,
} from "../constants/documentScope";
import {
  DOCUMENT_UPLOAD_MAX_FILES,
  DOCUMENT_UPLOAD_MAX_MB,
  formatDocumentFormatLabel,
  titleFromFileName,
  validateUploadFiles,
} from "../constants/documentUpload";

const route = useRoute();
const { isSystemAdmin } = useAuth();
const router = useRouter();
const message = useMessage();
const dialog = useDialog();

const loading = ref(false);
const keyword = ref("");
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

const showCreate = ref(false);
const createTitle = ref("");
const createDesc = ref("");
const createScope = ref("personal");
const createDeptId = ref(null);
const uploadFile = ref(null);
const creating = ref(false);

const showBatchUpload = ref(false);
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

const STATUS_LABELS = {
  active: "启用",
  disabled: "关闭",
  draft: "草稿",
  archived: "归档",
};

const LEVEL_LABELS = {
  visible: "可见",
  query: "可查询",
  edit: "可编辑",
  full: "完全",
  read: "可见",
  use: "可编辑",
  delete: "完全",
};

const isMainView = computed(() => libraryView.value === "main");
const isRecycleView = computed(() => libraryView.value === "recycle");
const isMySharesView = computed(() => libraryView.value === "my-shares");
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
  () => usesKbFolders.value && !activeKbFolderKey.value
);
const isSharedFolderView = computed(
  () => activeKbFolderKey.value === VIRTUAL_SHARED
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
    !showKbFolderList.value &&
    !isSharedFolderView.value &&
    !isSharedScopeTab.value &&
    activeScope.value !== "all"
);

const showBatchRecycleActions = computed(() => isRecycleView.value);

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

const canBatchRecycleDelete = computed(
  () => showBatchRecycleActions.value && selectedRows.value.length > 0
);

const cardTitle = computed(() => {
  if (isRecycleView.value) return "回收站";
  if (isMySharesView.value) return "我的分享";
  return "文档中心";
});

const columns = computed(() => {
  const base = [];
  if (showBatchDocActions.value || showBatchRecycleActions.value) {
    base.push({
      type: "selection",
      disabled: (row) =>
        showBatchRecycleActions.value ? false : !row.can_edit && !row.can_delete,
    });
  }
  base.push({ title: "标题", key: "title", ellipsis: { tooltip: true } });
  if (!isRecycleView.value) {
    base.push({
      title: "格式",
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
        title: "状态",
        key: "status",
        width: 90,
        render: (row) => STATUS_LABELS[row.status] || row.status,
      },
      {
        title: "原分级",
        key: "scope",
        width: 90,
        render: (row) => SCOPE_LABELS[row.scope] || row.scope,
      },
      {
        title: "删除时间",
        key: "deleted_at",
        width: 180,
        render: (row) =>
          row.deleted_at ? new Date(row.deleted_at).toLocaleString() : "—",
      },
      {
        title: "操作",
        key: "actions",
        width: 100,
        render: (row) =>
          h(
            NButton,
            {
              text: true,
              type: "primary",
              onClick: () => handleRestore(row.id),
            },
            { default: () => "恢复" }
          ),
      }
    );
    return base;
  }
  if (isMySharesView.value) {
    base.push(
      {
        title: "分级",
        key: "scope",
        width: 90,
        render: (row) => SCOPE_LABELS[row.scope] || row.scope,
      },
      {
        title: "分享给",
        key: "share_to_summary",
        ellipsis: { tooltip: true },
        render: (row) => row.share_to_summary || "—",
      },
      {
        title: "更新时间",
        key: "updated_at",
        width: 180,
        render: (row) => new Date(row.updated_at).toLocaleString(),
      },
      {
        title: "操作",
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
            { default: () => "查看" }
          ),
      }
    );
    return base;
  }
  base.push({
    title: "状态",
    key: "status",
    width: 90,
    render: (row) => STATUS_LABELS[row.status] || row.status,
  });
  if (activeScope.value === "all") {
    base.push(
      {
        title: "分级",
        key: "scope",
        width: 90,
        render: (row) => SCOPE_LABELS[row.scope] || row.scope,
      },
      {
        title: "上传人",
        key: "owner_name",
        width: 120,
        render: (row) => row.owner_name || "未知用户",
      },
      {
        title: "所属部门",
        key: "dept_name",
        width: 110,
        render: (row) =>
          ORG_SCOPES.includes(row.scope) ? row.dept_name || "—" : "—",
      },
      {
        title: "我的权限",
        key: "effective_level",
        width: 90,
        render: (row) => LEVEL_LABELS[row.effective_level] || row.effective_level || "—",
      }
    );
  } else if (isSharedScopeTab.value || isSharedFolderView.value) {
    base.push(
      {
        title: "分享人",
        key: "owner_name",
        width: 120,
        render: (row) => row.owner_name || "未知用户",
      },
      {
        title: "授权人",
        key: "granted_by_name",
        width: 140,
        render: (row) => row.granted_by_name || "—",
      },
      {
        title: "我的权限",
        key: "shared_level",
        width: 90,
        render: (row) => LEVEL_LABELS[row.shared_level] || row.shared_level || "—",
      }
    );
  } else if (ORG_SCOPES.includes(activeScope.value)) {
    base.push(
      {
        title:
          activeScope.value === "company"
            ? "所属公司"
            : activeScope.value === "team"
              ? "所属小组"
              : "所属部门",
        key: "dept_name",
        width: 120,
        render: (row) => row.dept_name || "—",
      },
      {
        title: "上传人",
        key: "owner_name",
        width: 140,
        render: (row) => row.owner_name || "未知用户",
      }
    );
  }
  base.push(
    {
      title: "更新时间",
      key: "updated_at",
      width: 180,
      render: (row) => new Date(row.updated_at).toLocaleString(),
    },
    {
      title: "操作",
      key: "actions",
      width: 80,
      render: (row) =>
        h(
          NButton,
          {
            text: true,
            type: "primary",
            onClick: () => openDocumentDetail(row.id),
          },
          { default: () => "查看" }
        ),
    }
  );
  return base;
});

async function handleRestore(documentId) {
  try {
    await restoreDocument(documentId);
    message.success("已恢复");
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

function confirmPurgeDocument(documentId, title, { fromRecycle = false } = {}) {
  dialog.warning({
    title: fromRecycle ? "彻底删除" : "删除文档",
    content: fromRecycle
      ? `确定彻底删除「${title || "该文档"}」？删除后无法恢复，文件与相关记录将从系统中移除。`
      : `确定删除「${title || "该文档"}」？将删除全部版本文件及文档记录，且无法恢复。`,
    positiveText: fromRecycle ? "彻底删除" : "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await permanentlyDeleteDocument(documentId);
        message.success(fromRecycle ? "已彻底删除" : "已删除");
        await load();
      } catch (e) {
        message.error(e.message);
        return false;
      }
      return true;
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
  const fromRecycle = isRecycleView.value;
  const title =
    rows.length === 1
      ? `「${rows[0].title || "该文档"}」`
      : `选中的 ${rows.length} 份文档`;
  dialog.warning({
    title: fromRecycle ? "批量彻底删除" : "批量删除文档",
    content: fromRecycle
      ? `确定彻底删除${title}？删除后无法恢复。`
      : `确定删除${title}？将删除全部版本文件及文档记录，且无法恢复。`,
    positiveText: fromRecycle ? "彻底删除" : "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        const res = await batchDeleteDocuments(
          rows.map((row) => row.id),
          { permanent: true }
        );
        const count = res.deleted_count ?? res.deleted?.length ?? 0;
        const failed = res.failed || [];
        if (failed.length) {
          message.warning(
            `已删除 ${count} 份，${failed.length} 份失败：${failed[0].message || "未知错误"}`
          );
        } else {
          message.success(fromRecycle ? `已彻底删除 ${count} 份文档` : `已删除 ${count} 份文档`);
        }
        checkedRowKeys.value = [];
        await load();
      } catch (e) {
        message.error(e.message);
        return false;
      }
      return true;
    },
  });
}

function handlePermanentDelete(documentId, title) {
  confirmPurgeDocument(documentId, title, { fromRecycle: true });
}

async function confirmEmptyRecycle() {
  try {
    const res = await emptyRecycleBin();
    message.success(res.message || "回收站已清空");
    page.value = 1;
    await load();
  } catch (e) {
    message.error(e.message);
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
    message.error(e.message);
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
    message.error(e.message);
  }
}

async function load() {
  const seq = ++documentsLoadSeq;
  loading.value = true;
  items.value = [];
  checkedRowKeys.value = [];
  try {
    if (usesKbFolders.value && !activeKbFolderKey.value) {
      await loadKbFolders();
      if (seq !== documentsLoadSeq) return;
      total.value = 0;
      return;
    }
    const params = {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
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
    message.error(e.message);
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
    message.warning("当前分级下无权新建文件夹");
    return;
  }
  createFolderName.value = "";
  createFolderDesc.value = "";
  showCreateFolder.value = true;
}

async function submitCreateFolder() {
  const name = createFolderName.value.trim();
  if (!name) {
    message.warning("请输入文件夹名称");
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
    message.success("文件夹已创建");
    showCreateFolder.value = false;
    await loadKbFolders();
  } catch (e) {
    message.error(e.message);
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
    message.warning("请输入文件夹名称");
    return;
  }
  savingFolder.value = true;
  try {
    await updateKbFolder(folder.id, {
      name,
      description: editFolderDesc.value.trim(),
    });
    message.success("文件夹已更新");
    editFolderTarget.value = null;
    await loadKbFolders();
  } catch (e) {
    message.error(e.message);
  } finally {
    savingFolder.value = false;
  }
}

async function onDeleteKbFolder(folder) {
  if (!folder?.id) return;
  try {
    await deleteKbFolder(folder.id);
    message.success("文件夹已删除，其中文档已移至未分类");
    if (activeKbFolderKey.value === String(folder.id)) {
      backToKbFolders();
    } else {
      await loadKbFolders();
    }
  } catch (e) {
    message.error(e.message);
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
    dialog.warning({
      title: "删除文件夹",
      content: `确定删除「${folder.name}」？其中文档将归入「未分类」。`,
      positiveText: "删除",
      negativeText: "取消",
      onPositiveClick: () => onDeleteKbFolder(folder),
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
      message.warning(check.message);
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
    message.warning(check.message);
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
    message.warning("请进入知识库文件夹后再新建（分享文件夹内不可新建）");
    return false;
  }
  if (!activeKbFolderKey.value) {
    message.warning("请先进入具体文件夹");
    return false;
  }
  if (!canCreateInActive.value) {
    message.warning("当前分级下无权新建文档");
    return false;
  }
  createScope.value = activeScope.value;
  createDeptId.value =
    ORG_SCOPES.includes(activeScope.value)
      ? activeDeptId.value || orgUnits.value[0]?.id
      : null;
  return true;
}

function openCreate() {
  if (!ensureCanCreateDocuments()) return;
  createTitle.value = "";
  createDesc.value = "";
  uploadFile.value = null;
  showCreate.value = true;
}

function openBatchUpload() {
  if (!ensureCanCreateDocuments()) return;
  batchUploadFiles.value = [];
  batchProgress.value = { done: 0, total: 0 };
  showBatchUpload.value = true;
}

async function submitCreate() {
  if (!uploadFile.value) {
    message.warning("请选择要上传的文件");
    return;
  }
  const check = validateUploadFiles([uploadFile.value], { maxFiles: 1 });
  if (!check.ok) {
    message.warning(check.message);
    return;
  }
  let title = createTitle.value.trim();
  if (!title) {
    title = titleFromFileName(uploadFile.value.name);
  }
  if (!title) {
    message.warning("请输入标题");
    return;
  }
  creating.value = true;
  let createdId = null;
  try {
    const doc = await createDocument(buildCreatePayload(title, createDesc.value));
    createdId = doc.id;
    await uploadFileToDocument(doc.id, uploadFile.value);
    message.success("文档已创建");
    showCreate.value = false;
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
    message.error(e.message);
  } finally {
    creating.value = false;
  }
}

async function submitBatchUpload() {
  const check = validateUploadFiles(batchUploadFiles.value);
  if (!check.ok) {
    message.warning(check.message);
    return;
  }
  if (ORG_SCOPES.includes(createScope.value) && !createDeptId.value) {
    message.warning("请选择所属部门");
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
      message.success(`已成功上传 ${success} 个文档`);
      showBatchUpload.value = false;
      batchUploadFiles.value = [];
    } else if (success) {
      message.warning(
        `成功 ${success} 个，失败 ${failed.length} 个：${failed.map((f) => f.name).join("、")}`
      );
    } else {
      message.error(failed[0]?.reason || "批量上传失败");
    }
    await load();
  } finally {
    batchUploading.value = false;
  }
}

watch(activeScope, () => {
  if (isMainView.value) page.value = 1;
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
  <n-card :title="cardTitle">
    <p v-if="isRecycleView" style="margin: 0 0 12px; color: #666; font-size: 13px">
      此处显示您删除的文档，可点击「恢复」还原到删除前的位置。
    </p>
    <p v-if="isMySharesView" style="margin: 0 0 12px; color: #666; font-size: 13px">
      此处显示您作为上传人分享给其他用户的文档；「我的」下的「分享」文件夹中为别人分享给您的文档。
    </p>
    <n-tabs
      v-if="isMainView"
      v-model:value="activeScope"
      type="line"
      @update:value="onTabChange"
    >
      <n-tab-pane v-for="f in folders" :key="f.scope" :name="f.scope">
        <template #tab>
          <n-space :size="6" align="center">
            <span>{{ f.label }}</span>
            <n-tag
              v-if="!f.can_create"
              size="tiny"
              :bordered="false"
            >
              仅查阅
            </n-tag>
          </n-space>
        </template>
      </n-tab-pane>
    </n-tabs>

    <n-form
      v-if="isMainView && showOrgPicker"
      inline
      style="margin-bottom: 12px"
    >
      <n-form-item label="部门">
        <n-select
          :value="activeDeptId"
          :options="deptOptions"
          style="width: 200px"
          @update:value="onDeptChange"
        />
      </n-form-item>
    </n-form>

    <template #header-extra>
      <n-space>
        <n-button v-if="!isMainView" @click="backToLibrary">返回列表</n-button>
        <n-popconfirm
          v-if="isRecycleView"
          :disabled="!total"
          @positive-click="confirmEmptyRecycle"
        >
          <template #trigger>
            <n-button size="small" secondary :disabled="!total">
              清空回收站
            </n-button>
          </template>
          将彻底删除回收站中的 {{ total }} 份文档，不可恢复。确定继续？
        </n-popconfirm>
        <n-button v-if="isMainView" @click="openMyShares">我的分享</n-button>
        <n-button v-if="isMainView" @click="openRecycle">回收站</n-button>
        <n-input
          v-model:value="keyword"
          placeholder="搜索标题"
          clearable
          style="width: 200px"
          @keyup.enter="() => { page = 1; load(); }"
        />
        <n-button @click="() => { page = 1; load(); }">搜索</n-button>
        <n-button
          v-if="isMainView && usesKbFolders && activeKbFolderKey && !isSharedFolderView"
          type="primary"
          :disabled="!canCreateInActive"
          @click="openCreate"
        >
          新建文档
        </n-button>
        <n-button
          v-if="isMainView && usesKbFolders && activeKbFolderKey && !isSharedFolderView"
          :disabled="!canCreateInActive"
          @click="openBatchUpload"
        >
          批量上传
        </n-button>
      </n-space>
    </template>

    <div
      v-if="usesKbFolders && (showKbFolderList || activeKbFolderKey)"
      class="kb-folder-toolbar"
    >
      <n-button
        v-if="activeKbFolderKey && !showKbFolderList"
        quaternary
        circle
        title="返回文件夹"
        @click="backToKbFolders"
      >
        <template #icon>
          <n-icon :component="ArrowBackOutline" />
        </template>
      </n-button>
      <span
        v-if="activeKbFolderKey && !showKbFolderList && activeKbFolderLabel"
        class="kb-folder-toolbar__title"
      >
        {{ activeKbFolderLabel }}
      </span>
    </div>

    <div v-if="showKbFolderList" v-loading="loading">
      <n-empty
        v-if="!kbFolders.length && !canManageKbFolders"
        description="暂无文件夹"
      />
      <div v-else class="kb-folder-explorer">
        <div
          v-if="canManageKbFolders"
          class="kb-folder-explorer__cell"
          :style="{ '--folder-i': 0 }"
        >
          <KbFolderCreateCard @create="openCreateFolder" />
        </div>
        <div
          v-for="(folder, folderIdx) in kbFolders"
          :key="folder.virtual_id || folder.id"
          class="kb-folder-explorer__cell"
          :style="{ '--folder-i': canManageKbFolders ? folderIdx + 1 : folderIdx }"
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
      </div>
    </div>

    <template v-else>
    <div v-if="showBatchRecycleActions" class="batch-table-toolbar">
      <n-space align="center" :size="8">
        <n-button
          :disabled="!canBatchRecycleDelete"
          type="error"
          secondary
          @click="handleBatchDelete"
        >
          彻底删除
        </n-button>
        <span v-if="checkedRowKeys.length" class="batch-table-toolbar__hint">
          已选 {{ checkedRowKeys.length }} 项
        </span>
      </n-space>
    </div>

    <div v-else-if="showBatchDocActions" class="doc-list-toolbar">
      <n-space align="center">
        <n-button :disabled="!canBatchMove" @click="openBatchMove">移动</n-button>
        <n-button
          :disabled="!canBatchDelete"
          type="error"
          secondary
          @click="handleBatchDelete"
        >
          删除
        </n-button>
        <span
          v-if="checkedRowKeys.length"
          class="doc-list-toolbar__hint"
        >
          已选 {{ checkedRowKeys.length }} 项
        </span>
      </n-space>
    </div>

    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :row-key="(row) => row.id"
      :checked-row-keys="checkedRowKeys"
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

  <n-modal
    v-model:show="showCreate"
    preset="card"
    :title="`新建文档 · ${activeFolder?.label || ''}`"
    style="width: 480px"
    :mask-closable="false"
  >
    <n-form>
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
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showCreate = false">取消</n-button>
        <n-button type="primary" :loading="creating" @click="submitCreate">
          创建
        </n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal
    v-model:show="showBatchUpload"
    preset="card"
    :title="`批量上传 · ${activeFolder?.label || ''}`"
    style="width: 520px"
    :mask-closable="false"
  >
    <n-form>
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
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="batchUploading" @click="showBatchUpload = false">取消</n-button>
        <n-button
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
