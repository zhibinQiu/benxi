<script setup>
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
  useMessage,
  useDialog,
} from "naive-ui";
import { DownloadOutline, TrashOutline } from "@vicons/ionicons5";
import IconAction from "../components/IconAction.vue";
import {
  fetchDocument,
  updateDocument,
  prepareUpload,
  uploadDocumentBlob,
  completeUpload,
  downloadDocumentFile,
  deleteDocumentVersion,
  patchDocumentStatus,
  restoreDocument,
  permanentlyDeleteDocument,
  fetchDocumentAccessControl,
  fetchDocumentAclCandidates,
  fetchDocumentShares,
  grantDocumentShares,
  revokeDocumentShare,
  fetchDocumentDenials,
  denyDocumentAccess,
  liftDocumentDenial,
} from "../api/client";
import { useAuth } from "../composables/useAuth";
import OrgUserPickerTree from "../components/OrgUserPickerTree.vue";
import OrgDeptPickerTree from "../components/OrgDeptPickerTree.vue";
import DocumentKnowledgePanel from "../components/DocumentKnowledgePanel.vue";
import { knowledgeIndexTagProps } from "../utils/knowledgeIndex.js";
import { userLabel } from "../utils/orgUserTree";
import { goBackToEntry, navigateWithReturn } from "../utils/navigationReturn";
import { ORG_SCOPES, SCOPE_LABELS, SCOPE_PERM } from "../constants/documentScope";
const LEVEL_LABELS = {
  visible: "可见",
  query: "可查询",
  edit: "可编辑",
  full: "完全",
  read: "可见",
  use: "可编辑",
  delete: "完全",
};

const route = useRoute();
const router = useRouter();

function goBack() {
  goBackToEntry(router, route, { name: "documents" });
}

const message = useMessage();
const dialog = useDialog();

const { user, hasPerm } = useAuth();

const docId = route.params.id;
const doc = ref(null);
const loading = ref(false);
const editTitle = ref("");
const titleEditing = ref(false);
const titleSaving = ref(false);
const titleInputRef = ref(null);

const canEditDoc = computed(() => aclCaps.value.can_edit === true);

const canDeleteDoc = computed(() => aclCaps.value.can_delete === true);

const canManageDoc = computed(() => aclCaps.value.can_manage === true);

const canRestoreDoc = computed(() => aclCaps.value.can_restore === true);

const canViewDoc = computed(() => aclCaps.value.can_view !== false);

const isInRecycle = computed(() => Boolean(doc.value?.deleted_at));

const statusEnabled = computed({
  get: () => doc.value?.status === "active",
  set: () => {},
});

const isOwner = computed(
  () => user.value?.id && doc.value?.owner_id === user.value.id
);

const ownerLabel = computed(() => doc.value?.owner_name || "未知用户");

const uploadedAtLabel = computed(() => {
  const t = doc.value?.uploaded_at || doc.value?.created_at;
  return t ? new Date(t).toLocaleString() : "—";
});

const displayVersions = computed(() => doc.value?.versions || []);

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
  effective_level: null,
});

const canGrantAcl = computed(() => aclCaps.value.can_grant);
const canDenyAcl = computed(() => aclCaps.value.can_deny);
const canManageAcl = computed(() => canGrantAcl.value || canDenyAcl.value);

const shares = ref([]);
const denials = ref([]);
const showDeny = ref(false);
const aclPicker = ref({
  company_label: "公司",
  departments: [],
  users: [],
});
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

const canPublishCompany = computed(
  () => isOwner.value && hasPerm("doc.company.create")
);
const canPublishDept = computed(() => isOwner.value && hasPerm("doc.dept.create"));
const canPublishTeam = computed(() => isOwner.value && hasPerm("doc.team.create"));
const showPublishCard = computed(
  () =>
    !isInRecycle.value &&
    (canPublishCompany.value || canPublishDept.value || canPublishTeam.value)
);
const showAccessCard = computed(
  () => !isInRecycle.value && (showPublishCard.value || canGrantAcl.value)
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
  if (ORG_SCOPES.includes(s) && doc.value?.dept_id) {
    const d = aclDepartments.value.find((x) => x.id === doc.value.dept_id);
    const tier = SCOPE_LABELS[s] || s;
    return `${tier} · ${d?.name || "已选组织"}`;
  }
  return SCOPE_LABELS[s] || s;
});

