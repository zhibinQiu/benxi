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
  NTooltip,
  NIcon,
  NDropdown,
  useMessage,
  useDialog,
} from "naive-ui";
import {
  Folder,
  FolderOpen,
  ShareSocial,
  EllipsisHorizontal,
  CreateOutline,
  TrashOutline,
  AddOutline,
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
  permanentlyDeleteDocument,
  emptyRecycleBin,
  updateKbFolder,
} from "../api/client";
import MoveDocumentFolderModal from "../components/MoveDocumentFolderModal.vue";
import { navigateWithReturn } from "../utils/navigationReturn";

const route = useRoute();
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
const departments = ref([]);

const showCreateFolder = ref(false);
const createFolderName = ref("");
const createFolderDesc = ref("");
const savingFolder = ref(false);
const editFolderTarget = ref(null);
const editFolderName = ref("");
const editFolderDesc = ref("");

const showMoveDoc = ref(false);
const moveDocTarget = ref(null);

const showCreate = ref(false);
const createTitle = ref("");
const createDesc = ref("");
const createScope = ref("personal");
const createDeptId = ref(null);
const uploadFile = ref(null);
const creating = ref(false);
const activeFolder = computed(() =>
  folders.value.find((f) => f.scope === activeScope.value)
);

const canCreateInActive = computed(() => activeFolder.value?.can_create ?? false);

const deptOptions = computed(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id }))
);

const scopeTagType = {
  company: "info",
  department: "warning",
  personal: "default",
  shared: "success",
  all: "primary",
};

const FOLDER_ORDER = ["personal", "department", "company", "shared"];

const VIRTUAL_UNCATEGORIZED = "__uncategorized__";
const VIRTUAL_SHARED = "__shared__";

const SCOPE_LABELS = {
  company: "公司级",
  department: "部门级",
  personal: "我的",
  shared: "分享",
  all: "所有",
};

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
  if (activeScope.value === "department" && activeDeptId.value) {
    return activeDeptId.value;
  }
  return moveDocTarget.value?.dept_id ?? null;
});

const canShowDeleteInList = computed(
  () => isMainView.value && !isRecycleView.value && !isMySharesView.value
);

const cardTitle = computed(() => {
  if (isRecycleView.value) return "回收站";
  if (isMySharesView.value) return "我的分享";
  return "文档库";
});

