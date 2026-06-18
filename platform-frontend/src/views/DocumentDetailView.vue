<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, nextTick, onMounted, ref, watch } from "vue";
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
  NAlert,
} from "naive-ui";
import {
  DownloadOutline,
  EyeOutline,
  GitCompareOutline,
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
import { useI18n } from "../composables/useI18n";
import { useDocumentLibrary } from "../composables/useDocumentLibrary.js";
import OrgUserPickerTree from "../components/OrgUserPickerTree.vue";
import OrgDeptPickerTree from "../components/OrgDeptPickerTree.vue";
import { useDocumentReindex } from "../composables/useDocumentReindex.js";
import { knowledgeIndexTagProps } from "../utils/knowledgeIndex.js";
import { userLabel } from "../utils/orgUserTree";
import { goBackToEntry, navigateWithReturn } from "../utils/navigationReturn";
import { ORG_SCOPES } from "../constants/documentScope";
import {
  validateUploadFiles,
  validateVersionFormatMatch,
} from "../constants/documentUpload";
import {
  canDeleteDocument,
  canModifyDocument,
  canViewDocument,
  emptyDocumentAclCaps,
} from "../utils/documentCaps.js";
import { MIN_COMPARE_COLS } from "../utils/compareDocument.js";

const route = useRoute();
const router = useRouter();

function goBack() {
  goBackToEntry(router, route, { name: "documents" });
}

const ui = usePlatformUi();

const { user, hasPerm } = useAuth();
const { t, docLevelLabel, scopeLabel } = useI18n();
const { ensureUploadLimits } = useDocumentLibrary();

const docId = route.params.id;
const doc = ref(null);
const loading = ref(false);
const aclLoading = ref(false);
const editTitle = ref("");
const titleEditing = ref(false);
const titleSaving = ref(false);
const titleInputRef = ref(null);

const canModifyDoc = computed(() => canModifyDocument(aclCaps.value));

const canDeleteDoc = computed(() => canDeleteDocument(aclCaps.value));

const canEditDoc = canModifyDoc;

const canManageDoc = canModifyDoc;

const canReindexDoc = canModifyDoc;

const canViewDoc = computed(() => canViewDocument(aclCaps.value));

const statusEnabled = computed({
  get: () => doc.value?.status === "active",
  set: () => {}});

const isOwner = computed(
  () => user.value?.id && doc.value?.owner_id === user.value.id
);

const ownerLabel = computed(() => doc.value?.owner_name || t("documents.unknownUser"));

const uploadedAtLabel = computed(() => {
  const t = doc.value?.uploaded_at || doc.value?.created_at;
  return t ? new Date(t).toLocaleString() : "—";
});

const displayVersions = computed(() => doc.value?.versions || []);

const uploadedVersionCount = computed(
  () => displayVersions.value.filter((v) => v.uploaded).length
);

const canCompareVersions = computed(
  () => canViewDoc.value && uploadedVersionCount.value >= MIN_COMPARE_COLS
);

const {
  reindexModalShow,
  reindexTargetVersion,
  parserId,
  layoutRecognize,
  chunkMethodOptions,
  layoutOptions,
  pageindexBlockReason,
  reparsing,
  indexPolling,
  loadParserOptions,
  openReindexModal,
  submitReindex,
  renderIndexedSelectLabel,
  reindexSelectNodeProps,
  reindexSelectMenuProps,
  reindexSelectPlacement,
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
    ui.warning(t("documents.detail.chooseFile"));
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
    ui.success(t("documents.detail.versionUploaded"));
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

const aclCaps = ref(emptyDocumentAclCaps());

const canGrantAcl = computed(() => aclCaps.value.can_grant);
const canDenyAcl = computed(() => aclCaps.value.can_deny);
const canManageAcl = computed(() => canGrantAcl.value || canDenyAcl.value);

const shares = ref([]);
const denials = ref([]);
const showDeny = ref(false);
function emptyAclPicker() {
  return {
    company_label: t("documents.detail.companyDefault"),
    departments: [],
    users: [],
  };
}

const aclPicker = ref(emptyAclPicker());
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
    const tier = scopeLabel(s) || s;
    const deptName =
      doc.value?.dept_name ||
      aclDepartments.value.find((x) => x.id === doc.value?.dept_id)?.name;
    return deptName ? `${tier} · ${deptName}` : tier;
  }
  return scopeLabel(s) || s;
});

