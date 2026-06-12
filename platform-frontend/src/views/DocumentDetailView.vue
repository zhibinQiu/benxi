<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, nextTick, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NCard,
  NButton,
  NSpace,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  NUpload,
  NTable,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NSwitch,
  NText,
  NDivider,
  NRadio,
  NRadioGroup,
  NSelect,
} from "naive-ui";
import {
  DownloadOutline,
  EyeOutline,
  LayersOutline,
  RefreshOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import IconAction from "../components/IconAction.vue";
import AdminFormModal from "../components/AdminFormModal.vue";
import DocumentVersionPreviewModal from "../components/DocumentVersionPreviewModal.vue";
import {
  fetchDocument,
  updateDocument,
  prepareUpload,
  uploadDocumentBlob,
  completeUpload,
  downloadDocumentFile,
  deleteDocumentVersion,
  patchDocumentStatus,
  fetchDocumentAccessControl,
  fetchDocumentAclCandidates,
  fetchDocumentShares,
  grantDocumentShares,
  revokeDocumentShare,
  fetchDocumentDenials,
  denyDocumentAccess,
  liftDocumentDenial } from "../api/client";
import { useAuth } from "../composables/useAuth";
import OrgUserPickerTree from "../components/OrgUserPickerTree.vue";
import OrgDeptPickerTree from "../components/OrgDeptPickerTree.vue";
import { useDocumentReindex } from "../composables/useDocumentReindex.js";
import { knowledgeIndexTagProps } from "../utils/knowledgeIndex.js";
import { userLabel } from "../utils/orgUserTree";
import { goBackToEntry, navigateWithReturn } from "../utils/navigationReturn";
import { ORG_SCOPES, SCOPE_LABELS, SCOPE_PERM } from "../constants/documentScope";
import {
  applyUploadLimitsFromLibrary,
  validateUploadFiles,
  validateVersionFormatMatch,
} from "../constants/documentUpload";
import { readDocumentsLibraryCache } from "../utils/documentsViewCache.js";
import { fetchDocumentLibrary } from "../api/documents.js";
const LEVEL_LABELS = {
  visible: "可见",
  query: "可查",
  modify: "可修改",
  edit: "可修改",
  full: "可修改",
  read: "可见",
  use: "可修改",
  delete: "可修改"};

const route = useRoute();
const router = useRouter();

function goBack() {
  goBackToEntry(router, route, { name: "documents" });
}

const ui = usePlatformUi();

const { user, hasPerm } = useAuth();

const docId = route.params.id;
const doc = ref(null);
const loading = ref(false);
const editTitle = ref("");
const titleEditing = ref(false);
const titleSaving = ref(false);
const titleInputRef = ref(null);

const canModifyDoc = computed(
  () =>
    aclCaps.value.can_modify === true ||
    aclCaps.value.can_edit === true ||
    aclCaps.value.can_manage === true
);

const canDeleteDoc = computed(
  () => canModifyDoc.value || aclCaps.value.can_delete === true
);

const canEditDoc = canModifyDoc;

const canManageDoc = canModifyDoc;

const canReindexDoc = canModifyDoc;

const canViewDoc = computed(() => aclCaps.value.can_view !== false);

const statusEnabled = computed({
  get: () => doc.value?.status === "active",
  set: () => {}});

const isOwner = computed(
  () => user.value?.id && doc.value?.owner_id === user.value.id
);

const ownerLabel = computed(() => doc.value?.owner_name || "未知用户");

const uploadedAtLabel = computed(() => {
  const t = doc.value?.uploaded_at || doc.value?.created_at;
  return t ? new Date(t).toLocaleString() : "—";
});

const displayVersions = computed(() => doc.value?.versions || []);

const {
  reindexModalShow,
  reindexTargetVersion,
  parserId,
  layoutRecognize,
  chunkMethodOptions,
  layoutOptions,
  reparsing,
  indexPolling,
  loadParserOptions,
  openReindexModal,
  submitReindex,
} = useDocumentReindex(docId, () => load({ notifyOnError: false }));

const showVersionActions = computed(
  () => canViewDoc.value || canDeleteDoc.value || canReindexDoc.value
);

const versionChangeDesc = ref("");
const versionUploadFile = ref(null);
const versionUploadFileList = ref([]);
const versionUploading = ref(false);
const versionRefreshing = ref(false);
const showVersionPreview = ref(false);
const previewVersion = ref(null);

function onVersionFileChange({ fileList }) {
  const file = fileList[0]?.file ?? null;
  if (file) {
    const sizeCheck = validateUploadFiles([file], { maxFiles: 1 });
    if (!sizeCheck.ok) {
      ui.warning(sizeCheck.message);
      versionUploadFile.value = null;
      versionUploadFileList.value = [];
      return;
    }
    const formatCheck = validateVersionFormatMatch(displayVersions.value, file);
    if (!formatCheck.ok) {
      ui.warning(formatCheck.message);
      versionUploadFile.value = null;
      versionUploadFileList.value = [];
      return;
    }
  }
  versionUploadFile.value = file;
  versionUploadFileList.value = fileList;
}

async function submitVersionUpload() {
  if (!versionUploadFile.value) {
    ui.warning("请选择文件");
    return;
  }
  const sizeCheck = validateUploadFiles([versionUploadFile.value], { maxFiles: 1 });
  if (!sizeCheck.ok) {
    ui.warning(sizeCheck.message);
    return;
  }
  const formatCheck = validateVersionFormatMatch(
    displayVersions.value,
    versionUploadFile.value
  );
  if (!formatCheck.ok) {
    ui.warning(formatCheck.message);
    return;
  }
  const raw = versionUploadFile.value;
  versionUploading.value = true;
  try {
    const prep = await prepareUpload(
      docId,
      raw.name,
      raw.type || "application/octet-stream"
    );
    await uploadDocumentBlob(prep.upload_url, raw);
    await completeUpload(docId, {
      version_id: prep.version_id,
      file_size: raw.size,
      change_description: versionChangeDesc.value.trim(),
    });
    ui.success("新版本已上传，知识库正在后台同步");
    versionChangeDesc.value = "";
    versionUploadFile.value = null;
    versionUploadFileList.value = [];
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e.message);
  } finally {
    versionUploading.value = false;
  }
}

