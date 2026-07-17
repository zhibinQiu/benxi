<script setup>
import { computed, h, nextTick, onMounted, ref, watch } from "vue";
import {
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NPagination,
  NSpace,
  NSwitch,
  NTag,
  NText,
  NTooltip,
  NUpload,
  NUploadDragger,
} from "naive-ui";
import {
  AddOutline,
  CloudUploadOutline,
  CreateOutline,
  DownloadOutline,
  FolderOpenOutline,
  RefreshOutline,
  SearchOutline,
  SyncOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import IconAction from "../IconAction.vue";
import AdminFormModal from "../AdminFormModal.vue";
import { useClientListPagination } from "../../composables/useClientListPagination.js";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import {
  createGeneratedAgentSkill,
  deleteAgentSkill,
  downloadAgentSkillZip,
  fetchAgentSkill,
  fetchAgentSkillFile,
  fetchAgentSkillRegistry,
  patchBuiltinSkill,
  updateAgentSkill,
  updateAgentSkillFile,
  uploadAgentSkillFolder,
  uploadAgentSkillZip,
} from "../../api/agentSkills.js";
import {
  createMcpSkill,
  deleteMcpSkill,
  fetchMcpServerInfo,
  fetchMcpSkills,
  syncMcpSkill,
} from "../../api/mcpSkills.js";
import { renderIconActionGroup } from "../../utils/tableIconActions.js";
import { isBuiltinSkill } from "../../utils/agentSkillsHelpers.js";
import {
  hasSkillsTabCacheData,
  isSkillsTabCacheFresh,
  readSkillsTabCache,
  writeSkillsTabCache,
} from "../../utils/agentSkillsSkillsTabCache.js";

const emit = defineEmits(["registry-changed"]);

const props = defineProps({
  refreshing: { type: Boolean, default: false },
  onRefresh: { type: Function, default: null },
  onConnectMcp: { type: Function, default: null },
});

const ui = usePlatformUi();
const { t } = useI18n();

const initialCache = readSkillsTabCache({ allowStale: true });
const hydrated = ref(hasSkillsTabCacheData(initialCache));

const registryLoading = ref(false);
const registry = ref(initialCache?.registry || []);
const keyword = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);

function toggleSearch() {
  searchOpen.value = !searchOpen.value;
  if (searchOpen.value) {
    nextTick(() => searchInputRef.value?.focus?.());
  } else {
    keyword.value = "";
  }
}

const mcpSkills = ref(initialCache?.mcpSkills || []);

const mcpSkillsLoading = ref(false);
const mcpServerInfo = ref(initialCache?.mcpServerInfo || null);
const mcpSkillModalOpen = ref(false);
const mcpSkillSaving = ref(false);
const mcpSkillForm = ref({
  name: "",
  title: "",
  description: "",
  endpoint: "",
  transport: "http",
  auth_token: "",
  enabled: true,
  sync_tools: true,
});

const uploading = ref(false);
const replaceExisting = ref(true);
const createOpen = ref(false);
const createSaving = ref(false);
const createForm = ref({ name: "", description: "", skillMdBody: "" });

const builtinDetailOpen = ref(false);
const builtinDetailRow = ref(null);

const detailOpen = ref(false);
const detailLoading = ref(false);
const detail = ref(null);
const previewPath = ref("");
const previewContent = ref("");
const previewLoading = ref(false);
const previewDirty = ref(false);
const previewSaving = ref(false);
const previewEditable = ref(false);

const loading = computed(() => registryLoading.value || mcpSkillsLoading.value);

const allSkills = computed(() => [
  ...(registry.value || []).map((s) => ({ ...s, _isMcp: false })),
  ...(mcpSkills.value || []).map((s) => ({ ...s, _isMcp: true })),
]);

const mergedSkills = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  if (!q) return allSkills.value;
  return allSkills.value.filter((row) => {
    const hay = [row.name, row.title, row.description, row.endpoint].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(q);
  });
});

const {
  page: skillsPage,
  pageSize: skillsPageSize,
  total: skillsTotal,
  pagedItems: skillsPagedItems,
  onPageChange: onSkillsPageChange,
  resetPage: resetSkillsPage,
} = useClientListPagination(mergedSkills);

