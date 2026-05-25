<script setup>
import { computed, onMounted, ref } from "vue";
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
  NDataTable,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSwitch,
  NText,
  NDivider,
  useMessage,
  useDialog,
} from "naive-ui";
import {
  fetchDocument,
  updateDocument,
  prepareUpload,
  completeUpload,
  getDownloadUrl,
  deleteDocumentVersion,
  patchDocumentStatus,
  restoreDocument,
  permanentlyDeleteDocument,
  fetchDocumentAccessControl,
  fetchDocumentAclCandidates,
  fetchDocumentPermissions,
  grantPermission,
  revokePermission,
  fetchDocumentDenials,
  denyDocumentAccess,
  liftDocumentDenial,
} from "../api/client";
import { useAuth } from "../composables/useAuth";

const SCOPE_LABELS = {
  company: "公司级",
  department: "部门级",
  personal: "个人级",
};
const SCOPE_PERM = {
  company: "doc.company",
  department: "doc.dept",
  personal: "doc.personal",
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

const route = useRoute();
const router = useRouter();
const message = useMessage();
const dialog = useDialog();

const { user } = useAuth();

const docId = route.params.id;
const doc = ref(null);
const loading = ref(false);
const editTitle = ref("");
const titleSaving = ref(false);

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

const canDownloadFile = computed(() =>
  displayVersions.value.some((v) => v.is_current && v.uploaded)
);

function versionFileLabel(v) {
  if (v.uploaded && v.file_name) return v.file_name;
  return v.file_name || "（尚未上传）";
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

const perms = ref([]);
const denials = ref([]);
const showDeny = ref(false);
const aclCandidates = ref([]);
const denyUserId = ref(null);
const denyReason = ref("");
const shareSelectedKeys = ref([]);
const shareGranting = ref(false);

const shareColumns = [
  { type: "selection" },
  {
    title: "用户",
    key: "username",
    render: (row) => userLabel(row),
  },
  {
    title: "部门",
    key: "department_names",
    render: (row) => (row.department_names || []).join("、") || "—",
  },
];

const sharePermissionActions = [
  { level: "visible", label: "可见", desc: "下载、预览" },
  { level: "query", label: "可查询", desc: "知识问答" },
  { level: "edit", label: "可编辑", desc: "上传/翻译/对比" },
  { level: "full", label: "完全", desc: "含删除" },
];

function userLabel(u) {
  return u.username || "—";
}

const userSelectOptions = computed(() =>
  aclCandidates.value.map((u) => ({
    label: userLabel(u),
    value: u.id,
  }))
);

const userNameById = computed(() => {
  const m = {};
  for (const u of aclCandidates.value) {
    m[u.id] = userLabel(u);
  }
  for (const p of perms.value) {
    if (p.subject_type === "user" && p.subject_label) {
      m[p.subject_id] = p.subject_label;
    }
  }
  return m;
});

async function loadAclCandidates() {
  if (!canManageAcl.value) return;
  try {
    aclCandidates.value = await fetchDocumentAclCandidates(docId);
  } catch {
    aclCandidates.value = [];
  }
}

async function ensureCandidates() {
  if (!aclCandidates.value.length) {
    await loadAclCandidates();
  }
}

async function saveTitle() {
  if (!doc.value || !canEditDoc.value || isInRecycle.value) return;
  const next = editTitle.value.trim();
  if (!next) {
    message.warning("标题不能为空");
    editTitle.value = doc.value.title;
    return;
  }
  if (next === doc.value.title) return;
  titleSaving.value = true;
  try {
    doc.value = await updateDocument(docId, { title: next });
    editTitle.value = doc.value.title;
    message.success("标题已保存");
  } catch (e) {
    editTitle.value = doc.value.title;
    message.error(e.message);
  } finally {
    titleSaving.value = false;
  }
}

async function load() {
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
        can_edit: false,
        can_delete: false,
        can_manage: false,
        can_restore: false,
      };
    }
    await loadAclCandidates();
    perms.value = [];
    denials.value = [];
    if (canGrantAcl.value) {
      await loadAclCandidates();
      try {
        perms.value = await fetchDocumentPermissions(docId);
      } catch {
        perms.value = [];
      }
    } else {
      aclCandidates.value = [];
      perms.value = [];
    }
    if (canDenyAcl.value) {
      try {
        denials.value = await fetchDocumentDenials(docId);
      } catch {
        denials.value = [];
      }
    }
  } catch (e) {
    message.error(e.message);
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
    const putRes = await fetch(prep.upload_url, {
      method: "PUT",
      body: raw,
      headers: { "Content-Type": raw.type || "application/octet-stream" },
    });
    if (!putRes.ok) throw new Error("上传失败");
    await completeUpload(docId, {
      version_id: prep.version_id,
      file_size: raw.size,
    });
    message.success("新版本已上传");
    await load();
    onFinish?.();
  } catch (e) {
    message.error(e.message);
    onError?.();
  }
}