function versionFileLabel(v) {
  return v.file_name || "—";
}

function versionSizeLabel(v) {
  if (!v.uploaded || !v.file_size) return "—";
  return `${(v.file_size / 1024).toFixed(1)} KB`;
}

const aclCaps = ref({
  can_grant: false,
  can_deny: false,
  is_owner: false,
  can_view: true,
  can_query: false,
  can_edit: false,
  can_delete: false,
  can_manage: false,
  can_restore: false,
  effective_level: null});

const canGrantAcl = computed(() => aclCaps.value.can_grant);
const canDenyAcl = computed(() => aclCaps.value.can_deny);
const canManageAcl = computed(() => canGrantAcl.value || canDenyAcl.value);

const shares = ref([]);
const denials = ref([]);
const showDeny = ref(false);
const aclPicker = ref({
  company_label: "公司",
  departments: [],
  users: []});
const aclCandidates = computed(() => aclPicker.value.users || []);
const aclDepartments = computed(() => aclPicker.value.departments || []);
const denyUserId = ref(null);
const denyReason = ref("");
const shareSelectedKeys = ref([]);
const shareGranting = ref(false);
const publishTarget = ref("department");
const publishDeptIds = ref([]);
const publishLoading = ref(false);
const accessMode = ref("publish");

const canPublishCompanyPerm = computed(
  () => isOwner.value && hasPerm("doc.company.create")
);
const canPublishDeptPerm = computed(
  () => isOwner.value && hasPerm("doc.dept.create")
);
const canPublishTeamPerm = computed(
  () => isOwner.value && hasPerm("doc.team.create")
);
const canPublishCompany = computed(() => {
  if (!isOwner.value) return false;
  if (canPublishCompanyPerm.value) return true;
  return doc.value?.scope === "company";
});
const canPublishDept = computed(() => {
  if (!isOwner.value) return false;
  if (canPublishDeptPerm.value) return true;
  return doc.value?.scope === "department" || doc.value?.scope === "company";
});
/** 部门/公司/小组级文档的创建人仍可调整至小组级 */
const showTeamPublish = computed(() => {
  if (!isOwner.value) return false;
  if (canPublishTeamPerm.value) return true;
  return ORG_SCOPES.includes(doc.value?.scope ?? "");
});
const showPublishCard = computed(
  () =>
    canPublishCompany.value ||
    canPublishDept.value ||
    showTeamPublish.value
);
const showAccessCard = computed(
  () => showPublishCard.value || canGrantAcl.value
);

