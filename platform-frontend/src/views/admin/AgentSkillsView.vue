<script setup>
import { computed, h, onActivated, onMounted, ref } from "vue";
import {
  NButton,
  NCard,
  NCheckbox,
  NCheckboxGroup,
  NDataTable,
  NDivider,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NSpace,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NText,
  NTooltip,
  NUpload,
  NUploadDragger,
} from "naive-ui";
import { AddOutline, CreateOutline, DownloadOutline, FolderOpenOutline, CloudUploadOutline, SettingsOutline, TrashOutline } from "@vicons/ionicons5";
import ListRefreshButton from "../../components/ListRefreshButton.vue";
import ListTableFooter from "../../components/ListTableFooter.vue";
import IconAction from "../../components/IconAction.vue";
import FeatureSubsystemShell from "../../components/FeatureSubsystemShell.vue";
import { formatAgentDisplayName } from "../../utils/agentDisplay.js";
import { useClientListPagination } from "../../composables/useClientListPagination.js";
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
  fetchAgentProfiles,
  fetchAgentProfile,
  fetchAgentProfileFile,
  updateAgentProfileFile,
  invokeAgentSkill,
  patchAgentProfile,
  patchBuiltinSkill,
  updateAgentMemory,
  updateAgentSkill,
  updateAgentSkillFile,
  clearAgentMemory,
  uploadAgentSkillFolder,
  uploadAgentSkillZip,
} from "../../api/agentSkills.js";
import {
  createExternalAgent,
  deleteExternalAgent,
  fetchExternalAgents,
  patchExternalAgent,
} from "../../api/aipExternalAgents.js";
import { LIST_PAGE_SIZE } from "../../constants/listPage.js";
import { renderIconActionGroup } from "../../utils/tableIconActions.js";
import {
  hasAgentsTabCacheData,
  isAgentsTabCacheFresh,
  readAgentsTabCache,
  writeAgentsTabCache,
} from "../../utils/agentSkillsAgentsTabCache.js";

function normalizeBuiltinAgent(agent) {
  if (!agent) return agent;
  return {
    ...agent,
    service_enabled:
      agent.service_enabled === undefined || agent.service_enabled === null
        ? agent.enabled !== false
        : Boolean(agent.service_enabled),
  };
}

function mergeBuiltinAgent(existing, updated) {
  return normalizeBuiltinAgent({ ...existing, ...updated });
}

const ui = usePlatformUi();
const { t } = useI18n();

const initialAgentsTabCache = readAgentsTabCache({ allowStale: true });

const activeTab = ref("agents");
const registryLoading = ref(false);
const registry = ref([]);
const registryForPicker = ref([]);
const toolsLoading = ref(false);
const tools = ref([]);

const agentsLoading = ref(false);
const agents = ref(
  (initialAgentsTabCache?.agents || []).map((row) => normalizeBuiltinAgent(row))
);
const externalAgents = ref(initialAgentsTabCache?.externalAgents || []);
const agentsTabHydrated = ref(hasAgentsTabCacheData(initialAgentsTabCache));
const externalAgentsLoading = ref(false);
const externalAgentModalOpen = ref(false);
const externalAgentSaving = ref(false);
const externalAgentForm = ref({
  aid: "",
  name: "",
  description: "",
  service_endpoint: "",
  enabled: true,
});
const configDrawerOpen = ref(false);
const configDrawerAgent = ref(null);
const configDrawerKind = ref("builtin");
const configEnabled = ref(true);
const configServiceEnabled = ref(true);
const selectedSkillNames = ref([]);
const configSaving = ref(false);

const agentDetailOpen = ref(false);
const agentDetailLoading = ref(false);
const agentDetail = ref(null);
const agentPreviewPath = ref("");
const agentPreviewContent = ref("");
const agentPreviewLoading = ref(false);
const agentPreviewDirty = ref(false);
const agentPreviewSaving = ref(false);

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
const {
  page: builtinPage,
  pageSize: builtinPageSize,
  total: builtinTotal,
  pagedItems: builtinPagedItems,
  onPageChange: onBuiltinPageChange,
} = useClientListPagination(builtinSkills);

const {
  page: toolsPage,
  pageSize: toolsPageSize,
  total: toolsTotal,
  pagedItems: toolsPagedItems,
  onPageChange: onToolsPageChange,
} = useClientListPagination(tools);

const skillPickerOptions = computed(() =>
  registryForPicker.value.map((s) => ({
    title: s.title || s.name,
    name: s.name,
    description: s.description || "",
    value: s.name,
    disabled: !s.enabled,
  }))
);