const displayInfo = computed(() => {
  if (!skillsTotal.value) return "";
  const start = (skillsPage.value - 1) * skillsPageSize + 1;
  const end = Math.min(skillsPage.value * skillsPageSize, skillsTotal.value);
  return `${skillsTotal.value}条数据中的 ${start}-${end} 条`;
});

function kindLabel(row) {
  if (row._isMcp) return t("admin.agentSkills.mcpSkillTag");
  return isBuiltinSkill(row)
    ? t("admin.agentSkills.kindBuiltin")
    : t("admin.agentSkills.kindDeveloped");
}

function readinessTagType(readiness) {
  if (readiness === "ready") return "success";
  if (readiness === "stub") return "warning";
  if (readiness === "disabled") return "default";
  return "error";
}

function readinessLabel(readiness) {
  return t(`admin.agentSkills.readiness.${readiness}`, readiness);
}

function sourceLabel(row) {
  if (row._isMcp) return t("admin.agentSkills.sourceExternal");
  if (row.source_type === "generated") return t("admin.agentSkills.sourceGenerated");
  if (row.source_type === "folder") return t("admin.agentSkills.sourceFolder");
  return t("admin.agentSkills.sourceZip");
}

const sortedDetailFiles = computed(() => {
  const files = detail.value?.files || [];
  return [...files].sort((a, b) => a.localeCompare(b));
});

function persistCache() {
  writeSkillsTabCache({
    registry: registry.value,
    mcpSkills: mcpSkills.value,
    mcpServerInfo: mcpServerInfo.value,
  });
}

async function loadRegistry({ background = false, foreground = false } = {}) {
  const showLoading = foreground || !background;
  if (showLoading) registryLoading.value = true;
  try {
    registry.value =
      (await fetchAgentSkillRegistry({ includeDisabled: true, catalogOnly: true })) || [];
    hydrated.value = true;
    persistCache();
  } catch (e) {
    if (!background || !hydrated.value) {
      ui.error(e.message || t("admin.agentSkills.loadFailed"));
    }
  } finally {
    if (showLoading) registryLoading.value = false;
  }
}

async function loadMcpSkills({ background = false, foreground = false, withServerInfo = false } = {}) {
  const showLoading = foreground || !background;
  if (showLoading) mcpSkillsLoading.value = true;
  try {
    const skills = (await fetchMcpSkills()) || [];
    mcpSkills.value = skills;
    if (withServerInfo) {
      mcpServerInfo.value = (await fetchMcpServerInfo().catch(() => null)) || null;
    }
    hydrated.value = true;
    persistCache();
  } catch (e) {
    if (!background || !hydrated.value) {
      ui.error(e.message || t("admin.agentSkills.loadFailed"));
      mcpSkills.value = [];
    }
  } finally {
    if (showLoading) mcpSkillsLoading.value = false;
  }
}

async function reload({ background = false, foreground = false } = {}) {
  const bg = foreground ? false : background;
  await Promise.all([
    loadRegistry({ background: bg }),
    loadMcpSkills({
      background: bg,
      withServerInfo: Boolean(mcpServerInfo.value?.endpoint || mcpSkills.value.length),
    }),
  ]);
}

async function toggleBuiltin(row, enabled) {
  try {
    await patchBuiltinSkill(row.name, { enabled });
    row.enabled = enabled;
    await loadRegistry();
    ui.success(t("admin.agentSkills.saved"));
    emit("registry-changed");
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  }
}

async function toggleDeveloped(row, enabled) {
  if (!row.skill_id) return;
  try {
    await updateAgentSkill(row.skill_id, { enabled });
    row.enabled = enabled;
    await loadRegistry();
    ui.success(t("admin.agentSkills.saved"));
    emit("registry-changed");
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  }
}

function toggleSkill(row, enabled) {
  if (isBuiltinSkill(row)) return toggleBuiltin(row, enabled);
  return toggleDeveloped(row, enabled);
}

function viewBuiltinDetail(row) {
  builtinDetailRow.value = row;
  builtinDetailOpen.value = true;
}

function removeBuiltinSkill(row) {
  ui.confirmDelete({
    title: t("admin.agentSkills.deleteTitle"),
    content: t("admin.agentSkills.builtinDeleteConfirm", { name: row.title || row.name }),
    onPositive: async () => {
      try {
        await patchBuiltinSkill(row.name, { enabled: false });
        row.enabled = false;
        await loadRegistry();
        ui.success(t("admin.agentSkills.builtinDisabled"));
        emit("registry-changed");
      } catch (e) {
        ui.error(e.message || t("admin.agentSkills.saveFailed"));
      }
    },
  });
}