const supportsKbFolder = computed(() =>
  ["company", "department", "team", "personal"].includes(doc.value?.scope)
);

const sharePermissionActions = [
  { level: "visible", label: "可见", desc: "下载、预览" },
  { level: "query", label: "可查询", desc: "知识问答" },
  { level: "edit", label: "可编辑", desc: "上传/翻译/对比" },
  { level: "full", label: "完全", desc: "含删除" },
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
  if (!doc.value || !canEditDoc.value || isInRecycle.value) return;
  editTitle.value = doc.value.title || "";
  titleEditing.value = true;
  nextTick(() => titleInputRef.value?.focus());
}

function cancelEditTitle() {
  editTitle.value = doc.value?.title || "";
  titleEditing.value = false;
}

async function saveTitle() {
  if (!doc.value || !canEditDoc.value || isInRecycle.value) return;
  const next = editTitle.value.trim();
  if (!next) {
    message.warning("标题不能为空");
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
    message.success("标题已保存");
  } catch (e) {
    editTitle.value = doc.value.title;
    message.error(e.message);
  } finally {
    titleSaving.value = false;
  }
}

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    doc.value = await fetchDocument(docId);
    editTitle.value = doc.value.title || "";
    syncAccessModeDefault();
    if (doc.value.scope === "company") {
      publishTarget.value = "company";
    } else if (doc.value.scope === "department" && doc.value.dept_id) {
      publishTarget.value = "department";
      publishDeptIds.value = [doc.value.dept_id];
    } else {
      publishTarget.value = "department";
      publishDeptIds.value = [];
    }
    try {
      aclCaps.value = await fetchDocumentAccessControl(docId);
    } catch {
      aclCaps.value = {
        can_grant: false,
        can_deny: false,
        is_owner: false,
        can_view: true,
        can_query: false,
        can_edit: false,
        can_delete: false,
        can_manage: false,
        can_restore: false,
      };
    }
    shares.value = [];
    denials.value = [];
    const docOwner =
      user.value?.id && doc.value?.owner_id === user.value.id;
    if (canGrantAcl.value || docOwner) {
      await loadAclCandidates();
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
    if (notifyOnError) message.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function uploadVersion({ file, onFinish, onError }) {
  const raw = file?.file;
  if (!raw) {
    onError?.();
    return;
  }
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
    });
    message.success("新版本已上传，知识库正在后台同步");
    await load({ notifyOnError: false });
    onFinish?.();
  } catch (e) {
    message.error(e.message);
    onError?.();
  }
}

async function downloadVersion(v) {
  if (!v?.uploaded) return;
  try {
    const fallback =
      v.file_name || `${doc.value?.title || "document"}.pdf`;
    await downloadDocumentFile(docId, fallback, v.id);
    message.success("已开始下载");
  } catch (e) {
    message.error(e.message);
  }
}

async function onStatusChange(enabled) {
  if (!canManageDoc.value) return;
  const next = enabled ? "active" : "disabled";
  try {
    doc.value = await patchDocumentStatus(docId, next);
    message.success(enabled ? "已启用" : "已关闭");
  } catch (e) {
    message.error(e.message);
    await load({ notifyOnError: false });
  }
}

function confirmDeleteVersion(v) {
  const label = `v${v.version_no}`;
  const hint = displayVersions.value.length <= 1
    ? "这是最后一个版本，删除后整份文档将移入回收站。"
    : "仅删除该版本文件，其他版本保留。";
  dialog.warning({
    title: `删除版本 ${label}`,
    content: `${hint} 确定继续？`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        const res = await deleteDocumentVersion(docId, v.id);
        if (res.document_deleted) {
          message.success(res.message || "文档已移入回收站");
          goBack();
          return;
        }
        message.success(res.message || "版本已删除");
        await load({ notifyOnError: false });
      } catch (e) {
        message.error(e.message);
      }
    },
  });
}