const selectedSkillCount = computed(() => selectedSkillNames.value.length);

function persistAgentsTabCache() {
  writeAgentsTabCache({
    agents: agents.value,
    externalAgents: externalAgents.value,
  });
}

const agentsTabRefreshing = computed(
  () => agentsLoading.value || externalAgentsLoading.value
);

const agentsTabInitialLoading = computed(
  () => agentsTabRefreshing.value && !agentsTabHydrated.value
);

async function refreshActiveTab() {
  if (activeTab.value === "agents") {
    await reloadAgentsTab({ foreground: true });
    return;
  }
  if (activeTab.value === "tools") {
    await loadTools();
    return;
  }
  if (activeTab.value === "skills") {
    await Promise.all([loadRegistry(), loadUploadedList()]);
    return;
  }
  if (activeTab.value === "memory") {
    await loadMemory();
  }
}

async function loadAgents({ background = false, foreground = false } = {}) {
  const showLoading = foreground || (!background && !agentsTabHydrated.value);
  if (showLoading) agentsLoading.value = true;
  try {
    const rows = (await fetchAgentProfiles()) || [];
    agents.value = rows.map(normalizeBuiltinAgent);
    agentsTabHydrated.value = true;
    persistAgentsTabCache();
  } catch (e) {
    if (!background || !agentsTabHydrated.value) {
      ui.error(e.message || t("admin.agentSkills.loadFailed"));
    }
  } finally {
    if (showLoading) agentsLoading.value = false;
  }
}

async function loadExternalAgents({ background = false, foreground = false } = {}) {
  const showLoading = foreground || (!background && !agentsTabHydrated.value);
  if (showLoading) externalAgentsLoading.value = true;
  try {
    externalAgents.value = (await fetchExternalAgents()) || [];
    agentsTabHydrated.value = true;
    persistAgentsTabCache();
  } catch (e) {
    if (!background || !agentsTabHydrated.value) {
      externalAgents.value = [];
      const msg = String(e?.message || "");
      if (!/not found|404/i.test(msg)) {
        ui.error(msg || t("admin.agentSkills.loadFailed"));
      }
    }
  } finally {
    if (showLoading) externalAgentsLoading.value = false;
  }
}

async function reloadAgentsTab({ background = false, foreground = false } = {}) {
  const bg = foreground ? false : background;
  await Promise.all([
    loadAgents({ background: bg, foreground }),
    loadExternalAgents({ background: bg, foreground }),
  ]);
}

function openExternalAgentModal() {
  externalAgentForm.value = {
    aid: "",
    name: "",
    description: "",
    service_endpoint: "",
    enabled: true,
  };
  externalAgentModalOpen.value = true;
}

async function submitExternalAgent() {
  const form = externalAgentForm.value;
  if (!form.aid.trim() || !form.name.trim() || !form.service_endpoint.trim()) {
    ui.warning(t("admin.agentSkills.externalAgentFormRequired"));
    return;
  }
  externalAgentSaving.value = true;
  try {
    await createExternalAgent({
      aid: form.aid.trim(),
      name: form.name.trim(),
      description: form.description.trim(),
      service_endpoint: form.service_endpoint.trim(),
      enabled: form.enabled,
    });
    ui.success(t("admin.agentSkills.saved"));
    externalAgentModalOpen.value = false;
    await loadExternalAgents();
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    externalAgentSaving.value = false;
  }
}

async function removeExternalAgent(agent) {
  if (agent.source === "config" || !agent.id) {
    ui.info(t("admin.agentSkills.externalAgentConfigReadonly"));
    return;
  }
  await ui.confirmDelete({
    title: t("admin.agentSkills.externalAgentDeleteTitle"),
    content: t("admin.agentSkills.externalAgentDeleteConfirm", { name: agent.name }),
    onPositive: async () => {
      await deleteExternalAgent(agent.id);
      ui.success(t("admin.agentSkills.deleted"));
      await loadExternalAgents();
    },
  });
}

function agentStatusLabel(agent) {
  return agent.status === "running"
    ? t("admin.agentSkills.statusRunning")
    : t("admin.agentSkills.statusIdle");
}

function configDrawerDisplayName() {
  const agent = configDrawerAgent.value;
  if (!agent) return "";
  if (configDrawerKind.value === "external") return agent.name || agent.aid || "";
  return formatAgentDisplayName(agent.title) || agent.id || "";
}