function syncAccessModeDefault() {
  if (accessMode.value === "publish" && !showPublishCard.value && canGrantAcl.value) {
    accessMode.value = "share";
  } else if (accessMode.value === "share" && !canGrantAcl.value && showPublishCard.value) {
    accessMode.value = "publish";
  } else if (!showPublishCard.value && canGrantAcl.value) {
    accessMode.value = "share";
  } else if (showPublishCard.value && !canGrantAcl.value) {
    accessMode.value = "publish";
  }
}
const currentScopeLabel = computed(() => {
  const s = doc.value?.scope || "personal";
  if (ORG_SCOPES.includes(s)) {
    const tier = SCOPE_LABELS[s] || s;
    const deptName =
      doc.value?.dept_name ||
      aclDepartments.value.find((x) => x.id === doc.value?.dept_id)?.name;
    return deptName ? `${tier} · ${deptName}` : tier;
  }
  return SCOPE_LABELS[s] || s;
});

const versionUploadFileLabel = computed(() => {
  const name = versionUploadFile.value?.name;
  if (!name) return "选择文件";
  return name.length > 28 ? `${name.slice(0, 25)}…` : name;
});

const supportsKbFolder = computed(() =>
  ["company", "department", "team", "personal"].includes(doc.value?.scope)
);

const sharePermissionActions = [
  { level: "visible", label: "可见", desc: "下载、预览" },
  { level: "query", label: "可查", desc: "问答、检索" },
  { level: "modify", label: "可修改", desc: "上传、分享、重建索引、删除" },
];

const userNameById = computed(() => {
  const m = {};
  for (const u of aclCandidates.value) {
    m[u.id] = userLabel(u);
  }
  for (const s of shares.value) {
    if (s.user_name) {
      m[s.user_id] = s.user_name;
    }
  }
  return m;
});

async function loadAclCandidates() {
  if (!canManageAcl.value) return;
  try {
    aclPicker.value = await fetchDocumentAclCandidates(docId);
  } catch {
    aclPicker.value = { company_label: "公司", departments: [], users: [] };
  }
}

async function ensureCandidates() {
  if (!aclPicker.value.users?.length && !aclPicker.value.departments?.length) {
    await loadAclCandidates();
  }
}

function startEditTitle() {
  if (!doc.value || !canEditDoc.value) return;
  editTitle.value = doc.value.title || "";
  titleEditing.value = true;
  nextTick(() => titleInputRef.value?.focus());
}

function cancelEditTitle() {
  editTitle.value = doc.value?.title || "";
  titleEditing.value = false;
}

async function saveTitle() {
  if (!doc.value || !canEditDoc.value) return;
  const next = editTitle.value.trim();
  if (!next) {
    ui.warning("标题不能为空");
    editTitle.value = doc.value.title;
    return;
  }
  if (next === doc.value.title) {
    titleEditing.value = false;
    return;
  }
  titleSaving.value = true;
  try {
    doc.value = await updateDocument(docId, { title: next });
    editTitle.value = doc.value.title;
    titleEditing.value = false;
    ui.success("标题已保存");
  } catch (e) {
    editTitle.value = doc.value.title;
    ui.error(e.message);
  } finally {
    titleSaving.value = false;
  }
}

