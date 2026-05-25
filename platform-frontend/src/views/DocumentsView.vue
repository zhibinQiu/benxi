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
  useMessage,
  useDialog,
} from "naive-ui";
import {
  createDocument,
  fetchDocumentLibrary,
  fetchDocuments,
  fetchRecycleDocuments,
  fetchMySharedDocuments,
  prepareUpload,
  completeUpload,
  restoreDocument,
  permanentlyDeleteDocument,
  emptyRecycleBin,
} from "../api/client";

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
const activeScope = ref("company");
/** main | recycle | my-shares */
const libraryView = ref("main");
const departments = ref([]);

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

const FOLDER_ORDER = ["company", "department", "personal", "shared", "all"];

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
                router.push({ name: "document-detail", params: { id: row.id } }),
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
        title: "我的权限",
        key: "effective_level",
        width: 90,
        render: (row) => LEVEL_LABELS[row.effective_level] || row.effective_level || "—",
      }
    );
  } else if (activeScope.value === "shared") {
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
  } else if (["company", "department"].includes(activeScope.value)) {
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
      width: 100,
      render: (row) =>
        h(
          NButton,
          {
            text: true,
            type: "primary",
            onClick: () =>
              router.push({ name: "document-detail", params: { id: row.id } }),
          },
          { default: () => "详情" }
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

function handlePermanentDelete(documentId, title) {
  dialog.warning({
    title: "彻底删除",
    content: `确定彻底删除「${title || "该文档"}」？删除后无法恢复，文件与相关记录将从系统中移除。`,
    positiveText: "彻底删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await permanentlyDeleteDocument(documentId);
        message.success("已彻底删除");
        await load();
      } catch (e) {
        message.error(e.message);
        return false;
      }
      return true;
    },
  });
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
    return;
  }
  if (view === "my-shares") {
    libraryView.value = "my-shares";
    return;
  }
  libraryView.value = "main";
  const q = route.query.scope;
  if (typeof q === "string" && q && q !== "recycle") {
    activeScope.value = q;
  }
}

async function loadFolders() {
  try {
    const lib = await fetchDocumentLibrary();
    folders.value = normalizeFolders(lib.folders);
    departments.value = lib.departments || [];
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

async function load() {
  loading.value = true;
  items.value = [];
  try {
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

function onTabChange(scope) {
  activeScope.value = scope;
  page.value = 1;
  const query = scope === "company" ? {} : { scope };
  router.replace({ name: "documents", query });
  load();
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
  if (!isMainView.value || activeScope.value === "shared" || activeScope.value === "all") {
    message.warning("请切换到公司/部门/我的文档库后再新建");
    return;
  }
  if (!canCreateInActive.value) {
    message.warning("当前分级下无权新建文档");
    return;
  }
  createScope.value = activeScope.value;
  createDeptId.value =
    activeScope.value === "department" && departments.value.length
      ? departments.value[0].id
      : null;
  createTitle.value = "";
  createDesc.value = "";
  uploadFile.value = null;
  showCreate.value = true;
}

async function submitCreate() {
  let title = createTitle.value.trim();
  if (!title && uploadFile.value) {
    title = titleFromFileName(uploadFile.value.name);
  }
  if (!title) {
    message.warning("请输入标题或选择文件");
    return;
  }
  creating.value = true;
  try {
    const payload = {
      title,
      description: createDesc.value,
      scope: createScope.value,
    };
    if (createScope.value === "department" && createDeptId.value) {
      payload.dept_id = createDeptId.value;
    }
    const doc = await createDocument(payload);
    if (uploadFile.value) {
      const file = uploadFile.value;
      const prep = await prepareUpload(doc.id, file.name, file.type || "application/octet-stream");
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
      message.success("文档已创建并上传");
    } else {
      message.success("文档已创建，可在详情页上传文件");
    }
    showCreate.value = false;
    createTitle.value = "";
    createDesc.value = "";
    uploadFile.value = null;
    await load();
    router.push({ name: "document-detail", params: { id: doc.id } });
  } catch (e) {
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
  await load();
});

watch(
  () => [route.query.view, route.query.scope],
  () => {
    applyRouteFromQuery();
    page.value = 1;
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
      此处显示您作为上传人分享给其他用户的文档；「分享」Tab 中为别人分享给您的文档。
    </p>
    <p v-if="isMainView && activeScope === 'all'" style="margin: 0 0 12px; color: #666; font-size: 13px">
      汇总您具备「可查询」及以上权限的全部文档（与 PDF 翻译、知识问答等可选范围一致）；各分级 Tab 仍按库规则展示。
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
            <n-tag v-if="!f.can_create" size="tiny" :bordered="false">
              仅查阅
            </n-tag>
          </n-space>
        </template>
      </n-tab-pane>
    </n-tabs>

    <template #header-extra>
      <n-space>
        <n-button v-if="!isMainView" @click="backToLibrary">返回文档库</n-button>
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
          v-if="isMainView && activeScope !== 'shared' && activeScope !== 'all'"
          type="primary"
          :disabled="!canCreateInActive"
          @click="openCreate"
        >
          新建文档
        </n-button>
      </n-space>
    </template>

    <n-data-table
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
      <n-form-item label="文件（可选）">
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
</template>