async function download() {
  try {
    const { download_url } = await getDownloadUrl(docId);
    window.open(download_url, "_blank");
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
    await load();
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
          router.push({ name: "documents", query: { view: "recycle" } });
          return;
        }
        message.success(res.message || "版本已删除");
        await load();
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
        router.push({ name: "documents", query: { view: "recycle" } });
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
    router.push({ name: "document-detail", params: { id: docId } });
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

async function grantShareLevel(level) {
  if (!shareSelectedKeys.value.length) {
    message.warning("请先勾选要分享的用户");
    return;
  }
  shareGranting.value = true;
  try {
    for (const uid of shareSelectedKeys.value) {
      await grantPermission(docId, {
        subject_type: "user",
        subject_id: uid,
        level,
      });
    }
    const label = LEVEL_LABELS[level] || level;
    message.success(
      `已为 ${shareSelectedKeys.value.length} 人授予「${label}」权限`
    );
    perms.value = await fetchDocumentPermissions(docId);
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

async function removePerm(permId) {
  try {
    await revokePermission(docId, permId);
    message.success("已移除");
    perms.value = await fetchDocumentPermissions(docId);
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
          <n-input
            v-if="canEditDoc && !isInRecycle"
            v-model:value="editTitle"
            class="doc-title-input"
            placeholder="文档标题"
            maxlength="512"
            :loading="titleSaving"
            :disabled="titleSaving"
            @blur="saveTitle"
            @keyup.enter="saveTitle"
          />
          <n-text v-else strong style="font-size: 16px">{{ doc.title }}</n-text>
        </n-space>
      </template>
      <template #header-extra>
        <n-space>
          <n-button @click="router.push({ name: 'documents' })">返回</n-button>
          <n-button
            type="primary"
            :disabled="!canDownloadFile || !canViewDoc"
            @click="download"
          >
            下载
          </n-button>
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
          按版本删除；删光全部版本后文档进入回收站
        </n-text>
      </template>
      <n-table :single-line="false">
        <thead>
          <tr>
            <th>版本</th>
            <th>文件名</th>
            <th>大小</th>
            <th>时间</th>
            <th v-if="!isInRecycle && canDeleteDoc">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in displayVersions" :key="v.id">
            <td>
              <n-space :size="6" align="center">
                <span>v{{ v.version_no }}</span>
                <n-tag v-if="v.is_current" size="small" type="info">当前</n-tag>
                <n-tag v-if="!v.uploaded" size="small">待上传</n-tag>
              </n-space>
            </td>
            <td>{{ versionFileLabel(v) }}</td>
            <td>{{ versionSizeLabel(v) }}</td>
            <td>{{ new Date(v.created_at).toLocaleString() }}</td>
            <td v-if="!isInRecycle && canDeleteDoc">
              <n-button
                text
                type="error"
                size="small"
                @click="confirmDeleteVersion(v)"
              >
                删除
              </n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <n-card v-if="canGrantAcl && !isInRecycle" title="分享">
      <p style="margin: 0 0 12px; color: #666; font-size: 13px">
        先勾选要分享的用户，再点击下方权限按钮完成授权（默认建议「可见」）。
      </p>
      <n-data-table
        v-if="aclCandidates.length"
        :columns="shareColumns"
        :data="aclCandidates"
        :row-key="(row) => row.id"
        :checked-row-keys="shareSelectedKeys"
        @update:checked-row-keys="(keys) => (shareSelectedKeys = keys)"
        size="small"
        :max-height="280"
      />
      <span v-else style="color: #999; font-size: 13px">暂无可选用户</span>
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
      <n-divider v-if="perms.length" style="margin: 16px 0" />
      <p v-if="perms.length" style="margin: 0 0 8px; font-weight: 500; font-size: 13px">
        已分享用户
      </p>
      <n-table v-if="perms.length" :single-line="false">
        <thead>
          <tr>
            <th>用户</th>
            <th>级别</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in perms" :key="p.id">
            <td>
              {{
                p.subject_type === "user"
                  ? p.subject_label || userNameById[p.subject_id] || "未知用户"
                  : p.subject_type
              }}
            </td>
            <td>{{ LEVEL_LABELS[p.level] || p.level }}</td>
            <td>
              <n-button text type="error" size="small" @click="removePerm(p.id)">移除</n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
      <span v-else>暂无额外授权。个人文档默认仅自己可见；部门/公司文档默认按分级与角色可见。</span>
    </n-card>

    <n-card v-if="canDenyAcl && !isInRecycle" title="访问限制">
      <p style="margin: 0 0 12px; color: #666; font-size: 13px">
        屏蔽在部门/公司分级下本应可见的成员；个人文档仅创建人或系统管理员可操作。
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

  <n-modal v-model:show="showDeny" preset="card" title="禁止用户访问" style="width: 480px">
    <n-form>
      <n-form-item label="用户">
        <n-select
          v-model:value="denyUserId"
          :options="userSelectOptions"
          filterable
          placeholder="搜索并选择员工"
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