async function refreshVersionHistory() {
  versionRefreshing.value = true;
  try {
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e.message);
  } finally {
    versionRefreshing.value = false;
  }
}

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    doc.value = await fetchDocument(docId);
    editTitle.value = doc.value.title || "";
    try {
      aclCaps.value = await fetchDocumentAccessControl(docId);
    } catch {
      aclCaps.value = {
        can_grant: false,
        can_deny: false,
        is_owner: false,
        can_view: true,
        can_query: false,
        can_modify: false,
        can_edit: false,
        can_delete: false,
        can_manage: false,
        can_restore: false};
    }
    const docOwner =
      user.value?.id && doc.value?.owner_id === user.value.id;
    if (canGrantAcl.value || docOwner) {
      await loadAclCandidates();
    }
    if (ORG_SCOPES.includes(doc.value.scope)) {
      publishTarget.value = doc.value.scope;
      publishDeptIds.value = doc.value.dept_id ? [doc.value.dept_id] : [];
    } else {
      publishTarget.value = "department";
      publishDeptIds.value = [];
    }
    syncAccessModeDefault();
    shares.value = [];
    denials.value = [];
    if (canGrantAcl.value || docOwner) {
      try {
        shares.value = await fetchDocumentShares(docId);
      } catch {
        shares.value = [];
      }
    } else {
      aclPicker.value = { company_label: "公司", departments: [], users: [] };
      shares.value = [];
    }
    if (canDenyAcl.value) {
      try {
        denials.value = await fetchDocumentDenials(docId);
      } catch {
        denials.value = [];
      }
    }
  } catch (e) {
    if (notifyOnError) ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function downloadVersion(v) {
  if (!v?.uploaded) return;
  try {
    const fallback =
      v.file_name || `${doc.value?.title || "document"}.pdf`;
    await downloadDocumentFile(docId, fallback, v.id);
    ui.success("已开始下载");
  } catch (e) {
    ui.error(e.message);
  }
}

function openVersionPreview(v) {
  if (!v?.uploaded) return;
  previewVersion.value = v;
  showVersionPreview.value = true;
}

function onPreviewDownload(v) {
  showVersionPreview.value = false;
  downloadVersion(v);
}

async function onStatusChange(enabled) {
  if (!canManageDoc.value) return;
  const next = enabled ? "active" : "disabled";
  try {
    doc.value = await patchDocumentStatus(docId, next);
    ui.success(enabled ? "已启用" : "已关闭");
  } catch (e) {
    ui.error(e.message);
    await load({ notifyOnError: false });
  }
}

function confirmDeleteVersion(v) {
  const label = `v${v.version_no}`;
  const hint =
    displayVersions.value.length <= 1
      ? "这是最后一个版本，删除后整份文档及知识库索引将被永久删除。"
      : "仅删除该版本文件，其他版本保留。";
  ui.confirmDelete({
    title: `删除版本 ${label}`,
    content: `${hint} 确定继续？`,
    onPositive: async () => {
      const res = await deleteDocumentVersion(docId, v.id);
      if (res.document_deleted) {
        ui.success(res.message || "文档已删除");
        goBack();
        return;
      }
      ui.success(res.message || "版本已删除");
      await load({ notifyOnError: false });
    },
  });
}

async function publishToLibrary() {
  if (ORG_SCOPES.includes(publishTarget.value)) {
    if (!publishDeptIds.value.length) {
      ui.warning("请选择要发布到的组织单元");
      return;
    }
    if (publishTarget.value === "team" && !showTeamPublish.value) {
      ui.warning("无权发布到小组级文库");
      return;
    }
    if (publishTarget.value === "department" && !canPublishDept.value) {
      ui.warning("无权发布到部门级文库");
      return;
    }
  } else if (!canPublishCompany.value) {
    ui.warning("无权发布到公司级文库");
    return;
  }
  publishLoading.value = true;
  try {
    const payload = { scope: publishTarget.value };
    if (ORG_SCOPES.includes(publishTarget.value)) {
      payload.dept_id = publishDeptIds.value[0];
    }
    doc.value = await updateDocument(docId, payload);
    ui.success("已发布到文库，可在文档库对应分级中查看");
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e.message);
  } finally {
    publishLoading.value = false;
  }
}