function openConfigDrawer(agent, kind = "builtin") {
  configDrawerAgent.value = agent;
  configDrawerKind.value = kind;
  configEnabled.value = agent.enabled !== false;
  configServiceEnabled.value =
    kind === "builtin"
      ? agent.service_enabled !== undefined && agent.service_enabled !== null
        ? Boolean(agent.service_enabled)
        : agent.enabled !== false
      : agent.enabled !== false;
  selectedSkillNames.value = [...(agent.skill_names || [])];
  configDrawerOpen.value = true;
}

async function saveAgentConfig() {
  if (!configDrawerAgent.value) return;
  configSaving.value = true;
  try {
    if (configDrawerKind.value === "external") {
      const agent = configDrawerAgent.value;
      if (agent.source === "config" || !agent.id) {
        ui.info(t("admin.agentSkills.externalAgentConfigReadonly"));
        return;
      }
      const updated = await patchExternalAgent(agent.id, { enabled: configEnabled.value });
      const idx = externalAgents.value.findIndex((a) => a.id === updated.id);
      if (idx >= 0) externalAgents.value[idx] = updated;
    } else {
      const agent = configDrawerAgent.value;
      if (!agent.id) return;
      const payload = {
        enabled: configEnabled.value,
        service_enabled: configServiceEnabled.value,
      };
      if (agent.skills_configurable) {
        payload.skill_names = selectedSkillNames.value;
      }
      const updated = await patchAgentProfile(agent.id, payload);
      const idx = agents.value.findIndex((a) => a.id === updated.id);
      if (idx >= 0) agents.value[idx] = mergeBuiltinAgent(agents.value[idx], updated);
      configDrawerAgent.value = mergeBuiltinAgent(configDrawerAgent.value, updated);
      if (agentDetail.value?.id === updated.id) {
        agentDetail.value = { ...agentDetail.value, ...updated };
      }
    }
    ui.success(t("admin.agentSkills.saved"));
    configDrawerOpen.value = false;
    persistAgentsTabCache();
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    configSaving.value = false;
  }
}

async function openAgentDetail(agent) {
  agentDetailOpen.value = true;
  agentDetailLoading.value = true;
  agentPreviewPath.value = "";
  agentPreviewContent.value = "";
  try {
    agentDetail.value = await fetchAgentProfile(agent.id);
    if (agentDetail.value?.files?.includes("AGENT.md")) {
      await loadAgentPreview("AGENT.md");
    }
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    agentDetailLoading.value = false;
  }
}

async function loadAgentPreview(path) {
  if (!agentDetail.value?.id) return;
  agentPreviewLoading.value = true;
  agentPreviewPath.value = path;
  agentPreviewDirty.value = false;
  try {
    const file = await fetchAgentProfileFile(agentDetail.value.id, path);
    agentPreviewContent.value = file?.text || "";
  } catch (e) {
    agentPreviewContent.value = e.message || "";
  } finally {
    agentPreviewLoading.value = false;
  }
}

async function saveAgentPreview() {
  if (!agentDetail.value?.id || !agentPreviewPath.value) return;
  agentPreviewSaving.value = true;
  try {
    await updateAgentProfileFile(
      agentDetail.value.id,
      agentPreviewPath.value,
      agentPreviewContent.value
    );
    agentPreviewDirty.value = false;
    ui.success(t("admin.agentSkills.saved"));
    agentDetail.value = await fetchAgentProfile(agentDetail.value.id);
    const idx = agents.value.findIndex((a) => a.id === agentDetail.value.id);
    if (idx >= 0) agents.value[idx] = { ...agents.value[idx], ...agentDetail.value };
    persistAgentsTabCache();
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    agentPreviewSaving.value = false;
  }
}

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
    const [catalog, picker] = await Promise.all([
      fetchAgentSkillRegistry({ includeDisabled: true, catalogOnly: true }),
      fetchAgentSkillRegistry({ includeDisabled: true, catalogOnly: false }),
    ]);
    registry.value = catalog || [];
    registryForPicker.value = picker || [];
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
  await Promise.all([
    loadAgents(),
    loadExternalAgents(),
    loadTools(),
    loadRegistry(),
    loadUploadedList(),
  ]);
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
    createOpen.value = false;
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
    createOpen.value = false;
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
    ellipsis: { tooltip: true },
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
    width: 88,
    render: (row) =>
      renderIconActionGroup([
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
      ]),
  },
]);

onMounted(async () => {
  if (agentsTabHydrated.value) {
    void reloadAgentsTab({ background: !isAgentsTabCacheFresh() });
  } else {
    await reloadAgentsTab();
  }
  void Promise.all([loadTools(), loadRegistry(), loadUploadedList()]);
  await loadMemory();
});

onActivated(async () => {
  if (agentsTabHydrated.value) {
    void reloadAgentsTab({ background: !isAgentsTabCacheFresh() });
    return;
  }
  await reloadAgentsTab();
});
</script>

