<script setup>
import { computed, h, onActivated, onMounted, ref } from "vue";
import {
  NButton,
  NCard,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NIcon,
  NInput,
  NModal,
  NSpace,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NText,
  NUpload,
  NUploadDragger,
} from "naive-ui";
import { FolderOpenOutline, CloudUploadOutline, RefreshOutline } from "@vicons/ionicons5";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import {
  createGeneratedAgentSkill,
  deleteAgentSkill,
  downloadAgentSkillZip,
  fetchAgentMemory,
  fetchAgentSkill,
  fetchAgentSkillFile,
  fetchAgentSkillRegistry,
  fetchAgentSkills,
  fetchAgentTools,
  invokeAgentSkill,
  patchBuiltinSkill,
  updateAgentMemory,
  updateAgentSkill,
  updateAgentSkillFile,
  clearAgentMemory,
  uploadAgentSkillFolder,
  uploadAgentSkillZip,
} from "../../api/agentSkills.js";
import { LIST_PAGE_SIZE } from "../../constants/listPage.js";

const ui = usePlatformUi();
const { t } = useI18n();

const activeTab = ref("tools");
const registryLoading = ref(false);
const registry = ref([]);
const toolsLoading = ref(false);
const tools = ref([]);

const loading = ref(false);
const uploading = ref(false);
const skills = ref([]);
const total = ref(0);
const page = ref(1);
const keyword = ref("");
const replaceExisting = ref(true);

const detailOpen = ref(false);
const detailLoading = ref(false);
const detail = ref(null);
const previewPath = ref("");
const previewContent = ref("");
const previewLoading = ref(false);
const previewDirty = ref(false);
const previewSaving = ref(false);
const previewEditable = ref(false);

const memoryContent = ref("");
const memoryLoading = ref(false);
const memorySaving = ref(false);

const createOpen = ref(false);
const createSaving = ref(false);
const createForm = ref({ name: "", description: "", skillMdBody: "" });

const builtinSkills = computed(() =>
  registry.value.filter((s) => s.kind === "builtin" || s.source === "builtin")
);
const developedInRegistry = computed(() =>
  registry.value.filter((s) => s.kind === "developed" || s.source === "uploaded")
);