const versionUploadFileLabel = computed(() => {
  const name = versionUploadFile.value?.name;
  if (!name) return t("common.fileDrop.selectFile");
  return name.length > 28 ? `${name.slice(0, 25)}…` : name;
});

const supportsKbFolder = computed(() =>
  ["company", "department", "team", "personal"].includes(doc.value?.scope)
);

const sharePermissionActions = computed(() => [
  {
    level: "visible",
    label: docLevelLabel("visible"),
    desc: t("documents.detail.visibleDesc"),
  },
  {
    level: "query",
    label: docLevelLabel("query"),
    desc: t("documents.detail.queryDesc"),
  },
  {
    level: "modify",
    label: docLevelLabel("modify"),
    desc: t("documents.detail.modifyDesc"),
  },
]);

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

function canLoadAclCandidates() {
  const docOwner = Boolean(
    user.value?.id && doc.value?.owner_id === user.value.id
  );
  return canManageAcl.value || docOwner;
}

async function loadAclCandidates() {
  if (!canLoadAclCandidates()) return;
  try {
    aclPicker.value = await fetchDocumentAclCandidates(docId);
  } catch {
    aclPicker.value = emptyAclPicker();
  }
}

async function ensureCandidates() {
  if (!canLoadAclCandidates()) return;
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
    ui.warning(t("documents.detail.titleEmpty"));
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
    ui.success(t("documents.detail.titleSaved"));
  } catch (e) {
    editTitle.value = doc.value.title;
    ui.error(e.message);
  } finally {
    titleSaving.value = false;
  }
}

function capsFromDoc(d) {
  if (!d) return emptyDocumentAclCaps();
  return {
    ...emptyDocumentAclCaps(),
    is_owner: Boolean(user.value?.id && d.owner_id === user.value.id),
    can_view: true,
    can_modify: Boolean(d.can_modify),
    can_edit: Boolean(d.can_edit),
    can_delete: Boolean(d.can_delete),
    can_manage: Boolean(d.can_modify),
    effective_level: d.effective_level ?? null,
  };
}

function applyPublishStateFromDoc(d) {
  if (!d) return;
  if (ORG_SCOPES.includes(d.scope)) {
    publishTarget.value = d.scope;
    publishDeptIds.value = d.dept_id ? [d.dept_id] : [];
  } else {
    publishTarget.value = "department";
    publishDeptIds.value = [];
  }
  syncAccessModeDefault();
}

async function loadAclData() {
  if (!doc.value) return;
  aclLoading.value = true;
  const docOwner = Boolean(
    user.value?.id && doc.value.owner_id === user.value.id
  );
  try {
    let caps = emptyDocumentAclCaps();
    try {
      caps = await fetchDocumentAccessControl(docId);
    } catch {
      caps = capsFromDoc(doc.value);
    }
    aclCaps.value = caps;

    const tasks = [];
    if (canGrantAcl.value || docOwner) {
      tasks.push(
        fetchDocumentShares(docId)
          .then((rows) => {
            shares.value = rows;
          })
          .catch(() => {
            shares.value = [];
          })
      );
    } else {
      shares.value = [];
      aclPicker.value = emptyAclPicker();
    }
    if (canDenyAcl.value) {
      tasks.push(
        fetchDocumentDenials(docId)
          .then((rows) => {
            denials.value = rows;
          })
          .catch(() => {
            denials.value = [];
          })
      );
    } else {
      denials.value = [];
    }
    await Promise.all(tasks);
    syncAccessModeDefault();
  } finally {
    aclLoading.value = false;
  }
}

function openVersionCompare() {
  navigateWithReturn(
    router,
    {
      name: "compare",
      query: { mode: "version", documentId: docId },
    },
    route
  );
}