function formatDateCompact(dt) {
  if (!dt) return "—";
  const d = new Date(dt);
  if (Number.isNaN(d.getTime())) return "—";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}${m}${day}`;
}

const skillColumns = computed(() => [
  {
    title: t("admin.agentSkills.colName"),
    key: "name",
    minWidth: 220,
    ellipsis: { tooltip: true },
    render: (row) => {
      const infoLines = [];
      if (!row._isMcp && row.readiness) {
        infoLines.push(`${t("admin.agentSkills.colReadiness")}: ${readinessLabel(row.readiness)}`);
      }
      if (!row._isMcp && row.created_at) {
        infoLines.push(`${t("admin.agentSkills.colCreatedAt")}: ${formatDateCompact(row.created_at)}`);
      }
      const cell = h("div", { style: "display:flex;flex-direction:column;gap:2px;padding:2px 0;" }, [
        h("div", { style: "font-size:var(--platform-font-size-sm);font-weight:500;color:var(--platform-text);line-height:1.4;" }, row.title || row.name),
        h("div", { style: "font-size:var(--platform-font-size-sm);color:var(--platform-text-tertiary);line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, row.description || ""),
      ]);
      if (!infoLines.length) return cell;
      return h(
        NTooltip,
        { placement: "top" },
        {
          trigger: () => cell,
          default: () =>
            h("div", { style: "white-space: nowrap;" }, infoLines.join(" | ")),
        }
      );
    },
  },
  {
    title: t("admin.agentSkills.colKind"),
    key: "kind",
    width: 96,
    render: (row) =>
      h(
        NTag,
        {
          size: "small",
          type: row._isMcp ? "info" : isBuiltinSkill(row) ? "info" : "default",
          bordered: false,
        },
        { default: () => kindLabel(row) }
      ),
  },
  {
    title: t("admin.agentSkills.colEnabled"),
    key: "enabled",
    width: 80,
    render: (row) =>
      h(NSwitch, {
        size: "small",
        value: row.enabled,
        onUpdateValue: (v) => toggleSkill(row, v),
      }),
  },
  {
    title: t("admin.agentSkills.colSource"),
    key: "source_type",
    width: 108,
    render: (row) =>
      h(NTag, { size: "small", bordered: false }, { default: () => sourceLabel(row) }),
  },
  {
    title: t("common.actions"),
    key: "actions",
    width: 120,
    render: (row) => {
      if (row._isMcp) {
        return renderIconActionGroup([
          {
            label: t("admin.agentSkills.mcpSkillSync"),
            icon: SyncOutline,
            type: "primary",
            disabled: row.source === "config",
            onClick: () => handleSyncMcpSkill(row),
          },
          {
            label: t("common.delete"),
            icon: TrashOutline,
            type: "error",
            disabled: row.source === "config",
            onClick: () => removeMcpSkill(row),
          },
        ]);
      }
      if (isBuiltinSkill(row)) {
        return renderIconActionGroup([
          {
            label: t("common.edit"),
            icon: CreateOutline,
            type: "primary",
            onClick: () => viewBuiltinDetail(row),
          },
          {
            label: t("common.delete"),
            icon: TrashOutline,
            type: "error",
            onClick: () => removeBuiltinSkill(row),
          },
        ]);
      }
      return renderIconActionGroup([
        {
          label: t("common.edit"),
          icon: CreateOutline,
          type: "primary",
          onClick: () => openDetail(row),
        },
        {
          label: t("common.delete"),
          icon: TrashOutline,
          type: "error",
          onClick: () => removeSkill(row),
        },
      ]);
    },
  },
]);

async function openDetail(row) {
  if (!row.skill_id) return;
  detailOpen.value = true;
  detailLoading.value = true;
  previewPath.value = "";
  previewContent.value = "";
  try {
    detail.value = await fetchAgentSkill(row.skill_id);
    if (detail.value?.files?.includes("SKILL.md")) {
      await loadPreview("SKILL.md");
    }
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    detailLoading.value = false;
  }
}

async function loadPreview(path) {
  if (!detail.value?.id) return;
  previewLoading.value = true;
  previewPath.value = path;
  previewDirty.value = false;
  try {
    const file = await fetchAgentSkillFile(detail.value.id, path);
    previewContent.value = file?.text || (file?.base64 ? `[binary: ${path}]` : "");
    previewEditable.value = Boolean(file?.text != null && file?.text !== undefined);
  } catch (e) {
    previewContent.value = e.message || "";
    previewEditable.value = false;
  } finally {
    previewLoading.value = false;
  }
}

async function savePreview() {
  if (!detail.value?.id || !previewPath.value || !previewEditable.value) return;
  previewSaving.value = true;
  try {
    await updateAgentSkillFile(detail.value.id, previewPath.value, previewContent.value);
    previewDirty.value = false;
    ui.success(t("admin.agentSkills.saved"));
    await reload();
    emit("registry-changed");
    detail.value = await fetchAgentSkill(detail.value.id);
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    previewSaving.value = false;
  }
}

async function downloadSkill() {
  if (!detail.value?.id) return;
  try {
    await downloadAgentSkillZip(detail.value.id, `${detail.value.name}.zip`);
    ui.success(t("admin.agentSkills.downloadOk"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.downloadFailed"));
  }
}

function removeSkillById(skillId, name = "") {
  if (!skillId) return;
  ui.confirmDelete({
    title: t("admin.agentSkills.deleteTitle"),
    content: t("admin.agentSkills.deleteConfirm", { name: name || "—" }),
    onPositive: async () => {
      try {
        await deleteAgentSkill(skillId);
        ui.success(t("admin.agentSkills.deleted"));
        if (detail.value?.id === skillId) detailOpen.value = false;
        await reload();
        emit("registry-changed");
      } catch (e) {
        ui.error(e.message || t("admin.agentSkills.deleteFailed"));
      }
    },
  });
}

function removeSkill(row) {
  removeSkillById(row.skill_id, row.name);
}

async function submitCreateSkill() {
  createSaving.value = true;
  try {
    await createGeneratedAgentSkill({
      name: createForm.value.name.trim(),
      description: createForm.value.description.trim(),
      skillMdBody: createForm.value.skillMdBody,
      replaceExisting: replaceExisting.value,
    });
    createOpen.value = false;
    createForm.value = { name: "", description: "", skillMdBody: "" };
    ui.success(t("admin.agentSkills.createOk"));
    await reload();
    emit("registry-changed");
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.createFailed"));
  } finally {
    createSaving.value = false;
  }
}

async function handleZipUpload({ file }) {
  uploading.value = true;
  try {
    const result = await uploadAgentSkillZip(file.file, { replaceExisting: replaceExisting.value });
    const names = (result?.skills || []).map((s) => s.name).join(", ");
    ui.success(t("admin.agentSkills.uploadOk", { names: names || "—" }));
    createOpen.value = false;
    await reload();
    emit("registry-changed");
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.uploadFailed"));
  } finally {
    uploading.value = false;
  }
  return false;
}

async function onFolderChange(event) {
  const list = Array.from(event.target.files || []);
  if (!list.length) return;
  uploading.value = true;
  try {
    const result = await uploadAgentSkillFolder(list, { replaceExisting: replaceExisting.value });
    const names = (result?.skills || []).map((s) => s.name).join(", ");
    ui.success(t("admin.agentSkills.uploadOk", { names: names || "—" }));
    createOpen.value = false;
    await reload();
    emit("registry-changed");
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.uploadFailed"));
  } finally {
    uploading.value = false;
    event.target.value = "";
  }
}

function openMcpSkillModal() {
  mcpSkillForm.value = {
    name: "",
    title: "",
    description: "",
    endpoint: "",
    transport: "http",
    auth_token: "",
    enabled: true,
    sync_tools: true,
  };
  if (!mcpServerInfo.value?.endpoint) {
    void fetchMcpServerInfo()
      .then((info) => {
        mcpServerInfo.value = info || null;
        persistCache();
      })
      .catch(() => {});
  }
  mcpSkillModalOpen.value = true;
}

async function submitMcpSkill() {
  const form = mcpSkillForm.value;
  if (!form.name?.trim() || !form.endpoint?.trim()) {
    ui.warning(t("admin.agentSkills.mcpSkillFormRequired"));
    return;
  }
  mcpSkillSaving.value = true;
  try {
    await createMcpSkill(form);
    ui.success(t("admin.agentSkills.saved"));
    mcpSkillModalOpen.value = false;
    await reload();
    emit("registry-changed");
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    mcpSkillSaving.value = false;
  }
}

async function handleSyncMcpSkill(skill) {
  if (!skill?.id || skill.source === "config") {
    ui.info(t("admin.agentSkills.mcpSkillConfigReadonly"));
    return;
  }
  try {
    await syncMcpSkill(skill.id);
    ui.success(t("admin.agentSkills.mcpSkillSyncOk"));
    await reload();
    emit("registry-changed");
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  }
}

function removeMcpSkill(skill) {
  if (!skill?.id || skill.source === "config") {
    ui.info(t("admin.agentSkills.mcpSkillConfigReadonly"));
    return;
  }
  ui.confirmDelete({
    title: t("admin.agentSkills.mcpSkillDeleteTitle"),
    content: t("admin.agentSkills.mcpSkillDeleteConfirm", { name: skill.name }),
    onPositive: async () => {
      try {
        await deleteMcpSkill(skill.id);
        ui.success(t("admin.agentSkills.deleted"));
        await reload();
        emit("registry-changed");
      } catch (e) {
        ui.error(e.message || t("admin.agentSkills.deleteFailed"));
      }
    },
  });
}

watch(keyword, () => {
  resetSkillsPage();
});

onMounted(async () => {
  if (hydrated.value) {
    void reload({ background: !isSkillsTabCacheFresh() });
  } else {
    await reload();
  }
});

defineExpose({ reload, toggleSearch, loadRegistry, loadMcpSkills, loading, openMcpSkillModal });
</script>

<template>
    <div class="skills-card__header">
      <div class="skills-card__title-row">
        <div class="skills-card__title">{{ t('admin.agentSkills.tabSkills') }}</div>
        <div class="skills-card__actions">
          <IconAction
            :label="t('common.search')"
            :icon="SearchOutline"
            :active="searchOpen"
            @click="toggleSearch"
          />
          <IconAction
            v-if="onConnectMcp"
            :label="t('admin.agentSkills.connectMcpSkill')"
            :icon="DownloadOutline"
            @click="onConnectMcp"
          />
          <IconAction
            :label="t('admin.agentSkills.developedTitle')"
            :icon="AddOutline"
            @click="createOpen = true"
          />
          <IconAction
            v-if="onRefresh"
            :label="t('common.refresh')"
            :icon="RefreshOutline"
            :loading="refreshing"
            @click="onRefresh"
          />
          <NInput
            v-show="searchOpen"
            ref="searchInputRef"
            v-model:value="keyword"
            clearable
            :placeholder="t('admin.agentSkills.searchPlaceholder')"
            style="width: 240px"
          />
        </div>
      </div>
      <div class="skills-card__hint">{{ t('admin.agentSkills.toolbarHint.skills') }}</div>
    </div>
    <div class="skills-card">
      <div class="admin-list-table">
        <NDataTable
          :loading="loading && !hydrated"
          :columns="skillColumns"
          :data="skillsPagedItems"
          :pagination="false"
        />
      </div>
      <div class="skills-table-footer">
        <span class="skills-table-footer__info">{{ displayInfo }}</span>
        <div class="skills-table-footer__pages">
          <NPagination
            :page="skillsPage"
            :page-size="skillsPageSize"
            :item-count="skillsTotal"
            :page-slot="7"
            @update:page="onSkillsPageChange"
          />
        </div>
      </div>
    </div>

  <AdminFormModal
    v-model:show="createOpen"
    :title="t('admin.agentSkills.developedTitle')"
    :width="768"
  >
    <NSpace vertical :size="19">
      <NText depth="3">{{ t("admin.agentSkills.developedHint") }}</NText>
      <NSpace align="center">
        <NText depth="3">{{ t("admin.agentSkills.replaceExisting") }}</NText>
        <NSwitch v-model:value="replaceExisting" />
      </NSpace>
      <NSpace :size="19" wrap>
        <NUpload
          :show-file-list="false"
          accept=".zip,application/zip"
          :disabled="uploading"
          @before-upload="handleZipUpload"
        >
          <NUploadDragger style="width: 336px">
            <NSpace vertical align="center" :size="10">
              <NIcon :size="43" :depth="3"><CloudUploadOutline /></NIcon>
              <NText>{{ t("admin.agentSkills.uploadZip") }}</NText>
            </NSpace>
          </NUploadDragger>
        </NUpload>
        <label class="folder-upload">
          <input
            type="file"
            webkitdirectory
            directory
            multiple
            :disabled="uploading"
            @change="onFolderChange"
          />
          <NSpace vertical align="center" :size="10" class="folder-upload-inner">
            <NIcon :size="43" :depth="3"><FolderOpenOutline /></NIcon>
            <NText>{{ t("admin.agentSkills.uploadFolder") }}</NText>
          </NSpace>
        </label>
      </NSpace>
      <NText depth="3">{{ t("admin.agentSkills.createSkill") }}</NText>
      <NInput v-model:value="createForm.name" :placeholder="t('admin.agentSkills.createNamePh')" />
      <NInput
        v-model:value="createForm.description"
        :placeholder="t('admin.agentSkills.createDescPh')"
      />
      <NInput
        v-model:value="createForm.skillMdBody"
        type="textarea"
        :rows="10"
        :placeholder="t('admin.agentSkills.createBodyPh')"
      />
    </NSpace>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="createOpen = false">{{ t("common.cancel") }}</NButton>
        <NButton type="primary" :loading="createSaving" @click="submitCreateSkill">
          {{ t("admin.agentSkills.createSkill") }}
        </NButton>
      </NSpace>
    </template>
  </AdminFormModal>

  <NDrawer v-if="detailOpen" v-model:show="detailOpen" :width="864" placement="right">
    <NDrawerContent :title="detail?.name || t('admin.agentSkills.detailTitle')" closable>
      <div v-if="detailLoading">{{ t("common.loading") }}</div>
      <template v-else-if="detail">
        <NText depth="3">{{ detail.description }}</NText>
        <NSpace style="margin: 14px 0" :size="10">
          <NButton size="small" @click="downloadSkill">
            {{ t("admin.agentSkills.downloadZip") }}
          </NButton>
          <IconAction
            variant="table"
            type="error"
            :label="t('common.delete')"
            :icon="TrashOutline"
            @click="removeSkillById(detail.id, detail.name)"
          />
        </NSpace>
        <NSpace style="margin: 0 0 14px" :size="10" wrap>
          <NTag
            v-for="f in sortedDetailFiles"
            :key="f"
            size="small"
            :bordered="false"
            checkable
            :checked="previewPath === f"
            @click="loadPreview(f)"
          >
            {{ f }}
          </NTag>
        </NSpace>
        <NCard v-if="previewPath" size="small" :title="previewPath">
          <div v-if="previewLoading">{{ t("common.loading") }}</div>
          <template v-else>
            <NInput
              v-if="previewEditable"
              v-model:value="previewContent"
              type="textarea"
              :rows="18"
              @update:value="previewDirty = true"
            />
            <pre v-else class="skill-preview">{{ previewContent }}</pre>
            <NSpace v-if="previewEditable" style="margin-top: 10px">
              <NButton
                type="primary"
                size="small"
                :loading="previewSaving"
                :disabled="!previewDirty"
                @click="savePreview"
              >
                {{ t("common.save") }}
              </NButton>
            </NSpace>
          </template>
        </NCard>
      </template>
    </NDrawerContent>
  </NDrawer>

  <AdminFormModal
    v-model:show="mcpSkillModalOpen"
    :title="t('admin.agentSkills.connectMcpSkill')"
    :width="768"
  >
    <NText depth="3" class="mcp-skill-modal__hint">
      {{ t("admin.agentSkills.mcpSkillModalHint") }}
    </NText>
    <NForm @submit.prevent="submitMcpSkill">
      <NFormItem :label="t('admin.agentSkills.mcpSkillName')" required>
        <NInput v-model:value="mcpSkillForm.name" :placeholder="t('admin.agentSkills.mcpSkillNamePh')" />
      </NFormItem>
      <NFormItem :label="t('admin.agentSkills.mcpSkillTitle')">
        <NInput v-model:value="mcpSkillForm.title" :placeholder="t('admin.agentSkills.mcpSkillTitlePh')" />
      </NFormItem>
      <NFormItem :label="t('admin.agentSkills.mcpSkillEndpoint')" required>
        <NInput
          v-model:value="mcpSkillForm.endpoint"
          :placeholder="t('admin.agentSkills.mcpSkillEndpointPh')"
        />
      </NFormItem>
      <NFormItem :label="t('admin.agentSkills.mcpSkillTransport')">
        <NInput v-model:value="mcpSkillForm.transport" placeholder="http" />
      </NFormItem>
      <NFormItem :label="t('admin.agentSkills.mcpSkillAuthToken')">
        <NInput v-model:value="mcpSkillForm.auth_token" type="password" show-password-on="click" />
      </NFormItem>
      <NFormItem :label="t('admin.agentSkills.colDescription')">
        <NInput
          v-model:value="mcpSkillForm.description"
          type="textarea"
          :rows="3"
          :placeholder="t('admin.agentSkills.mcpSkillDescPh')"
        />
      </NFormItem>
      <NFormItem :label="t('admin.agentSkills.serviceEnabled')">
        <NSwitch v-model:value="mcpSkillForm.enabled" />
      </NFormItem>
    </NForm>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="mcpSkillModalOpen = false">{{ t("common.cancel") }}</NButton>
        <NButton type="primary" :loading="mcpSkillSaving" @click="submitMcpSkill">
          {{ t("common.save") }}
        </NButton>
      </NSpace>
    </template>
  </AdminFormModal>

  <AdminFormModal
    v-model:show="builtinDetailOpen"
    :title="t('admin.agentSkills.builtinDetailTitle')"
    :width="640"
  >
    <NSpace v-if="builtinDetailRow" vertical :size="14">
      <NForm label-placement="left" label-width="100" :show-feedback="false">
        <NFormItem :label="t('admin.agentSkills.colName')">
          <NText depth="2">{{ builtinDetailRow.name }}</NText>
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.colTitle')">
          <NText depth="2">{{ builtinDetailRow.title || builtinDetailRow.name }}</NText>
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.colDescription')">
          <NText depth="2">{{ builtinDetailRow.description || '—' }}</NText>
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.colReadiness')">
          <NTag :type="readinessTagType(builtinDetailRow.readiness)" size="small" bordered>
            {{ readinessLabel(builtinDetailRow.readiness) }}
          </NTag>
        </NFormItem>
        <NFormItem v-if="builtinDetailRow.route" :label="t('admin.agentSkills.builtinDetailRoute')">
          <NText depth="2">{{ builtinDetailRow.route }}</NText>
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.builtinDetailUseWhen')">
          <NText depth="2" style="white-space:pre-wrap">{{ builtinDetailRow.use_when || '—' }}</NText>
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.builtinDetailDontUseWhen')">
          <NText depth="2" style="white-space:pre-wrap">{{ builtinDetailRow.dont_use_when || '—' }}</NText>
        </NFormItem>
        <NFormItem v-if="builtinDetailRow.orchestrated_tools?.length" :label="t('admin.agentSkills.builtinDetailTools')">
          <NSpace :size="6" wrap>
            <NTag v-for="tool in builtinDetailRow.orchestrated_tools" :key="tool" size="small" bordered>
              {{ tool }}
            </NTag>
          </NSpace>
        </NFormItem>
      </NForm>
    </NSpace>
  </AdminFormModal>
</template>

<style scoped>
.mcp-skill-modal__hint {
  display: block;
  margin-bottom: 19px;
}

.skills-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.skills-card__header {
  margin: 0 0 8px;
  padding-left: 16px;
}

.skills-card__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.skills-card__title {
  font-size: var(--platform-font-size-sm);
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.4;
  flex-shrink: 0;
}

.skills-card__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.skills-card__hint {
  margin-top: 2px;
  font-size: var(--platform-font-size-sm);
  font-weight: 400;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}

.skills-card :deep(.n-data-table-th),
.skills-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.skills-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.skills-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}


/* Switch 自定义：Naive UI 把变量设为内联样式，必须用 !important 覆盖 */
.skills-card :deep(.n-switch) {
  --n-rail-width: 28px !important;
  --n-rail-height: 16px !important;
  --n-button-width: 12px !important;
  --n-button-height: 12px !important;
  --n-button-width-pressed: 12px !important;
  --n-height: 16px !important;
  --n-width: 28px !important;
  --n-offset: 2px !important;
  --n-rail-color: var(--platform-border-strong) !important;
  --n-rail-color-active: var(--platform-accent) !important;
}

.skills-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-top: 1px solid var(--platform-border-strong);
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
}

.skills-table-footer__pages :deep(.n-pagination) {
  justify-content: flex-end;
}

.skills-table-footer__pages :deep(.n-pagination-item) {
  font-size: var(--platform-font-size-sm);
}
</style>