<template>
  <FeatureSubsystemShell :show-intro="false">
    <template #extra>
      <div class="agent-skills-toolbar">
        <NText depth="3" class="agent-skills-toolbar__hint">
          {{ t(`admin.agentSkills.toolbarHint.${activeTab}`) }}
        </NText>
        <NSpace align="center" :size="8" class="agent-skills-toolbar__actions">
          <ListRefreshButton
            :loading="
              activeTab === 'agents'
                ? agentsTabRefreshing
                : activeTab === 'tools'
                  ? toolsLoading
                  : activeTab === 'skills'
                    ? registryLoading || loading
                    : memoryLoading
            "
            @click="refreshActiveTab"
          />
          <IconAction
            v-if="activeTab === 'agents'"
            type="primary"
            :label="t('admin.agentSkills.connectExternalAgent')"
            :icon="DownloadOutline"
            @click="openExternalAgentModal"
          />
        </NSpace>
      </div>
    </template>

    <div class="agent-skills-view">
    <NTabs v-model:value="activeTab" type="line" animated>
      <NTabPane name="agents" :tab="t('admin.agentSkills.tabAgents')">
        <NText depth="3" class="agents-tab-hint">
          {{ t("admin.agentSkills.agentsHint") }}
        </NText>
        <div v-if="agentsTabInitialLoading">{{ t("common.loading") }}</div>
        <div v-else class="agent-card-grid">
          <NCard
            v-for="agent in agents"
            :key="agent.id"
            size="small"
            class="agent-card agent-card--clickable"
            :class="{ 'agent-card--disabled': !agent.enabled }"
            @click="openAgentDetail(agent)"
          >
            <div class="agent-card__head">
              <span
                class="agent-status-dot"
                :class="agent.status === 'running' ? 'agent-status-dot--running' : 'agent-status-dot--idle'"
                :title="agentStatusLabel(agent)"
              />
              <div class="agent-card__identity">
                <div class="agent-card-title">{{ formatAgentDisplayName(agent.title) }}</div>
              </div>
              <span class="agent-card__badge agent-card__badge--builtin">
                {{ t("admin.agentSkills.builtinAgentTag") }}
              </span>
            </div>

            <div class="agent-card__desc-wrap">
              <NText
                v-if="agent.description"
                depth="3"
                class="agent-card__desc"
                :title="agent.description"
              >
                {{ agent.description }}
              </NText>
            </div>

            <div class="agent-card__bottom" @click.stop>
              <div class="agent-card__meta">
                <span class="agent-card__meta-item">
                  {{ t("admin.agentSkills.toolsCount", { count: agent.tool_count }) }}
                </span>
                <span class="agent-card__meta-sep" aria-hidden="true">·</span>
                <span class="agent-card__meta-item">
                  {{ t("admin.agentSkills.skillsCount", { count: agent.skill_names?.length || 0 }) }}
                </span>
                <template v-if="!agent.enabled">
                  <span class="agent-card__meta-sep" aria-hidden="true">·</span>
                  <span class="agent-card__meta-item agent-card__meta-item--warn">
                    {{ t("admin.agentSkills.disabledAgent") }}
                  </span>
                </template>
                <template v-else-if="!agent.service_enabled">
                  <span class="agent-card__meta-sep" aria-hidden="true">·</span>
                  <span class="agent-card__meta-item agent-card__meta-item--warn">
                    {{ t("admin.agentSkills.serviceClosed") }}
                  </span>
                </template>
              </div>
              <div class="agent-card__actions">
                <IconAction
                  variant="table"
                  type="primary"
                  :label="t('admin.agentSkills.configure')"
                  :icon="SettingsOutline"
                  @click="openConfigDrawer(agent)"
                />
              </div>
            </div>
          </NCard>

          <NCard
            v-for="agent in externalAgents"
            :key="agent.aid"
            size="small"
            class="agent-card agent-card--external"
            :class="{ 'agent-card--disabled': !agent.enabled }"
          >
            <div class="agent-card__head">
              <div class="agent-card__identity">
                <div class="agent-card-title">{{ agent.name }}</div>
              </div>
              <NTag size="small" type="info" :bordered="false" class="agent-card__badge">
                {{ t("admin.agentSkills.externalAgentTag") }}
              </NTag>
            </div>

            <div class="agent-card__desc-wrap">
              <NText
                v-if="agent.description || agent.service_endpoint"
                depth="3"
                class="agent-card__desc"
                :title="agent.description || agent.service_endpoint"
              >
                {{ agent.description || agent.service_endpoint }}
              </NText>
            </div>

            <div class="agent-card__bottom">
              <div class="agent-card__meta">
                <span v-if="agent.source === 'config'" class="agent-card__meta-item">
                  {{ t("admin.agentSkills.externalAgentConfigSource") }}
                </span>
                <span
                  v-if="agent.source === 'config' && !agent.enabled"
                  class="agent-card__meta-sep"
                  aria-hidden="true"
                >
                  ·
                </span>
                <span v-if="!agent.enabled" class="agent-card__meta-item agent-card__meta-item--warn">
                  {{ t("admin.agentSkills.serviceClosed") }}
                </span>
              </div>
              <div class="agent-card__actions">
                <IconAction
                  variant="table"
                  type="primary"
                  :label="t('admin.agentSkills.configure')"
                  :icon="SettingsOutline"
                  @click="openConfigDrawer(agent, 'external')"
                />
                <IconAction
                  v-if="agent.source !== 'config'"
                  variant="table"
                  type="error"
                  :label="t('common.delete')"
                  :icon="TrashOutline"
                  @click="removeExternalAgent(agent)"
                />
              </div>
            </div>
          </NCard>
        </div>
      </NTabPane>

      <NTabPane name="skills" :tab="t('admin.agentSkills.tabSkills')">
        <NCard size="small" :title="t('admin.agentSkills.builtinTitle')" style="margin-bottom: 16px">
          <template #header-extra>
            <ListRefreshButton :loading="registryLoading" @click="loadRegistry" />
          </template>
          <NText depth="3" style="display: block; margin-bottom: 12px">
            {{ t("admin.agentSkills.builtinHint") }}
          </NText>
          <div class="admin-list-table">
            <NDataTable
              :loading="registryLoading"
              :columns="builtinColumns"
              :data="builtinPagedItems"
              :pagination="false"
            />
            <ListTableFooter
              :page="builtinPage"
              :page-size="builtinPageSize"
              :item-count="builtinTotal"
              @update:page="onBuiltinPageChange"
            />
          </div>
        </NCard>

        <NCard size="small" style="margin-bottom: 16px">
          <template #header>
            <NSpace justify="space-between" align="center" style="width: 100%">
              <span>{{ t("admin.agentSkills.listTitle") }}</span>
              <NSpace align="center" :size="8">
                <NTooltip placement="bottom">
                  <template #trigger>
                    <NButton
                      circle
                      quaternary
                      size="small"
                      :aria-label="t('admin.agentSkills.developedTitle')"
                      @click="createOpen = true"
                    >
                      <NIcon :component="AddOutline" />
                    </NButton>
                  </template>
                  {{ t("admin.agentSkills.developedTitle") }}
                </NTooltip>
                <ListRefreshButton :loading="loading" @click="loadUploadedList" />
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
          <NText depth="3" style="display: block; margin-bottom: 12px">
            {{ t("admin.agentSkills.developedListHint") }}
          </NText>
          <div class="admin-list-table">
            <NDataTable
              remote
              :loading="loading"
              :columns="uploadedColumns"
              :data="skills"
              :pagination="false"
            />
            <ListTableFooter
              :page="page"
              :page-size="LIST_PAGE_SIZE"
              :item-count="total"
              @update:page="handlePageChange"
            />
          </div>
        </NCard>
      </NTabPane>

      <NTabPane name="tools" :tab="t('admin.agentSkills.tabTools')">
        <NCard size="small" :title="t('admin.agentSkills.toolsTitle')">
          <template #header-extra>
            <ListRefreshButton :loading="toolsLoading" @click="loadTools" />
          </template>
          <NText depth="3" style="display: block; margin-bottom: 12px">
            {{ t("admin.agentSkills.toolsHint") }}
          </NText>
          <div class="admin-list-table">
            <NDataTable
              :loading="toolsLoading"
              :columns="toolColumns"
              :data="toolsPagedItems"
              :pagination="false"
            />
            <ListTableFooter
              :page="toolsPage"
              :page-size="toolsPageSize"
              :item-count="toolsTotal"
              @update:page="onToolsPageChange"
            />
          </div>
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
      :title="t('admin.agentSkills.developedTitle')"
      style="width: 640px"
    >
      <NSpace vertical :size="16">
        <NText depth="3">{{ t("admin.agentSkills.developedHint") }}</NText>
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
            <IconAction
              variant="table"
              type="error"
              :label="t('common.delete')"
              :icon="TrashOutline"
              @click="removeSkillById(detail.id, detail.name)"
            />
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

    <NDrawer v-model:show="agentDetailOpen" :width="720" placement="right">
      <NDrawerContent
        :title="
          t('admin.agentSkills.agentDetailTitle', { name: agentDetail?.title || '' })
        "
        closable
      >
        <div v-if="agentDetailLoading">{{ t("common.loading") }}</div>
        <template v-else-if="agentDetail">
          <NText depth="3">{{ agentDetail.description }}</NText>
          <NText depth="3" style="display: block; margin: 12px 0">
            {{ t("admin.agentSkills.agentConfigHint") }}
          </NText>
          <NSpace style="margin: 0 0 12px" :size="8" wrap>
            <NTag
              v-for="f in agentDetail.files || []"
              :key="f"
              size="small"
              :bordered="false"
              checkable
              :checked="agentPreviewPath === f"
              @click="loadAgentPreview(f)"
            >
              {{ f }}
            </NTag>
          </NSpace>
          <NCard v-if="agentPreviewPath" size="small" :title="agentPreviewPath">
            <div v-if="agentPreviewLoading">{{ t("common.loading") }}</div>
            <template v-else>
              <NInput
                v-model:value="agentPreviewContent"
                type="textarea"
                :rows="18"
                @update:value="agentPreviewDirty = true"
              />
              <NSpace style="margin-top: 8px">
                <NButton
                  type="primary"
                  size="small"
                  :loading="agentPreviewSaving"
                  :disabled="!agentPreviewDirty"
                  @click="saveAgentPreview"
                >
                  {{ t("common.save") }}
                </NButton>
                <IconAction
                  variant="table"
                  type="primary"
                  :label="t('admin.agentSkills.configure')"
                  :icon="SettingsOutline"
                  @click="openConfigDrawer(agentDetail)"
                />
              </NSpace>
            </template>
          </NCard>
        </template>
      </NDrawerContent>
    </NDrawer>

    <NDrawer v-model:show="configDrawerOpen" :width="420" placement="right">
      <NDrawerContent
        :title="t('admin.agentSkills.configDrawerTitle', { name: configDrawerDisplayName() })"
        closable
        :native-scrollbar="false"
        body-content-style="padding: 16px 20px 12px; display: flex; flex-direction: column; gap: 0;"
      >
        <div class="agent-config-drawer">
          <section class="agent-config-drawer__section">
            <div class="agent-config-drawer__section-title">
              {{ t("admin.agentSkills.configSectionGeneral") }}
            </div>
            <div class="agent-config-drawer__panel">
            <div
              v-if="configDrawerKind === 'builtin' && configDrawerAgent?.id !== 'orchestrator'"
              class="agent-config-drawer__row"
            >
              <div class="agent-config-drawer__row-text">
                <NText>{{ t("admin.agentSkills.agentEnabled") }}</NText>
                <NText depth="3">{{ t("admin.agentSkills.agentEnabledHint") }}</NText>
              </div>
              <NSwitch v-model:value="configEnabled" size="small" />
            </div>
            <div class="agent-config-drawer__row">
              <div class="agent-config-drawer__row-text">
                <NText>{{ t("admin.agentSkills.serviceEnabled") }}</NText>
                <NText depth="3">
                  {{
                    configDrawerKind === "external"
                      ? t("admin.agentSkills.externalServiceHint")
                      : t("admin.agentSkills.serviceEnabledHint")
                  }}
                </NText>
              </div>
              <NSwitch
                v-if="configDrawerKind === 'external'"
                v-model:value="configEnabled"
                size="small"
                :disabled="configDrawerAgent?.source === 'config'"
              />
              <NSwitch
                v-else
                v-model:value="configServiceEnabled"
                size="small"
                :disabled="
                  configDrawerAgent?.id !== 'orchestrator' && !configEnabled
                "
              />
            </div>
            <NText
              v-if="configDrawerKind === 'external' && configDrawerAgent?.source === 'config'"
              depth="3"
              class="agent-config-drawer__readonly-hint"
            >
              {{ t("admin.agentSkills.externalAgentConfigReadonly") }}
            </NText>
            </div>
          </section>

          <template
            v-if="configDrawerKind === 'builtin' && configDrawerAgent?.skills_configurable"
          >
            <NDivider class="agent-config-drawer__divider" />
            <section class="agent-config-drawer__section">
              <div class="agent-config-drawer__section-head">
                <div class="agent-config-drawer__section-title">
                  {{ t("admin.agentSkills.configSectionSkills") }}
                </div>
                <NTag size="small" :bordered="false" class="agent-config-drawer__skill-count">
                  {{ t("admin.agentSkills.skillsCount", { count: selectedSkillCount }) }}
                </NTag>
              </div>
              <NText depth="3" class="agent-config-drawer__section-hint">
                {{ t("admin.agentSkills.skillPickerHint") }}
              </NText>
              <NCheckboxGroup v-model:value="selectedSkillNames" class="agent-config-drawer__skills">
                <div class="agent-config-drawer__skill-list">
                  <div
                    v-for="opt in skillPickerOptions"
                    :key="opt.value"
                    class="agent-skill-option"
                    :class="{
                      'agent-skill-option--checked': selectedSkillNames.includes(opt.value),
                      'agent-skill-option--disabled': opt.disabled,
                    }"
                  >
                    <NCheckbox :value="opt.value" :disabled="opt.disabled" class="agent-skill-option__checkbox">
                      <div class="agent-skill-option__body">
                        <span class="agent-skill-option__title">{{ opt.title }}</span>
                        <span v-if="opt.title !== opt.name" class="agent-skill-option__name">
                          {{ opt.name }}
                        </span>
                        <span v-if="opt.description" class="agent-skill-option__desc">
                          {{ opt.description }}
                        </span>
                      </div>
                    </NCheckbox>
                  </div>
                </div>
              </NCheckboxGroup>
            </section>
          </template>
        </div>
        <template #footer>
          <NSpace justify="end" :size="8">
            <NButton @click="configDrawerOpen = false">{{ t("common.cancel") }}</NButton>
            <NButton
              type="primary"
              :loading="configSaving"
              :disabled="
                configDrawerKind === 'external' && configDrawerAgent?.source === 'config'
              "
              @click="saveAgentConfig"
            >
              {{ t("common.save") }}
            </NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

    <NModal
      v-model:show="externalAgentModalOpen"
      preset="card"
      :title="t('admin.agentSkills.connectExternalAgent')"
      style="width: 640px"
      :mask-closable="false"
    >
      <NText depth="3" style="display: block; margin-bottom: 16px">
        {{ t("admin.agentSkills.externalAgentModalHint") }}
      </NText>
      <NForm @submit.prevent="submitExternalAgent">
        <NFormItem :label="t('admin.agentSkills.externalAgentAid')" required>
          <NInput v-model:value="externalAgentForm.aid" :placeholder="t('admin.agentSkills.externalAgentAidPh')" />
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.externalAgentName')" required>
          <NInput v-model:value="externalAgentForm.name" :placeholder="t('admin.agentSkills.externalAgentNamePh')" />
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.externalAgentEndpoint')" required>
          <NInput
            v-model:value="externalAgentForm.service_endpoint"
            :placeholder="t('admin.agentSkills.externalAgentEndpointPh')"
          />
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.colDescription')">
          <NInput
            v-model:value="externalAgentForm.description"
            type="textarea"
            :rows="3"
            :placeholder="t('admin.agentSkills.externalAgentDescPh')"
          />
        </NFormItem>
        <NFormItem :label="t('admin.agentSkills.serviceEnabled')">
          <NSwitch v-model:value="externalAgentForm.enabled" />
        </NFormItem>
        <NSpace justify="end">
          <NButton @click="externalAgentModalOpen = false">{{ t("common.cancel") }}</NButton>
          <NButton type="primary" :loading="externalAgentSaving" @click="submitExternalAgent">
            {{ t("common.save") }}
          </NButton>
        </NSpace>
      </NForm>
    </NModal>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.agent-skills-view {
  max-width: 1200px;
}
.agent-skills-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px 16px;
  width: 100%;
  min-width: 0;
}
.agent-skills-toolbar__hint {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 1.45;
}
.agent-skills-toolbar__actions {
  flex-shrink: 0;
  margin-left: auto;
}
.agents-tab-hint {
  display: block;
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.45;
}
.agent-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.agent-card {
  height: 100%;
}
.agent-card :deep(.n-card) {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.agent-card :deep(.n-card__content) {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  height: 100%;
  padding: 10px 11px !important;
}
.agent-card--disabled {
  opacity: 0.72;
}
.agent-card--external {
  border-style: dashed;
}
.agent-card--clickable {
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.agent-card--clickable:hover {
  box-shadow: var(--platform-shadow-sm);
}
.agent-card__head {
  display: flex;
  align-items: center;
  gap: 7px;
}
.agent-card__identity {
  flex: 1;
  min-width: 0;
}
.agent-card-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  letter-spacing: -0.01em;
}
.agent-card__head :deep(.agent-card__badge) {
  font-size: 9px;
  padding: 0 5px;
  --n-height: 16px;
}
.agent-card__badge--builtin {
  flex-shrink: 0;
  font-size: 8px;
  line-height: 1.2;
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 500;
  color: var(--platform-text-tertiary);
  background: color-mix(in srgb, var(--platform-bg-muted, #f5f5f7) 72%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-border) 45%, transparent);
}
.agent-card-id {
  display: block;
  font-size: 11px;
  word-break: break-all;
}
.agent-card__desc-wrap {
  flex: 1 1 auto;
  min-height: calc(10px * 1.45 * 3);
  margin-top: 4px;
  padding-bottom: 8px;
}
.agent-card__desc {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  overflow: hidden;
  font-size: 10px;
  line-height: 1.45;
}
.agent-card__bottom {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid color-mix(in srgb, var(--platform-border) 50%, transparent);
}
.agent-card__actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 4px;
}
.agent-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 4px;
  font-size: 9px;
  line-height: 1.35;
  color: var(--platform-text-tertiary);
}
.agent-card__meta-item--warn {
  color: var(--n-warning-color, #f0a020);
}
.agent-card__meta-sep {
  color: color-mix(in srgb, var(--platform-text-tertiary) 55%, transparent);
  user-select: none;
}
.agent-config-drawer__divider {
  margin: 14px 0 !important;
}
.agent-config-drawer__section > .agent-config-drawer__section-title {
  margin-bottom: 8px;
}
.agent-config-drawer__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.agent-config-drawer__section-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: none;
  color: var(--platform-text-secondary);
}
.agent-config-drawer__skill-count :deep(.n-tag) {
  font-size: 10px;
  --n-height: 18px;
}
.agent-config-drawer__panel {
  border: 1px solid color-mix(in srgb, var(--platform-border) 62%, transparent);
  border-radius: 10px;
  overflow: hidden;
  background: color-mix(in srgb, var(--platform-bg-muted, #f5f5f7) 38%, transparent);
}
.agent-config-drawer__section-hint {
  display: block;
  font-size: 11px;
  line-height: 1.45;
  margin-bottom: 8px;
}
.agent-config-drawer__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 12px;
}
.agent-config-drawer__row + .agent-config-drawer__row {
  border-top: 1px solid color-mix(in srgb, var(--platform-border) 55%, transparent);
}
.agent-config-drawer__row-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}
.agent-config-drawer__row-text :deep(.n-text) {
  font-size: 12px;
}
.agent-config-drawer__row-text :deep(.n-text--depth-3) {
  font-size: 11px;
  line-height: 1.35;
}
.agent-config-drawer__readonly-hint {
  display: block;
  padding: 0 12px 10px;
  font-size: 11px;
  line-height: 1.45;
}
.agent-config-drawer__skills {
  max-height: min(52vh, 420px);
  overflow: auto;
  padding-right: 2px;
}
.agent-config-drawer__skill-list {
  border: 1px solid color-mix(in srgb, var(--platform-border) 62%, transparent);
  border-radius: 10px;
  overflow: hidden;
  background: color-mix(in srgb, var(--platform-bg-muted, #f5f5f7) 28%, transparent);
}
.agent-skill-option {
  border-bottom: 1px solid color-mix(in srgb, var(--platform-border) 50%, transparent);
  transition: background 0.15s ease;
}
.agent-skill-option:last-child {
  border-bottom: none;
}
.agent-skill-option--checked {
  background: color-mix(in srgb, var(--platform-accent) 7%, transparent);
}
.agent-skill-option--disabled {
  opacity: 0.58;
}
.agent-skill-option__checkbox {
  width: 100%;
  padding: 9px 12px;
  margin: 0;
}
.agent-skill-option__checkbox :deep(.n-checkbox) {
  align-items: flex-start;
  width: 100%;
}
.agent-skill-option__checkbox :deep(.n-checkbox-box-wrapper) {
  margin-top: 1px;
}
.agent-skill-option__checkbox :deep(.n-checkbox__label) {
  flex: 1;
  min-width: 0;
  padding-right: 0;
}
.agent-skill-option__body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.agent-skill-option__title {
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}
.agent-skill-option__name {
  font-size: 10px;
  line-height: 1.35;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: var(--platform-text-tertiary);
}
.agent-skill-option__desc {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
}
.agent-card__status-tags {
  flex: 1;
  min-width: 0;
}
.agent-status-dot {
  display: inline-block;
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px solid var(--platform-bg-elevated-solid, #fff);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--platform-border) 80%, transparent);
}
.agent-status-dot--running {
  background: #22c55e;
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--platform-border) 80%, transparent),
    0 0 0 3px color-mix(in srgb, #22c55e 28%, transparent);
}
.agent-status-dot--idle {
  background: var(--platform-text-quaternary, #8e8e93);
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