const ATOMIC_INVOKE_MAP = {
  web_search: { skillName: "web-search", toolName: "search", params: { query: "测试", max_items: 2 } },
  knowledge_retrieve: { skillName: "knowledge-search", toolName: "retrieve", params: { query: "测试" } },
  kg_query: { skillName: "kg-palantir", toolName: "query_entities", params: { question: "测试" } },
};

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / (1024 * 1024)).toFixed(1)} MB`;
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

function toolCategoryLabel(category) {
  return t(`admin.agentSkills.toolCategory.${category}`, category);
}

async function loadTools() {
  toolsLoading.value = true;
  try {
    tools.value = (await fetchAgentTools()) || [];
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    toolsLoading.value = false;
  }
}

async function loadRegistry() {
  registryLoading.value = true;
  try {
    registry.value = (await fetchAgentSkillRegistry({ includeDisabled: true })) || [];
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    registryLoading.value = false;
  }
}

async function handlePageChange(p) {
  page.value = p;
  await loadUploadedList();
}

async function loadUploadedList() {
  loading.value = true;
  try {
    const data = await fetchAgentSkills({
      page: page.value,
      pageSize: LIST_PAGE_SIZE,
      q: keyword.value.trim(),
    });
    skills.value = data?.items || [];
    total.value = data?.total || 0;
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function reloadAll() {
  await Promise.all([loadTools(), loadRegistry(), loadUploadedList()]);
}

async function toggleBuiltin(row, enabled) {
  try {
    await patchBuiltinSkill(row.name, { enabled });
    row.enabled = enabled;
    ui.success(t("admin.agentSkills.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  }
}

async function testBuiltin(row) {
  const atomic = row.orchestrated_tools?.[0];
  const route = ATOMIC_INVOKE_MAP[atomic];
  if (!route) {
    ui.info(t("admin.agentSkills.orchestrationOnly"));
    return;
  }
  try {
    const result = await invokeAgentSkill({
      skillName: route.skillName,
      toolName: route.toolName,
      params: route.params,
    });
    ui.info(result?.summary || t("admin.agentSkills.invokeOk"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.invokeFailed"));
  }
}

const toolColumns = computed(() => [
  { title: t("admin.agentSkills.colName"), key: "name", width: 200 },
  {
    title: t("admin.agentSkills.colCategory"),
    key: "category",
    width: 110,
    render: (row) => toolCategoryLabel(row.category),
  },
  {
    title: t("admin.agentSkills.colDescription"),
    key: "description",
    ellipsis: { tooltip: true },
  },
  {
    title: t("admin.agentSkills.colAvailable"),
    key: "available",
    width: 100,
    render: (row) =>
      h(
        NTag,
        {
          size: "small",
          type: row.available ? "success" : "default",
          bordered: false,
        },
        { default: () => (row.available ? t("admin.agentSkills.availableYes") : t("admin.agentSkills.availableNo")) }
      ),
  },
]);

const builtinColumns = computed(() => [
  { title: t("admin.agentSkills.colName"), key: "name", width: 160 },
  { title: t("admin.agentSkills.colTitle"), key: "title", width: 120 },
  {
    title: t("admin.agentSkills.colDescription"),
    key: "description",
    ellipsis: { tooltip: true },
  },
  {
    title: t("admin.agentSkills.colReadiness"),
    key: "readiness",
    width: 100,
    render: (row) =>
      h(
        NTag,
        { size: "small", type: readinessTagType(row.readiness), bordered: false },
        { default: () => readinessLabel(row.readiness) }
      ),
  },
  {
    title: t("admin.agentSkills.colOrchestration"),
    key: "orchestrated_tools",
    width: 220,
    render: (row) => (row.orchestrated_tools || []).join(", ") || "—",
  },
  {
    title: t("admin.agentSkills.colEnabled"),
    key: "enabled",
    width: 90,
    render: (row) =>
      h(NSwitch, {
        value: row.enabled,
        onUpdateValue: (v) => toggleBuiltin(row, v),
      }),
  },
  {
    title: t("common.actions"),
    key: "actions",
    width: 100,
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          quaternary: true,
          disabled: !row.enabled || !ATOMIC_INVOKE_MAP[row.orchestrated_tools?.[0]],
          onClick: () => testBuiltin(row),
        },
        { default: () => t("admin.agentSkills.testInvoke") }
      ),
  },
]);

async function openDetail(row) {
  detailOpen.value = true;
  detailLoading.value = true;
  previewPath.value = "";
  previewContent.value = "";
  try {
    detail.value = await fetchAgentSkill(row.id);
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
    await reloadAll();
    detail.value = await fetchAgentSkill(detail.value.id);
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    previewSaving.value = false;
  }
}

function sourceLabel(row) {
  if (row.source_type === "generated") return t("admin.agentSkills.sourceGenerated");
  if (row.source_type === "folder") return t("admin.agentSkills.sourceFolder");
  return t("admin.agentSkills.sourceZip");
}

const sortedDetailFiles = computed(() => {
  const files = detail.value?.files || [];
  return [...files].sort((a, b) => a.localeCompare(b));
});

async function loadMemory() {
  memoryLoading.value = true;
  try {
    const data = await fetchAgentMemory();
    memoryContent.value = data?.content || "";
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    memoryLoading.value = false;
  }
}

async function saveMemory() {
  memorySaving.value = true;
  try {
    const data = await updateAgentMemory(memoryContent.value);
    memoryContent.value = data?.content || "";
    ui.success(t("admin.agentSkills.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    memorySaving.value = false;
  }
}

function wipeMemory() {
  ui.confirmDelete({
    title: t("admin.agentSkills.memoryClearTitle"),
    content: t("admin.agentSkills.memoryClearConfirm"),
    onPositive: async () => {
      try {
        await clearAgentMemory();
        memoryContent.value = "";
        ui.success(t("admin.agentSkills.memoryCleared"));
      } catch (e) {
        ui.error(e.message || t("admin.agentSkills.saveFailed"));
      }
    },
  });
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
    await reloadAll();
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.createFailed"));
  } finally {
    createSaving.value = false;
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

async function toggleUploaded(row, enabled) {
  try {
    await updateAgentSkill(row.id, { enabled });
    row.enabled = enabled;
    await loadRegistry();
    ui.success(t("admin.agentSkills.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
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
        await reloadAll();
      } catch (e) {
        ui.error(e.message || t("admin.agentSkills.deleteFailed"));
      }
    },
  });
}

function removeSkill(row) {
  removeSkillById(row.id, row.name);
}

async function handleZipUpload({ file }) {
  uploading.value = true;
  try {
    const result = await uploadAgentSkillZip(file.file, { replaceExisting: replaceExisting.value });
    const names = (result?.skills || []).map((s) => s.name).join(", ");
    ui.success(t("admin.agentSkills.uploadOk", { names: names || "—" }));
    await reloadAll();
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
    await reloadAll();
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.uploadFailed"));
  } finally {
    uploading.value = false;
    event.target.value = "";
  }
}

const uploadedColumns = computed(() => [
  {
    title: t("admin.agentSkills.colName"),
    key: "name",
    render: (row) =>
      h(
        NButton,
        { text: true, type: "primary", onClick: () => openDetail(row) },
        { default: () => row.name }
      ),
  },
  {
    title: t("admin.agentSkills.colDescription"),
    key: "description",
    ellipsis: { tooltip: true },
  },
  {
    title: t("admin.agentSkills.colFiles"),
    key: "file_count",
    width: 90,
    render: (row) => String(row.file_count ?? 0),
  },
  {
    title: t("admin.agentSkills.colSize"),
    key: "total_bytes",
    width: 100,
    render: (row) => formatBytes(row.total_bytes),
  },
  {
    title: t("admin.agentSkills.colEnabled"),
    key: "enabled",
    width: 100,
    render: (row) =>
      h(NSwitch, {
        value: row.enabled,
        onUpdateValue: (v) => toggleUploaded(row, v),
      }),
  },
  {
    title: t("admin.agentSkills.colSource"),
    key: "source_type",
    width: 90,
    render: (row) =>
      h(
        NTag,
        { size: "small", bordered: false },
        {
          default: () => sourceLabel(row),
        }
      ),
  },
  {
    title: t("common.actions"),
    key: "actions",
    width: 100,
    render: (row) =>
      h(
        NButton,
        { size: "small", quaternary: true, type: "error", onClick: () => removeSkill(row) },
        { default: () => t("common.delete") }
      ),
  },
]);

onMounted(async () => {
  await reloadAll();
  await loadMemory();
});

onActivated(async () => {
  await reloadAll();
});
</script>

<template>
  <div class="agent-skills-view">
    <NTabs v-model:value="activeTab" type="line" animated>
      <NTabPane name="tools" :tab="t('admin.agentSkills.tabTools')">
        <NCard size="small" :title="t('admin.agentSkills.toolsTitle')">
          <template #header-extra>
            <NButton
              quaternary
              size="small"
              :loading="toolsLoading"
              @click="loadTools"
            >
              <template #icon>
                <NIcon :component="RefreshOutline" />
              </template>
              {{ t("common.refresh") }}
            </NButton>
          </template>
          <NText depth="3" style="display: block; margin-bottom: 12px">
            {{ t("admin.agentSkills.toolsHint") }}
          </NText>
          <NDataTable
            :loading="toolsLoading"
            :columns="toolColumns"
            :data="tools"
            :pagination="{ pageSize: LIST_PAGE_SIZE }"
          />
        </NCard>
      </NTabPane>

      <NTabPane name="skills" :tab="t('admin.agentSkills.tabSkills')">
        <NCard size="small" :title="t('admin.agentSkills.builtinTitle')" style="margin-bottom: 16px">
          <template #header-extra>
            <NButton
              quaternary
              size="small"
              :loading="registryLoading"
              @click="loadRegistry"
            >
              <template #icon>
                <NIcon :component="RefreshOutline" />
              </template>
              {{ t("common.refresh") }}
            </NButton>
          </template>
          <NText depth="3" style="display: block; margin-bottom: 12px">
            {{ t("admin.agentSkills.builtinHint") }}
          </NText>
          <NDataTable
            :loading="registryLoading"
            :columns="builtinColumns"
            :data="builtinSkills"
            :pagination="{ pageSize: LIST_PAGE_SIZE }"
          />
        </NCard>

        <NCard :title="t('admin.agentSkills.developedTitle')" size="small" style="margin-bottom: 16px">
          <NSpace vertical :size="12">
            <NText depth="3">{{ t("admin.agentSkills.developedHint") }}</NText>
            <NSpace align="center">
              <NButton size="small" @click="createOpen = true">
                {{ t("admin.agentSkills.createSkill") }}
              </NButton>
            </NSpace>
            <NSpace align="center">
              <NText depth="3">{{ t("admin.agentSkills.replaceExisting") }}</NText>
              <NSwitch v-model:value="replaceExisting" />
            </NSpace>
            <NSpace :size="16" wrap>
              <NUpload
                :show-file-list="false"
                accept=".zip,application/zip"
                :disabled="uploading"
                @before-upload="handleZipUpload"
              >
                <NUploadDragger style="width: 280px">
                  <NSpace vertical align="center" :size="8">
                    <NIcon :size="36" :depth="3"><CloudUploadOutline /></NIcon>
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
                <NSpace vertical align="center" :size="8" class="folder-upload-inner">
                  <NIcon :size="36" :depth="3"><FolderOpenOutline /></NIcon>
                  <NText>{{ t("admin.agentSkills.uploadFolder") }}</NText>
                </NSpace>
              </label>
            </NSpace>
          </NSpace>
        </NCard>

        <NCard size="small">
          <template #header>
            <NSpace justify="space-between" align="center" style="width: 100%">
              <span>{{ t("admin.agentSkills.listTitle") }}</span>
              <NSpace align="center" :size="8">
                <NButton quaternary size="small" :loading="loading" @click="loadUploadedList">
                  <template #icon>
                    <NIcon :component="RefreshOutline" />
                  </template>
                  {{ t("common.refresh") }}
                </NButton>
                <NInput
                  v-model:value="keyword"
                  clearable
                  :placeholder="t('admin.agentSkills.searchPlaceholder')"
                  style="width: 240px"
                  @keyup.enter="loadUploadedList"
                  @clear="loadUploadedList"
                />
              </NSpace>
            </NSpace>
          </template>
          <NDataTable
            remote
            :loading="loading"
            :columns="uploadedColumns"
            :data="skills"
            :pagination="{
              page: page,
              pageSize: LIST_PAGE_SIZE,
              itemCount: total,
              onUpdatePage: handlePageChange,
            }"
          />
        </NCard>

        <NCard
          v-if="developedInRegistry.length"
          size="small"
          style="margin-top: 16px"
          :title="t('admin.agentSkills.developedInCatalog')"
        >
          <template #header-extra>
            <NButton quaternary size="small" :loading="registryLoading" @click="loadRegistry">
              <template #icon>
                <NIcon :component="RefreshOutline" />
              </template>
              {{ t("common.refresh") }}
            </NButton>
          </template>
          <NSpace :size="8" wrap align="center">
            <NSpace
              v-for="s in developedInRegistry"
              :key="s.name"
              :size="4"
              align="center"
              inline
            >
              <NTag
                size="small"
                :bordered="false"
                :type="s.source_type === 'generated' ? 'info' : 'default'"
              >
                {{ s.name }}
                <template v-if="s.source_type === 'generated'">
                  · {{ t("admin.agentSkills.sourceGenerated") }}
                </template>
              </NTag>
              <NButton
                v-if="s.skill_id"
                text
                size="tiny"
                type="error"
                @click="removeSkillById(s.skill_id, s.name)"
              >
                {{ t("common.delete") }}
              </NButton>
            </NSpace>
          </NSpace>
        </NCard>
      </NTabPane>

      <NTabPane name="memory" :tab="t('admin.agentSkills.tabMemory')">
        <NCard size="small" :title="t('admin.agentSkills.memoryTitle')">
          <NText depth="3" style="display: block; margin-bottom: 12px">
            {{ t("admin.agentSkills.memoryHint") }}
          </NText>
          <div v-if="memoryLoading">{{ t("common.loading") }}</div>
          <template v-else>
            <NInput
              v-model:value="memoryContent"
              type="textarea"
              :rows="16"
              :placeholder="t('admin.agentSkills.memoryPlaceholder')"
            />
            <NSpace style="margin-top: 12px" :size="8">
              <NButton type="primary" :loading="memorySaving" @click="saveMemory">
                {{ t("common.save") }}
              </NButton>
              <NButton @click="loadMemory">{{ t("admin.agentSkills.reload") }}</NButton>
              <NButton type="error" quaternary @click="wipeMemory">
                {{ t("admin.agentSkills.memoryClear") }}
              </NButton>
            </NSpace>
          </template>
        </NCard>
      </NTabPane>
    </NTabs>

    <NModal
      v-model:show="createOpen"
      preset="card"
      :title="t('admin.agentSkills.createSkill')"
      style="width: 640px"
    >
      <NSpace vertical :size="12">
        <NInput v-model:value="createForm.name" :placeholder="t('admin.agentSkills.createNamePh')" />
        <NInput
          v-model:value="createForm.description"
          :placeholder="t('admin.agentSkills.createDescPh')"
        />
        <NInput
          v-model:value="createForm.skillMdBody"
          type="textarea"
          :rows="12"
          :placeholder="t('admin.agentSkills.createBodyPh')"
        />
        <NSpace justify="end">
          <NButton @click="createOpen = false">{{ t("common.cancel") }}</NButton>
          <NButton type="primary" :loading="createSaving" @click="submitCreateSkill">
            {{ t("admin.agentSkills.createSkill") }}
          </NButton>
        </NSpace>
      </NSpace>
    </NModal>

    <NDrawer v-model:show="detailOpen" :width="720" placement="right">
      <NDrawerContent :title="detail?.name || t('admin.agentSkills.detailTitle')" closable>
        <div v-if="detailLoading">{{ t("common.loading") }}</div>
        <template v-else-if="detail">
          <NText depth="3">{{ detail.description }}</NText>
          <NSpace style="margin: 12px 0" :size="8">
            <NButton size="small" @click="downloadSkill">
              {{ t("admin.agentSkills.downloadZip") }}
            </NButton>
            <NButton size="small" type="error" quaternary @click="removeSkillById(detail.id, detail.name)">
              {{ t("common.delete") }}
            </NButton>
          </NSpace>
          <NSpace style="margin: 0 0 12px" :size="8" wrap>
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
              <NSpace v-if="previewEditable" style="margin-top: 8px">
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
  </div>
</template>

<style scoped>
.agent-skills-view {
  max-width: 1200px;
}
.folder-upload {
  display: inline-block;
  cursor: pointer;
}
.folder-upload input {
  display: none;
}
.folder-upload-inner {
  width: 280px;
  padding: 24px;
  border: 1px dashed var(--n-border-color);
  border-radius: 8px;
  text-align: center;
}
.folder-upload:hover .folder-upload-inner {
  border-color: var(--n-primary-color);
}
.skill-preview {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  max-height: 480px;
  overflow: auto;
}
</style>