function handlePermanentDelete() {
  if (!doc.value) return;
  dialog.warning({
    title: "彻底删除",
    content: `确定彻底删除「${doc.value.title}」？删除后无法恢复。`,
    positiveText: "彻底删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await permanentlyDeleteDocument(docId);
        message.success("已彻底删除");
        goBack();
      } catch (e) {
        message.error(e.message);
        return false;
      }
      return true;
    },
  });
}

async function handleRestore() {
  try {
    doc.value = await restoreDocument(docId);
    message.success("已恢复");
    navigateWithReturn(
      router,
      { name: "document-detail", params: { id: docId } },
      route
    );
    await load({ notifyOnError: false });
  } catch (e) {
    message.error(e.message);
  }
}

async function publishToLibrary() {
  if (ORG_SCOPES.includes(publishTarget.value)) {
    if (!publishDeptIds.value.length) {
      message.warning("请选择要发布到的组织单元");
      return;
    }
    if (publishTarget.value === "team" && !canPublishTeam.value) {
      message.warning("无权发布到小组级文库");
      return;
    }
    if (publishTarget.value === "department" && !canPublishDept.value) {
      message.warning("无权发布到部门级文库");
      return;
    }
  } else if (!canPublishCompany.value) {
    message.warning("无权发布到公司级文库");
    return;
  }
  publishLoading.value = true;
  try {
    const payload = { scope: publishTarget.value };
    if (ORG_SCOPES.includes(publishTarget.value)) {
      payload.dept_id = publishDeptIds.value[0];
    }
    doc.value = await updateDocument(docId, payload);
    message.success("已发布到文库，可在文档库对应分级中查看");
    await load({ notifyOnError: false });
  } catch (e) {
    message.error(e.message);
  } finally {
    publishLoading.value = false;
  }
}

async function grantShareLevel(level) {
  if (!shareSelectedKeys.value.length) {
    message.warning("请先勾选要分享的用户");
    return;
  }
  shareGranting.value = true;
  try {
    shares.value = await grantDocumentShares(docId, {
      userIds: shareSelectedKeys.value,
      level,
    });
    const label = LEVEL_LABELS[level] || level;
    message.success(
      `已为 ${shareSelectedKeys.value.length} 人授予「${label}」权限`
    );
  } catch (e) {
    message.error(e.message);
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
    message.error(e.message);
  }
}

async function removeShare(userId) {
  try {
    await revokeDocumentShare(docId, userId);
    message.success("已取消该用户的分享");
    shares.value = await fetchDocumentShares(docId);
  } catch (e) {
    message.error(e.message);
  }
}

async function submitDeny() {
  if (!denyUserId.value) {
    message.warning("请选择要禁止访问的用户");
    return;
  }
  try {
    await denyDocumentAccess(docId, {
      user_id: denyUserId.value,
      reason: denyReason.value,
    });
    message.success("已禁止该用户访问（部门/公司默认可见规则不再生效）");
    showDeny.value = false;
    denyUserId.value = null;
    denyReason.value = "";
    denials.value = await fetchDocumentDenials(docId);
  } catch (e) {
    message.error(e.message);
  }
}

async function removeDenial(uid) {
  try {
    await liftDocumentDenial(docId, uid);
    message.success("已恢复访问");
    denials.value = await fetchDocumentDenials(docId);
  } catch (e) {
    message.error(e.message);
  }
}

onMounted(load);
</script>