async function grantShareLevel(level) {
  if (!shareSelectedKeys.value.length) {
    ui.warning("请先勾选要分享的用户");
    return;
  }
  shareGranting.value = true;
  try {
    shares.value = await grantDocumentShares(docId, {
      userIds: shareSelectedKeys.value,
      level});
    const label = LEVEL_LABELS[level] || level;
    ui.success(
      `已为 ${shareSelectedKeys.value.length} 人授予「${label}」权限`
    );
  } catch (e) {
    ui.error(e.message);
  } finally {
    shareGranting.value = false;
  }
}

async function openDenyModal() {
  try {
    await ensureCandidates();
    denyUserId.value = null;
    showDeny.value = true;
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeShare(userId) {
  try {
    await revokeDocumentShare(docId, userId);
    ui.success("已取消该用户的分享");
    shares.value = await fetchDocumentShares(docId);
  } catch (e) {
    ui.error(e.message);
  }
}

async function submitDeny() {
  if (!denyUserId.value) {
    ui.warning("请选择要禁止访问的用户");
    return;
  }
  try {
    await denyDocumentAccess(docId, {
      user_id: denyUserId.value,
      reason: denyReason.value});
    ui.success("已禁止该用户访问（部门/公司默认可见规则不再生效）");
    showDeny.value = false;
    denyUserId.value = null;
    denyReason.value = "";
    denials.value = await fetchDocumentDenials(docId);
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeDenial(uid) {
  try {
    await liftDocumentDenial(docId, uid);
    ui.success("已恢复访问");
    denials.value = await fetchDocumentDenials(docId);
  } catch (e) {
    ui.error(e.message);
  }
}

onMounted(() => {
  const cached = readDocumentsLibraryCache();
  if (cached) {
    applyUploadLimitsFromLibrary(cached);
  } else {
    fetchDocumentLibrary()
      .then(applyUploadLimitsFromLibrary)
      .catch(() => {});
  }
  load();
  loadParserOptions();
});
</script>

<template>
  <n-space vertical :size="16" v-if="doc">
    <n-card :loading="loading">
      <template #header>
        <n-space align="center" :size="12" style="flex-wrap: wrap">
          <template v-if="titleEditing && canEditDoc">
            <n-input
              ref="titleInputRef"
              v-model:value="editTitle"
              class="doc-title-input"
              placeholder="文档标题"
              maxlength="512"
              :disabled="titleSaving"
              @keyup.enter="saveTitle"
            />
            <n-button
              size="small"
              type="primary"
              :loading="titleSaving"
              :disabled="titleSaving"
              @click="saveTitle"
            >
              保存
            </n-button>
            <n-button size="small" :disabled="titleSaving" @click="cancelEditTitle">
              取消
            </n-button>
          </template>
          <template v-else>
            <n-text strong style="font-size: 16px">{{ doc.title }}</n-text>
            <n-button
              v-if="canEditDoc"
              text
              type="primary"
              size="small"
              @click="startEditTitle"
            >
              修改
            </n-button>
          </template>
        </n-space>
      </template>
      <n-descriptions :column="2" label-placement="left">
        <n-descriptions-item label="ID">{{ doc.id }}</n-descriptions-item>
        <n-descriptions-item label="文档状态">
          <n-space align="center" :size="8">
            <n-switch
              :value="statusEnabled"
              :disabled="!canManageDoc"
              @update:value="onStatusChange"
            />
            <span>{{ statusEnabled ? "启用" : "关闭" }}</span>
          </n-space>
        </n-descriptions-item>
        <n-descriptions-item label="分级">
          <n-tag size="small">{{ SCOPE_LABELS[doc.scope] || doc.scope }}</n-tag>
        </n-descriptions-item>
        <n-descriptions-item v-if="supportsKbFolder" label="所在文件夹">
          {{ doc.folder_name || "未分类" }}
        </n-descriptions-item>
        <n-descriptions-item
          v-if="ORG_SCOPES.includes(doc.scope) && (doc.dept_name || doc.dept_id)"
          label="所属组织"
        >
          {{ doc.dept_name || "—" }}
        </n-descriptions-item>
        <n-descriptions-item label="上传人">{{ ownerLabel }}</n-descriptions-item>
        <n-descriptions-item label="上传时间">{{ uploadedAtLabel }}</n-descriptions-item>
        <n-descriptions-item label="说明" :span="2">{{ doc.description || "—" }}</n-descriptions-item>
        <n-descriptions-item label="创建时间">
          {{ new Date(doc.created_at).toLocaleString() }}
        </n-descriptions-item>
        <n-descriptions-item label="更新时间">
          {{ new Date(doc.updated_at).toLocaleString() }}
        </n-descriptions-item>
      </n-descriptions>
    </n-card>

    <n-card title="版本历史">
      <template #header-extra>
        <IconAction
          label="刷新"
          :icon="RefreshOutline"
          :disabled="versionRefreshing || loading"
          @click="refreshVersionHistory"
        />
      </template>
      <n-table :single-line="false">
        <thead>
          <tr>
            <th>版本</th>
            <th>文件名</th>
            <th>版本说明</th>
            <th>大小</th>
            <th>时间</th>
            <th>索引</th>
            <th v-if="showVersionActions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in displayVersions" :key="v.id">
            <td>
              <n-space :size="6" align="center">
                <span>v{{ v.version_no }}</span>
                <n-tag v-if="v.is_current" size="small" type="info">当前</n-tag>
              </n-space>
            </td>
            <td>{{ versionFileLabel(v) }}</td>
            <td>{{ v.change_description || "—" }}</td>
            <td>{{ versionSizeLabel(v) }}</td>
            <td>{{ new Date(v.created_at).toLocaleString() }}</td>
            <td>
              <n-tag
                v-if="v.uploaded"
                size="small"
                :type="knowledgeIndexTagProps(v).type"
                :bordered="false"
              >
                {{ knowledgeIndexTagProps(v).label }}
              </n-tag>
              <span v-else>—</span>
            </td>
            <td v-if="showVersionActions">
              <div class="table-icon-actions">
                <IconAction
                  v-if="v.uploaded && canReindexDoc"
                  variant="table"
                  label="重新索引"
                  :icon="LayersOutline"
                  :disabled="indexPolling || reparsing"
                  @click="openReindexModal(v)"
                />
                <IconAction
                  v-if="v.uploaded && canViewDoc"
                  variant="table"
                  label="预览"
                  :icon="EyeOutline"
                  @click="openVersionPreview(v)"
                />
                <IconAction
                  v-if="v.uploaded && canViewDoc"
                  variant="table"
                  label="下载"
                  :icon="DownloadOutline"
                  type="primary"
                  @click="downloadVersion(v)"
                />
                <IconAction
                  v-if="canDeleteDoc"
                  variant="table"
                  label="删除"
                  :icon="TrashOutline"
                  type="error"
                  @click="confirmDeleteVersion(v)"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </n-table>

      <div v-if="canEditDoc" class="version-upload-bar">
        <n-input
          v-model:value="versionChangeDesc"
          class="version-upload-bar__desc"
          size="small"
          placeholder="版本说明（可选）"
          clearable
        />
        <n-upload
          class="version-upload-bar__pick"
          :max="1"
          :default-upload="false"
          :show-file-list="false"
          v-model:file-list="versionUploadFileList"
          @change="onVersionFileChange"
        >
          <n-button size="small" secondary>{{ versionUploadFileLabel }}</n-button>
        </n-upload>
        <n-button
          class="version-upload-bar__submit"
          size="small"
          type="primary"
          :loading="versionUploading"
          :disabled="!versionUploadFile || versionUploading"
          @click="submitVersionUpload"
        >
          上传新版本
        </n-button>
      </div>
    </n-card>

    <n-card v-if="showAccessCard" title="发布与分享">
      <div class="access-current-loc">
        <span class="access-current-loc__label">当前位置</span>
        <n-tag type="info" size="small" :bordered="false">{{ currentScopeLabel }}</n-tag>
      </div>

      <n-radio-group v-model:value="accessMode" class="access-mode-group">
        <n-space>
          <n-radio v-if="showPublishCard" value="publish">发布到文库</n-radio>
          <n-radio v-if="canGrantAcl" value="share">分享给个人</n-radio>
        </n-space>
      </n-radio-group>

      <template v-if="accessMode === 'publish' && showPublishCard">
        <p class="access-card-hint">
          可选择小组级 / 部门级 / 公司级发布位置；发布后按分级默认可见，不会进入「分享」Tab。
        </p>
        <n-radio-group v-model:value="publishTarget" class="access-publish-target">
          <n-space>
            <n-radio v-if="canPublishCompany" value="company">公司级</n-radio>
            <n-radio v-if="canPublishDept" value="department">部门级</n-radio>
            <n-radio v-if="showTeamPublish" value="team">小组级</n-radio>
          </n-space>
        </n-radio-group>
        <OrgDeptPickerTree
          v-if="ORG_SCOPES.includes(publishTarget) && aclDepartments.length"
          :departments="aclDepartments"
          v-model:department-ids="publishDeptIds"
          :max-height="280"
          style="margin-bottom: 12px"
        />
        <n-button
          type="primary"
          :loading="publishLoading"
          :disabled="ORG_SCOPES.includes(publishTarget) && !publishDeptIds.length"
          @click="publishToLibrary"
        >
          {{ doc.scope === "personal" ? "发布" : "更新发布位置" }}
        </n-button>
      </template>

      <template v-else-if="accessMode === 'share' && canGrantAcl">
        <p class="access-card-hint">
          按用户授予可见 / 可查 / 可修改权限；被分享者可在「分享」中查看。
          勾选部门将展开为该部门全部用户；也可单独勾选用户。
        </p>
        <OrgUserPickerTree
          v-if="aclCandidates.length || aclDepartments.length"
          mode="multi"
          :departments="aclDepartments"
          :users="aclCandidates"
          v-model:checked-keys="shareSelectedKeys"
          :max-height="320"
        />
        <n-space v-if="aclCandidates.length" style="margin-top: 12px" wrap>
          <n-button
            v-for="act in sharePermissionActions"
            :key="act.level"
            size="small"
            :loading="shareGranting"
            :disabled="!shareSelectedKeys.length"
            @click="grantShareLevel(act.level)"
          >
            {{ act.label }}（{{ act.desc }}）
          </n-button>
        </n-space>
        <n-divider v-if="shares.length" style="margin: 16px 0" />
        <p v-if="shares.length" style="margin: 0 0 8px; font-weight: 500; font-size: 13px">
          当前已授权
        </p>
        <n-table v-if="shares.length" :single-line="false">
          <thead>
            <tr>
              <th>用户</th>
              <th>权限</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in shares" :key="s.user_id">
              <td>{{ s.user_name || userNameById[s.user_id] || "未知用户" }}</td>
              <td>{{ LEVEL_LABELS[s.level] || s.level }}</td>
              <td>
                <n-button text type="error" size="small" @click="removeShare(s.user_id)">
                  取消分享
                </n-button>
              </td>
            </tr>
          </tbody>
        </n-table>
        <span v-else>暂无个人分享。</span>
      </template>
    </n-card>

    <n-card v-if="canDenyAcl" title="访问限制">
      <p style="margin: 0 0 12px; color: #666; font-size: 13px">
        屏蔽在部门/公司分级下本应可见的成员；仅文档创建人或系统管理员可操作。
      </p>
      <template #header-extra>
        <n-button size="small" @click="openDenyModal">禁止用户访问</n-button>
      </template>
      <n-table v-if="denials.length" :single-line="false">
        <thead>
          <tr>
            <th>用户</th>
            <th>原因</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in denials" :key="d.id">
            <td>{{ d.user_name || userNameById[d.user_id] || "未知用户" }}</td>
            <td>{{ d.reason || "—" }}</td>
            <td>
              <n-button text type="primary" size="small" @click="removeDenial(d.user_id)">
                恢复
              </n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
      <span v-else>未设置禁止访问名单。</span>
    </n-card>
  </n-space>

  <n-modal v-model:show="showDeny" preset="card" title="禁止用户访问" style="width: 520px">
    <n-form>
      <n-form-item label="用户">
        <OrgUserPickerTree
          v-if="aclCandidates.length || aclDepartments.length"
          mode="single"
          :departments="aclDepartments"
          :users="aclCandidates"
          v-model:selected-key="denyUserId"
          :max-height="360"
        />
      </n-form-item>
      <n-form-item label="原因">
        <n-input v-model:value="denyReason" type="textarea" placeholder="可选" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showDeny = false">取消</n-button>
        <n-button type="warning" @click="submitDeny">确定</n-button>
      </n-space>
    </template>
  </n-modal>

  <DocumentVersionPreviewModal
    v-model:show="showVersionPreview"
    :document-id="docId"
    :version="previewVersion"
    @download="onPreviewDownload"
  />

  <AdminFormModal
    v-model:show="reindexModalShow"
    :title="reindexTargetVersion ? `重新索引 v${reindexTargetVersion.version_no}` : '重新索引'"
    subtitle="将全量同步到知识库并按所选解析器重新索引"
    width="420px"
  >
    <n-form label-placement="top" :show-require-mark="false">
      <n-form-item label="PDF 解析器">
        <n-select
          v-model:value="layoutRecognize"
          :options="layoutOptions"
          :disabled="indexPolling || reparsing"
        />
      </n-form-item>
      <n-form-item label="分块方法">
        <n-select
          v-model:value="parserId"
          :options="chunkMethodOptions"
          :disabled="indexPolling || reparsing"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="reindexModalShow = false">取消</n-button>
        <n-button
          type="primary"
          :loading="reparsing || indexPolling"
          @click="submitReindex"
        >
          开始索引
        </n-button>
      </n-space>
    </template>
  </AdminFormModal>

</template>

<style scoped>
.doc-title-input {
  min-width: 240px;
  max-width: min(560px, 100%);
  font-weight: 600;
}

.version-upload-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: center;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--platform-border, #e2e8f0);
}

.version-upload-bar__desc {
  min-width: 0;
}

.version-upload-bar__pick {
  flex-shrink: 0;
}

.version-upload-bar__pick :deep(.n-upload-trigger) {
  display: inline-flex;
}

.version-upload-bar__submit {
  flex-shrink: 0;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .version-upload-bar {
    grid-template-columns: 1fr;
  }
}

.access-current-loc {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--platform-accent-muted, #f1f5f9);
  border: 1px solid var(--platform-border, #e2e8f0);
}

.access-current-loc__label {
  font-size: 13px;
  color: var(--platform-text-secondary, #64748b);
  flex-shrink: 0;
}

.access-mode-group {
  margin-bottom: 14px;
}

.access-publish-target {
  margin-bottom: 12px;
}

.access-card-hint {
  margin: 0 0 12px;
  color: var(--platform-text-secondary, #666);
  font-size: 13px;
  line-height: 1.55;
}
</style>