const columns = computed(() => {
  const base = [
    { title: "标题", key: "title", ellipsis: { tooltip: true } },
  ];
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
        width: 160,
        render: (row) =>
          h(NSpace, { size: 8 }, () => [
            h(
              NButton,
              {
                text: true,
                type: "primary",
                onClick: () => handleRestore(row.id),
              },
              { default: () => "恢复" }
            ),
            h(
              NButton,
              {
                text: true,
                type: "default",
                onClick: () => handlePermanentDelete(row.id, row.title),
              },
              { default: () => "彻底删除" }
            ),
          ]),
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
            { default: () => "详情" }
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
          row.scope === "department" ? row.dept_name || "—" : "—",
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
  } else if (activeScope.value === "department") {
    base.push(
      {
        title: "所属部门",
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
  } else if (activeScope.value === "company") {
    base.push({
      title: "上传人",
      key: "owner_name",
      width: 140,
      render: (row) => row.owner_name || "未知用户",
    });
  }
  base.push(
    {
      title: "上传时间",
      key: "uploaded_at",
      width: 180,
      render: (row) =>
        row.uploaded_at
          ? new Date(row.uploaded_at).toLocaleString()
          : new Date(row.updated_at).toLocaleString(),
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
      width: canShowDeleteInList.value ? 168 : 100,
      render: (row) => {
        if (!canShowDeleteInList.value) {
          return h(
            NButton,
            {
              text: true,
              type: "primary",
              onClick: () =>
                openDocumentDetail(row.id),
            },
            { default: () => "详情" }
          );
        }
        return h(NSpace, { size: 8 }, () => {
          const buttons = [
            h(
              NButton,
              {
                text: true,
                type: "primary",
                onClick: () =>
                  openDocumentDetail(row.id),
              },
              { default: () => "详情" }
            ),
          ];
          if (canShowMoveInList.value && row.can_edit) {
            buttons.push(
              h(
                NButton,
                {
                  text: true,
                  onClick: () => openMoveDocument(row),
                },
                { default: () => "移动" }
              )
            );
          }
          if (row.can_delete) {
            buttons.push(
              h(
                NButton,
                {
                  text: true,
                  type: "error",
                  onClick: () => handleDeleteDocument(row.id, row.title),
                },
                { default: () => "删除" }
              )
            );
          }
          return buttons;
        });
      },
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
  return FOLDER_ORDER.filter((s) => byScope[s]).map((s) => byScope[s]);
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
  const q = route.query.scope;
  if (typeof q === "string" && q && q !== "recycle") {
    activeScope.value = q;
  }
  if (route.query.dept_id) {
    activeDeptId.value = route.query.dept_id;
  }
  const fk = route.query.folder;
  activeKbFolderKey.value =
    typeof fk === "string" && fk ? fk : null;
}

async function loadFolders() {
  try {
    const lib = await fetchDocumentLibrary();
    folders.value = normalizeFolders(lib.folders);
    departments.value = lib.departments || [];
    if (
      activeScope.value === "department" &&
      departments.value.length &&
      !activeDeptId.value
    ) {
      activeDeptId.value = departments.value[0].id;
    }
    applyRouteFromQuery();
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
  if (!usesKbFolders.value) {
    kbFolders.value = [];
    return;
  }
  try {
    const params = { scope: activeScope.value };
    if (activeScope.value === "department" && activeDeptId.value) {
      params.dept_id = activeDeptId.value;
    }
    const data = await fetchKbFolders(params);
    kbFolders.value = data.items || [];
    kbCanManageFolders.value = !!data.can_manage_folders;
  } catch (e) {
    kbFolders.value = [];
    message.error(e.message);
  }
}

async function load() {
  loading.value = true;
  items.value = [];
  try {
    if (usesKbFolders.value && !activeKbFolderKey.value) {
      await loadKbFolders();
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
      if (activeScope.value === "department" && activeDeptId.value) {
        docParams.dept_id = activeDeptId.value;
      }
      if (activeKbFolderKey.value === VIRTUAL_UNCATEGORIZED) {
        docParams.uncategorized = true;
      } else {
        docParams.folder_id = activeKbFolderKey.value;
      }
      data = await fetchDocuments(docParams);
    } else {
      data = await fetchDocuments({ ...params, scope: activeScope.value });
    }
    items.value = data.items || [];
    total.value = data.total ?? 0;
  } catch (e) {
    items.value = [];
    total.value = 0;
    message.error(e.message);
  } finally {
    loading.value = false;
  }
}

function onPageChange(p) {
  page.value = p;
  load();
}

function buildLibraryQuery() {
  const query = {};
  if (activeScope.value !== "company") query.scope = activeScope.value;
  if (activeScope.value === "department" && activeDeptId.value) {
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

function onTabChange(scope) {
  activeScope.value = scope;
  if (scope === "shared") {
    activeKbFolderKey.value = null;
  }
  activeKbFolderKey.value = null;
  page.value = 1;
  if (scope === "department" && departments.value.length) {
    activeDeptId.value = departments.value[0].id;
  }
  router.replace({ name: "documents", query: buildLibraryQuery() });
  loadKbFolders();
  load();
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
    if (activeScope.value === "department" && activeDeptId.value) {
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

function folderIconColor(folder) {
  if (folder.kind === "shared") return "#3b82f6";
  if (folder.is_system) return "#94a3b8";
  return "#f0b429";
}

function folderIconComponent(folder) {
  if (folder.kind === "shared") return ShareSocial;
  if (folder.kind === "uncategorized") return FolderOpen;
  return Folder;
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

function openMoveDocument(row) {
  moveDocTarget.value = row;
  showMoveDoc.value = true;
}

function onDocumentMoved() {
  showMoveDoc.value = false;
  moveDocTarget.value = null;
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
  const query =
    activeScope.value === "company" ? {} : { scope: activeScope.value };
  router.replace({ name: "documents", query });
  load();
}

function titleFromFileName(fileName) {
  const base = String(fileName || "").replace(/^.*[/\\]/, "").trim();
  if (!base) return "";
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

function onCreateFileChange(opts) {
  const file = opts.fileList[0]?.file ?? null;
  uploadFile.value = file;
  if (file && !createTitle.value.trim()) {
    createTitle.value = titleFromFileName(file.name);
  }
}

function openCreate() {
  if (
    !isMainView.value ||
    activeScope.value === "all" ||
    isSharedScopeTab.value ||
    isSharedFolderView.value
  ) {
    message.warning("请进入知识库文件夹后再新建（分享文件夹内不可新建）");
    return;
  }
  if (!activeKbFolderKey.value) {
    message.warning("请先进入具体文件夹");
    return;
  }
  if (!canCreateInActive.value) {
    message.warning("当前分级下无权新建文档");
    return;
  }
  createScope.value = activeScope.value;
  createDeptId.value =
    activeScope.value === "department"
      ? activeDeptId.value || departments.value[0]?.id
      : null;
  createTitle.value = "";
  createDesc.value = "";
  uploadFile.value = null;
  showCreate.value = true;
}

async function submitCreate() {
  if (!uploadFile.value) {
    message.warning("请选择要上传的文件");
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
    const payload = {
      title,
      description: createDesc.value,
      scope: createScope.value,
    };
    if (createScope.value === "department" && createDeptId.value) {
      payload.dept_id = createDeptId.value;
    }
    if (
      activeKbFolderKey.value &&
      activeKbFolderKey.value !== VIRTUAL_UNCATEGORIZED &&
      activeKbFolderKey.value !== VIRTUAL_SHARED
    ) {
      payload.folder_id = activeKbFolderKey.value;
    }
    const doc = await createDocument(payload);
    createdId = doc.id;
    const file = uploadFile.value;
    const prep = await prepareUpload(
      doc.id,
      file.name,
      file.type || "application/octet-stream"
    );
    const putRes = await fetch(prep.upload_url, {
      method: "PUT",
      body: file,
      headers: { "Content-Type": file.type || "application/octet-stream" },
    });
    if (!putRes.ok) throw new Error("上传到存储失败");
    await completeUpload(doc.id, {
      version_id: prep.version_id,
      file_size: file.size,
    });
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

watch(activeScope, () => {
  if (isMainView.value) page.value = 1;
});

onMounted(async () => {
  applyRouteFromQuery();
  await loadFolders();
  await loadKbFolders();
  await load();
});

watch(
  () => [route.query.view, route.query.scope, route.query.folder, route.query.dept_id],
  async () => {
    applyRouteFromQuery();
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
    <p v-if="isSharedScopeTab" style="margin: 0 0 12px; color: #666; font-size: 13px">
      其他用户分享给您的文档；「我的分享」中可查看您分享给他人的文档。
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
              v-if="!f.can_create && f.scope !== 'shared'"
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
      v-if="isMainView && activeScope === 'department' && departments.length > 1"
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
      <n-button
        v-if="showKbFolderList && canManageKbFolders"
        quaternary
        circle
        type="primary"
        title="新建文件夹"
        @click="openCreateFolder"
      >
        <template #icon>
          <n-icon :component="AddOutline" />
        </template>
      </n-button>
    </div>

    <div v-if="showKbFolderList" v-loading="loading">
      <n-empty v-if="!kbFolders.length" description="暂无文件夹" />
      <div v-else class="kb-folder-explorer">
        <n-tooltip
          v-for="folder in kbFolders"
          :key="folder.virtual_id || folder.id"
          trigger="hover"
          :delay="400"
        >
          <template #trigger>
            <div
              class="kb-folder-item"
              role="button"
              tabindex="0"
              @click="openKbFolder(folder)"
              @keydown.enter="openKbFolder(folder)"
              @dblclick="openKbFolder(folder)"
            >
              <span v-if="folder.is_system" class="kb-folder-item__badge">内置</span>
              <div
                v-if="folderMenuOptions(folder).length"
                class="kb-folder-item__actions"
                @click.stop
              >
                <n-dropdown
                  trigger="click"
                  :options="folderMenuOptions(folder)"
                  @select="(key) => onFolderMenuSelect(key, folder)"
                >
                  <n-button quaternary circle size="tiny" title="更多操作">
                    <template #icon>
                      <n-icon :component="EllipsisHorizontal" />
                    </template>
                  </n-button>
                </n-dropdown>
              </div>
              <div class="kb-folder-item__icon">
                <n-icon
                  :size="folder.kind === 'shared' ? 40 : 44"
                  :color="folderIconColor(folder)"
                  :component="folderIconComponent(folder)"
                />
              </div>
              <div class="kb-folder-item__name">{{ folder.name }}</div>
              <div class="kb-folder-item__meta">{{ folder.document_count ?? 0 }} 项</div>
            </div>
          </template>
          {{ folderTooltip(folder) }}
        </n-tooltip>
      </div>
    </div>

    <n-data-table
      v-else
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="{
        page: page,
        pageSize: pageSize,
        itemCount: total,
        onUpdatePage: onPageChange,
      }"
    />
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
        v-if="createScope === 'department'"
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
    v-if="moveDocTarget"
    v-model:show="showMoveDoc"
    :document-id="moveDocTarget.id"
    :document-title="moveDocTarget.title"
    :scope="moveDocTarget.scope"
    :folder-scope="moveFolderScope"
    :dept-id="moveDocTarget.dept_id"
    :folder-dept-id="moveFolderDeptId"
    :current-folder-id="moveDocTarget.folder_id"
    @moved="onDocumentMoved"
  />
</template>