<template>
  <n-space vertical :size="16" v-if="doc">
    <n-card :loading="loading">
      <template #header>
        <n-space align="center" :size="12" style="flex-wrap: wrap">
          <template v-if="titleEditing && canEditDoc && !isInRecycle">
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
              v-if="canEditDoc && !isInRecycle"
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
          <n-space v-if="!isInRecycle" align="center" :size="8">
            <n-switch
              :value="statusEnabled"
              :disabled="!canManageDoc"
              @update:value="onStatusChange"
            />
            <span>{{ statusEnabled ? "启用" : "关闭" }}</span>
          </n-space>
          <n-tag v-else size="small" type="warning">回收站</n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="分级">
          <n-tag size="small">{{ SCOPE_LABELS[doc.scope] || doc.scope }}</n-tag>
        </n-descriptions-item>
        <n-descriptions-item v-if="supportsKbFolder" label="所在文件夹">
          {{ doc.folder_name || "未分类" }}
        </n-descriptions-item>
        <n-descriptions-item
          v-if="doc.scope === 'department' && (doc.dept_name || doc.dept_id)"
          label="所属部门"
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

    <n-card v-if="canEditDoc && !isInRecycle" title="上传新版本">
      <n-upload :max="1" :custom-request="uploadVersion">
        <n-button>选择文件并上传</n-button>
      </n-upload>
    </n-card>

    <DocumentKnowledgePanel
      v-if="canViewDoc && !isInRecycle"
      :document-id="docId"
      :title="doc.title"
      :versions="doc.versions || []"
      :current-version-id="doc.current_version_id"
      :can-manage="canEditDoc"
      @updated="load({ notifyOnError: false })"
    />

    <n-card title="版本历史">
      <template #header-extra>
        <n-space v-if="isInRecycle" :size="8">
          <n-button
            v-if="canRestoreDoc"
            type="primary"
            size="small"
            @click="handleRestore"
          >
            恢复文档
          </n-button>
          <n-button size="small" secondary @click="handlePermanentDelete">
            彻底删除
          </n-button>
        </n-space>
        <n-text v-else-if="!isInRecycle" depth="3" style="font-size: 13px">
          每个文档至少保留一个已上传版本；删光全部版本后文档进入回收站
        </n-text>
      </template>
      <n-table :single-line="false">
        <thead>
          <tr>
            <th>版本</th>
            <th>文件名</th>
            <th>大小</th>
            <th>时间</th>
            <th v-if="!isInRecycle">索引</th>
            <th v-if="!isInRecycle && (canViewDoc || canDeleteDoc)">操作</th>
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
            <td>{{ versionSizeLabel(v) }}</td>
            <td>{{ new Date(v.created_at).toLocaleString() }}</td>
            <td v-if="!isInRecycle">
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
            <td v-if="!isInRecycle && (canViewDoc || canDeleteDoc)">
              <div class="table-icon-actions">
                <IconAction
                  v-if="v.uploaded && canViewDoc"
                  label="下载"
                  :icon="DownloadOutline"
                  type="primary"
                  @click="downloadVersion(v)"
                />
                <IconAction
                  v-if="canDeleteDoc"
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
    </n-card>

    <n-card v-if="showAccessCard" title="发布与分享">
      <n-radio-group v-model:value="accessMode" style="margin-bottom: 14px">
        <n-space>
          <n-radio v-if="showPublishCard" value="publish">发布到文库</n-radio>
          <n-radio v-if="canGrantAcl" value="share">分享给个人</n-radio>
        </n-space>
      </n-radio-group>

      <template v-if="accessMode === 'publish' && showPublishCard">
        <p style="margin: 0 0 12px; color: #666; font-size: 13px">
          发布后文档出现在文档库「部门级」或「公司级」中，按分级默认可见；不会进入「分享」Tab。
          当前：{{ currentScopeLabel }}。
        </p>
        <n-radio-group v-model:value="publishTarget" style="margin-bottom: 12px">
          <n-space>
            <n-radio v-if="canPublishCompany" value="company">公司级</n-radio>
            <n-radio v-if="canPublishDept" value="department">部门级</n-radio>
            <n-radio v-if="canPublishTeam" value="team">小组级</n-radio>
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
        <p style="margin: 0 0 12px; color: #666; font-size: 13px">
          仅用于个人文档的例外协作：被分享者可在「分享」中查看，不会进入部门/公司文库。
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

    <n-card v-if="canDenyAcl && !isInRecycle" title="访问限制">
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

</template>

<style scoped>
.doc-title-input {
  min-width: 240px;
  max-width: min(560px, 100%);
  font-weight: 600;
}
</style>