async function refreshVersionHistory() {
  versionRefreshing.value = true;
  try {
    await load({ notifyOnError: false, liveIndex: true });
  } catch (e) {
    ui.error(e.message);
  } finally {
    versionRefreshing.value = false;
  }
}

async function load({ notifyOnError = true, liveIndex = false } = {}) {
  loading.value = true;
  try {
    doc.value = await fetchDocument(docId, { liveIndex });
    editTitle.value = doc.value.title || "";
    aclCaps.value = capsFromDoc(doc.value);
    applyPublishStateFromDoc(doc.value);
    shares.value = [];
    denials.value = [];
  } catch (e) {
    if (notifyOnError) ui.error(e.message);
  } finally {
    loading.value = false;
  }
  if (doc.value) {
    void loadAclData();
  }
}

async function downloadVersion(v) {
  if (!v?.uploaded) return;
  try {
    const fallback =
      v.file_name || `${doc.value?.title || "document"}.pdf`;
    await downloadDocumentFile(docId, fallback, v.id);
    ui.success(t("documents.detail.downloadStarted"));
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
    ui.success(enabled ? t("documents.detail.statusEnabled") : t("documents.detail.statusDisabled"));
  } catch (e) {
    ui.error(e.message);
    await load({ notifyOnError: false });
  }
}

function confirmDeleteVersion(v) {
  const label = `v${v.version_no}`;
  const hint =
    displayVersions.value.length <= 1
      ? t("documents.detail.deleteLastVersionHint")
      : t("documents.detail.deleteVersionHint");
  ui.confirmDelete({
    title: t("documents.detail.deleteVersionTitle", { label }),
    content: `${hint} ${t("documents.detail.deleteConfirmContinue")}`,
    onPositive: async () => {
      const res = await deleteDocumentVersion(docId, v.id);
      if (res.document_deleted) {
        ui.success(res.message || t("documents.detail.docDeleted"));
        goBack();
        return;
      }
      ui.success(res.message || t("documents.detail.versionDeleted"));
      await load({ notifyOnError: false });
    },
  });
}

async function publishToLibrary() {
  if (ORG_SCOPES.includes(publishTarget.value)) {
    if (!publishDeptIds.value.length) {
      ui.warning(t("documents.detail.selectPublishOrg"));
      return;
    }
    if (publishTarget.value === "team" && !showTeamPublish.value) {
      ui.warning(t("documents.detail.noTeamPublish"));
      return;
    }
    if (publishTarget.value === "department" && !canPublishDept.value) {
      ui.warning(t("documents.detail.noDeptPublish"));
      return;
    }
  } else if (!canPublishCompany.value) {
    ui.warning(t("documents.detail.noCompanyPublish"));
    return;
  }
  publishLoading.value = true;
  try {
    const payload = { scope: publishTarget.value };
    if (ORG_SCOPES.includes(publishTarget.value)) {
      payload.dept_id = publishDeptIds.value[0];
    }
    doc.value = await updateDocument(docId, payload);
    ui.success(t("documents.detail.publishedToLibrary"));
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e.message);
  } finally {
    publishLoading.value = false;
  }
}

async function grantShareLevel(level) {
  if (!shareSelectedKeys.value.length) {
    ui.warning(t("documents.detail.selectShareUsers"));
    return;
  }
  shareGranting.value = true;
  try {
    shares.value = await grantDocumentShares(docId, {
      userIds: shareSelectedKeys.value,
      level});
    const label = docLevelLabel(level) || level;
    ui.success(
      t("documents.detail.grantedToUsers", {
        count: shareSelectedKeys.value.length,
        label,
      })
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
    ui.success(t("documents.detail.shareRevoked"));
    shares.value = await fetchDocumentShares(docId);
  } catch (e) {
    ui.error(e.message);
  }
}

async function submitDeny() {
  if (!denyUserId.value) {
    ui.warning(t("documents.detail.selectDenyUser"));
    return;
  }
  try {
    await denyDocumentAccess(docId, {
      user_id: denyUserId.value,
      reason: denyReason.value});
    ui.success(t("documents.detail.denySuccess"));
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
    ui.success(t("documents.detail.accessRestored"));
    denials.value = await fetchDocumentDenials(docId);
  } catch (e) {
    ui.error(e.message);
  }
}

watch(
  () => {
    if (!showAccessCard.value) return false;
    const docOwner = Boolean(
      user.value?.id && doc.value?.owner_id === user.value.id
    );
    if (accessMode.value === "share" && (canGrantAcl.value || docOwner)) {
      return true;
    }
    return (
      accessMode.value === "publish" &&
      ORG_SCOPES.includes(publishTarget.value) &&
      (canPublishDept.value || canPublishCompany.value || showTeamPublish.value)
    );
  },
  (needs) => {
    if (needs) void ensureCandidates();
  }
);

onMounted(() => {
  ensureUploadLimits();
  load();
  loadParserOptions();
});
</script>

<template>
  <n-card v-if="loading && !doc" :title="t('documents.detail.title')" :loading="true" />
  <n-space v-else-if="doc" vertical :size="16">
    <n-card :loading="loading">
      <template #header>
        <n-space align="center" :size="12" style="flex-wrap: wrap">
          <template v-if="titleEditing && canEditDoc">
            <n-input
              ref="titleInputRef"
              v-model:value="editTitle"
              class="doc-title-input"
              :placeholder="t('documents.detail.docTitlePlaceholder')"
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
              {{ t("common.save") }}
            </n-button>
            <n-button size="small" :disabled="titleSaving" @click="cancelEditTitle">
              {{ t("common.cancel") }}
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
              {{ t("common.edit") }}
            </n-button>
          </template>
        </n-space>
      </template>
      <n-descriptions :column="2" label-placement="left">
        <n-descriptions-item label="ID">{{ doc.id }}</n-descriptions-item>
        <n-descriptions-item :label="t('documents.detail.docStatus')">
          <n-space align="center" :size="8">
            <n-switch
              :value="statusEnabled"
              :disabled="!canManageDoc"
              @update:value="onStatusChange"
            />
            <span>{{
              statusEnabled
                ? t("documents.detail.statusEnabled")
                : t("documents.detail.statusDisabled")
            }}</span>
          </n-space>
        </n-descriptions-item>
        <n-descriptions-item :label="t('documents.columns.scope')">
          <n-tag size="small">{{ scopeLabel(doc.scope) || doc.scope }}</n-tag>
        </n-descriptions-item>
        <n-descriptions-item v-if="supportsKbFolder" :label="t('documents.detail.folder')">
          {{ doc.folder_name || t("documents.uncategorized") }}
        </n-descriptions-item>
        <n-descriptions-item
          v-if="ORG_SCOPES.includes(doc.scope) && (doc.dept_name || doc.dept_id)"
          :label="t('documents.detail.org')"
        >
          {{ doc.dept_name || "—" }}
        </n-descriptions-item>
        <n-descriptions-item :label="t('documents.columns.owner')">{{ ownerLabel }}</n-descriptions-item>
        <n-descriptions-item :label="t('documents.detail.uploadedAt')">{{ uploadedAtLabel }}</n-descriptions-item>
        <n-descriptions-item :label="t('documents.detail.description')" :span="2">{{ doc.description || "—" }}</n-descriptions-item>
        <n-descriptions-item :label="t('documents.detail.createdAt')">
          {{ new Date(doc.created_at).toLocaleString() }}
        </n-descriptions-item>
        <n-descriptions-item :label="t('documents.columns.updatedAt')">
          {{ new Date(doc.updated_at).toLocaleString() }}
        </n-descriptions-item>
      </n-descriptions>
    </n-card>

    <n-card :title="t('documents.detail.versionHistory')">
      <template #header-extra>
        <n-space :size="4" align="center">
          <IconAction
            v-if="canCompareVersions"
            :label="t('documents.detail.compare')"
            :icon="GitCompareOutline"
            @click="openVersionCompare"
          />
          <IconAction
            :label="t('common.refresh')"
            :icon="RefreshOutline"
            :disabled="versionRefreshing || loading"
            @click="refreshVersionHistory"
          />
        </n-space>
      </template>
      <n-table :single-line="false">
        <thead>
          <tr>
            <th>{{ t("documents.detail.version") }}</th>
            <th>{{ t("documents.detail.fileName") }}</th>
            <th>{{ t("documents.detail.versionDesc") }}</th>
            <th>{{ t("documents.detail.size") }}</th>
            <th>{{ t("documents.detail.time") }}</th>
            <th>{{ t("documents.detail.index") }}</th>
            <th v-if="showVersionActions">{{ t("common.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in displayVersions" :key="v.id">
            <td>
              <n-space :size="6" align="center">
                <span>v{{ v.version_no }}</span>
                <n-tag v-if="v.is_current" size="small" type="info">{{ t("documents.detail.current") }}</n-tag>
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
                  :label="t('documents.detail.reindex')"
                  :icon="LayersOutline"
                  :disabled="indexPolling || reparsing"
                  @click="openReindexModal(v)"
                />
                <IconAction
                  v-if="v.uploaded && canViewDoc"
                  variant="table"
                  :label="t('documents.detail.preview')"
                  :icon="EyeOutline"
                  @click="openVersionPreview(v)"
                />
                <IconAction
                  v-if="v.uploaded && canViewDoc"
                  variant="table"
                  :label="t('documents.detail.download')"
                  :icon="DownloadOutline"
                  type="primary"
                  @click="downloadVersion(v)"
                />
                <IconAction
                  v-if="canDeleteDoc"
                  variant="table"
                  :label="t('common.delete')"
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
          :placeholder="t('documents.detail.versionDescPlaceholder')"
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
          {{ t("documents.detail.uploadNewVersion") }}
        </n-button>
      </div>
    </n-card>

    <n-card v-if="showAccessCard" :title="t('documents.detail.publishAndShare')" :loading="aclLoading">
      <div class="access-current-loc">
        <span class="access-current-loc__label">{{ t("documents.detail.currentLocation") }}</span>
        <n-tag type="info" size="small" :bordered="false">{{ currentScopeLabel }}</n-tag>
      </div>

      <n-radio-group v-model:value="accessMode" class="access-mode-group">
        <n-space>
          <n-radio v-if="showPublishCard" value="publish">{{ t("documents.detail.publishToLibrary") }}</n-radio>
          <n-radio v-if="canGrantAcl" value="share">{{ t("documents.detail.shareToIndividuals") }}</n-radio>
        </n-space>
      </n-radio-group>

      <template v-if="accessMode === 'publish' && showPublishCard">
        <p class="access-card-hint">
          {{ t("documents.detail.publishHint") }}
        </p>
        <n-radio-group v-model:value="publishTarget" class="access-publish-target">
          <n-space>
            <n-radio v-if="canPublishCompany" value="company">{{ t("scope.company") }}</n-radio>
            <n-radio v-if="canPublishDept" value="department">{{ t("scope.department") }}</n-radio>
            <n-radio v-if="showTeamPublish" value="team">{{ t("scope.team") }}</n-radio>
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
          {{ doc.scope === "personal" ? t("documents.detail.publish") : t("documents.detail.updatePublishLocation") }}
        </n-button>
      </template>

      <template v-else-if="accessMode === 'share' && canGrantAcl">
        <p class="access-card-hint">
          {{ t("documents.detail.shareHint") }}
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
          {{ t("documents.detail.currentAuthorized") }}
        </p>
        <n-table v-if="shares.length" :single-line="false">
          <thead>
            <tr>
              <th>{{ t("documents.detail.user") }}</th>
              <th>{{ t("documents.columns.permission") }}</th>
              <th>{{ t("common.actions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in shares" :key="s.user_id">
              <td>{{ s.user_name || userNameById[s.user_id] || t("documents.unknownUser") }}</td>
              <td>{{ docLevelLabel(s.level) || s.level }}</td>
              <td>
                <n-button text type="error" size="small" @click="removeShare(s.user_id)">
                  {{ t("documents.detail.revokeShare") }}
                </n-button>
              </td>
            </tr>
          </tbody>
        </n-table>
        <span v-else>{{ t("documents.detail.noPersonalShares") }}</span>
      </template>
    </n-card>

    <n-card v-if="canDenyAcl" :title="t('documents.detail.accessRestrictions')" :loading="aclLoading">
      <p style="margin: 0 0 12px; color: #666; font-size: 13px">
        {{ t("documents.detail.denyHint") }}
      </p>
      <template #header-extra>
        <n-button size="small" @click="openDenyModal">{{ t("documents.detail.denyUserAccess") }}</n-button>
      </template>
      <n-table v-if="denials.length" :single-line="false">
        <thead>
          <tr>
            <th>{{ t("documents.detail.user") }}</th>
            <th>{{ t("documents.detail.reason") }}</th>
            <th>{{ t("common.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in denials" :key="d.id">
            <td>{{ d.user_name || userNameById[d.user_id] || t("documents.unknownUser") }}</td>
            <td>{{ d.reason || "—" }}</td>
            <td>
              <n-button text type="primary" size="small" @click="removeDenial(d.user_id)">
                {{ t("common.restore") }}
              </n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
      <span v-else>{{ t("documents.detail.noDenials") }}</span>
    </n-card>
  </n-space>

  <n-modal v-model:show="showDeny" preset="card" :title="t('documents.detail.denyUserAccess')" style="width: 520px">
    <n-form>
      <n-form-item :label="t('documents.detail.user')">
        <OrgUserPickerTree
          v-if="aclCandidates.length || aclDepartments.length"
          mode="single"
          :departments="aclDepartments"
          :users="aclCandidates"
          v-model:selected-key="denyUserId"
          :max-height="360"
        />
      </n-form-item>
      <n-form-item :label="t('documents.detail.reason')">
        <n-input v-model:value="denyReason" type="textarea" :placeholder="t('common.optional')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showDeny = false">{{ t("common.cancel") }}</n-button>
        <n-button type="warning" @click="submitDeny">{{ t("common.confirm") }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <DocumentVersionPreviewModal
    v-model:show="showVersionPreview"
    :document-id="docId"
    :version="previewVersion"
    pdf-fit-mode="width"
    @download="onPreviewDownload"
  />

  <AdminFormModal
    v-model:show="reindexModalShow"
    :title="t('documents.detail.reindexTitle')"
    :subtitle="t('documents.detail.reindexSubtitle')"
    width="min(480px, 92vw)"
  >
    <n-form label-placement="top" :show-require-mark="false">
      <n-alert
        v-if="pageindexBlockReason"
        type="warning"
        :bordered="false"
        class="reindex-pageindex-hint"
        :title="pageindexBlockReason"
      />
      <n-form-item :label="t('documents.detail.chunkMethod')">
        <n-select
          v-model:value="parserId"
          :options="chunkMethodOptions"
          :render-label="renderIndexedSelectLabel"
          :node-props="reindexSelectNodeProps"
          :menu-props="reindexSelectMenuProps"
          :placement="reindexSelectPlacement"
          to="body"
          consistent-menu-width
          :disabled="indexPolling || reparsing"
        />
      </n-form-item>
      <n-form-item :label="t('documents.detail.layoutOcr')">
        <n-select
          v-model:value="layoutRecognize"
          :options="layoutOptions"
          :render-label="renderIndexedSelectLabel"
          :node-props="reindexSelectNodeProps"
          :menu-props="reindexSelectMenuProps"
          :placement="reindexSelectPlacement"
          to="body"
          consistent-menu-width
          :disabled="indexPolling || reparsing"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="reindexModalShow = false">{{ t("common.cancel") }}</n-button>
        <n-button
          type="primary"
          :loading="reparsing || indexPolling"
          @click="submitReindex"
        >
          {{ t("documents.detail.startIndex") }}
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

.reindex-pageindex-hint {
  margin-bottom: 12px;
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
