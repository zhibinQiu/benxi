<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import {
  NButton,
  NCard,
  NCheckbox,
  NCheckboxGroup,
  NDivider,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NScrollbar,
  NSpace,
  NSpin,
  NSwitch,
  NTag,
  NText,
} from "naive-ui";
import { SettingsOutline, TrashOutline } from "@vicons/ionicons5";
import IconAction from "../IconAction.vue";
import AdminFormModal from "../AdminFormModal.vue";
import { formatAgentDisplayName } from "../../utils/agentDisplay.js";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import {
  addKnowledgeMount,
  fetchAgentProfileFile,
  fetchAgentProfiles,
  fetchAgentSkillRegistry,
  fetchAgentTools,
  fetchKnowledgeMounts,
  patchAgentProfile,
  removeKnowledgeMount,
  updateAgentProfileFile,
} from "../../api/agentSkills.js";
import {
  createExternalAgent,
  deleteExternalAgent,
  fetchExternalAgents,
  patchExternalAgent,
} from "../../api/aipExternalAgents.js";
import {
  hasAgentsTabCacheData,
  isAgentsTabCacheFresh,
  readAgentsTabCache,
  writeAgentsTabCache,
} from "../../utils/agentSkillsAgentsTabCache.js";
import { mergeBuiltinAgent, normalizeBuiltinAgent } from "../../utils/agentSkillsHelpers.js";

const emit = defineEmits(["registry-changed"]);

const ui = usePlatformUi();
const { t } = useI18n();

const initialCache = readAgentsTabCache({ allowStale: true });

const loading = ref(false);
const externalLoading = ref(false);
const hydrated = ref(hasAgentsTabCacheData(initialCache));
const agents = ref((initialCache?.agents || []).map((row) => normalizeBuiltinAgent(row)));
const externalAgents = ref(initialCache?.externalAgents || []);
const keyword = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);
const registryForPicker = ref([]);

function toggleSearch() {
  searchOpen.value = !searchOpen.value;
  if (searchOpen.value) {
    nextTick(() => searchInputRef.value?.focus?.());
  } else {
    keyword.value = "";
  }
}

const configDrawerOpen = ref(false);
const configDrawerAgent = ref(null);
const configDrawerKind = ref("builtin");
const configEnabled = ref(true);
const configServiceEnabled = ref(true);
const selectedSkillNames = ref([]);
const configSaving = ref(false);

const configActiveTab = ref("agent-md");
const configAgentMdContent = ref("");
const configAgentMdLoading = ref(false);
const configAgentMdDirty = ref(false);
const configAgentMdSaving = ref(false);
const configStyleMdContent = ref("");
const configStyleMdLoading = ref(false);
const configStyleMdDirty = ref(false);
const configStyleMdSaving = ref(false);

// ── 文件夹 tab（文档树勾选） ─────────────────────
const configFolderTreeLoading = ref(false);
const configFolderList = ref([]);
const configMountedFolderKeys = ref(new Set());
const configFolderToggling = ref(new Set());
/** folderKey -> mountId 映射，用于移除挂载 */
const configFolderMountIdMap = ref({});

// ── 工具 tab ──────────────────────────────────────
const configToolsLoading = ref(false);
const configAgentTools = ref([]);

const externalAgentModalOpen = ref(false);
const externalAgentSaving = ref(false);
const externalAgentForm = ref({
  aid: "",
  name: "",
  description: "",
  service_endpoint: "",
  enabled: true,
});

const refreshing = computed(() => loading.value || externalLoading.value);
const initialLoading = computed(() => refreshing.value && !hydrated.value);

const skillPickerOptions = computed(() =>
  registryForPicker.value.map((s) => ({
    title: s.title || s.name,
    name: s.name,
    description: s.description || "",
    value: s.name,
    disabled: !s.enabled,
  }))
);

const filteredAgents = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  if (!q) return agents.value;
  return agents.value.filter((a) => {
    const hay = [a.title, a.id, a.description].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(q);
  });
});

const filteredExternalAgents = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  if (!q) return externalAgents.value;
  return externalAgents.value.filter((a) => {
    const hay = [a.name, a.aid, a.description, a.service_endpoint].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(q);
  });
});

const selectedSkillCount = computed(() => selectedSkillNames.value.length);

const showAgentEmpty = computed(() =>
  keyword.value.trim() && !filteredAgents.value.length && !filteredExternalAgents.value.length
);

function persistCache() {
  writeAgentsTabCache({
    agents: agents.value,
    externalAgents: externalAgents.value,
  });
}

async function loadRegistryForPicker() {
  try {
    registryForPicker.value =
      (await fetchAgentSkillRegistry({ includeDisabled: true, catalogOnly: false })) || [];
  } catch {
    registryForPicker.value = [];
  }
}

async function loadAgents({ background = false, foreground = false } = {}) {
  const showLoading = foreground || (!background && !hydrated.value);
  if (showLoading) loading.value = true;
  try {
    const rows = (await fetchAgentProfiles()) || [];
    agents.value = rows.map(normalizeBuiltinAgent);
    // 并行拉取每个内置智能体的知识库挂载数量
    await Promise.all(
      agents.value.map(async (agent) => {
        try {
          const res = await fetchKnowledgeMounts(agent.id);
          agent.mount_count = res?.data?.length ?? 0;
        } catch {
          agent.mount_count = 0;
        }
      })
    );
    hydrated.value = true;
    persistCache();
  } catch (e) {
    if (!background || !hydrated.value) {
      ui.error(e.message || t("admin.agentSkills.loadFailed"));
    }
  } finally {
    if (showLoading) loading.value = false;
  }
}

async function loadExternalAgents({ background = false, foreground = false } = {}) {
  const showLoading = foreground || (!background && !hydrated.value);
  if (showLoading) externalLoading.value = true;
  try {
    externalAgents.value = (await fetchExternalAgents()) || [];
    hydrated.value = true;
    persistCache();
  } catch (e) {
    if (!background || !hydrated.value) {
      externalAgents.value = [];
      const msg = String(e?.message || "");
      if (!/not found|404/i.test(msg)) {
        ui.error(msg || t("admin.agentSkills.loadFailed"));
      }
    }
  } finally {
    if (showLoading) externalLoading.value = false;
  }
}

async function reload({ background = false, foreground = false } = {}) {
  const bg = foreground ? false : background;
  await Promise.all([
    loadAgents({ background: bg, foreground }),
    loadExternalAgents({ background: bg, foreground }),
  ]);
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

async function openConfigDrawer(agent, kind = "builtin") {
  if (kind === "builtin" && agent.skills_configurable) {
    await loadRegistryForPicker();
  }
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
  configActiveTab.value = "agent-md";
  configDrawerOpen.value = true;
  if (kind === "builtin") {
    loadConfigAgentMd();
    loadConfigStyleMd();
    loadConfigFolderTree();
    loadConfigAgentTools();
  }
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
      emit("registry-changed");
    }
    ui.success(t("admin.agentSkills.saved"));
    configDrawerOpen.value = false;
    persistCache();
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    configSaving.value = false;
  }
}

async function loadConfigAgentMd() {
  const agent = configDrawerAgent.value;
  if (!agent?.id) return;
  configAgentMdLoading.value = true;
  configAgentMdContent.value = "";
  configAgentMdDirty.value = false;
  try {
    const file = await fetchAgentProfileFile(agent.id, "AGENT.md");
    configAgentMdContent.value = file?.text || "";
  } catch {
    configAgentMdContent.value = "";
  } finally {
    configAgentMdLoading.value = false;
  }
}

async function saveConfigAgentMd() {
  const agent = configDrawerAgent.value;
  if (!agent?.id) return;
  configAgentMdSaving.value = true;
  try {
    await updateAgentProfileFile(agent.id, "AGENT.md", configAgentMdContent.value);
    configAgentMdDirty.value = false;
    ui.success(t("admin.agentSkills.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    configAgentMdSaving.value = false;
  }
}

async function loadConfigStyleMd() {
  const agent = configDrawerAgent.value;
  if (!agent?.id) return;
  configStyleMdLoading.value = true;
  configStyleMdContent.value = "";
  configStyleMdDirty.value = false;
  try {
    const file = await fetchAgentProfileFile(agent.id, "STYLE.md");
    configStyleMdContent.value = file?.text || "";
  } catch {
    configStyleMdContent.value = "";
  } finally {
    configStyleMdLoading.value = false;
  }
}

async function saveConfigStyleMd() {
  const agent = configDrawerAgent.value;
  if (!agent?.id) return;
  configStyleMdSaving.value = true;
  try {
    await updateAgentProfileFile(agent.id, "STYLE.md", configStyleMdContent.value);
    configStyleMdDirty.value = false;
    ui.success(t("admin.agentSkills.saved"));
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    configStyleMdSaving.value = false;
  }
}

// ── 文件夹 tab：加载文档树与当前挂载 ──────────────
async function loadConfigFolderTree() {
  const agent = configDrawerAgent.value;
  if (!agent?.id) return;
  configFolderTreeLoading.value = true;
  try {
    const [foldersRes, mountsRes] = await Promise.all([
      import("../../api/knowledge.js").then((m) => m.fetchMountableFolders()),
      fetchKnowledgeMounts(agent.id),
    ]);
    const folders = foldersRes ?? [];
    // 按 library_label 分组构建树
    const libMap = {};
    for (const f of folders) {
      const mountId = f.folder_id || f.virtual_folder_id;
      if (!mountId) continue;
      const lib = f.library_label || t("admin.agentSkills.unknownLibrary");
      if (!libMap[lib]) libMap[lib] = { label: lib, scope: "library", children: [] };
      libMap[lib].children.push({
        key: `${f.dataset_id}::${mountId}`,
        label: f.label,
        scope: f.scope,
        dataset_id: f.dataset_id,
        folder_id: mountId,
        document_count: f.document_count || 0,
      });
    }
    const tree = Object.values(libMap);
    // 构建已挂载 keys 及 mountId 映射
    const mountedKeys = new Set();
    const mountIdMap = {};
    for (const m of mountsRes || []) {
      const key = `${m.dataset_id}::${m.folder_id}`;
      mountedKeys.add(key);
      mountIdMap[key] = m.id;
    }
    configFolderList.value = tree;
    configMountedFolderKeys.value = mountedKeys;
    configFolderMountIdMap.value = mountIdMap;
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.loadFailed"));
  } finally {
    configFolderTreeLoading.value = false;
  }
}

/** 将树结构拍平为展示数据（按 library 分组） */
const folderTreeData = computed(() => {
  const mapKey = (lib) => {
    const node = {
      key: lib.label,
      label: lib.label,
      children: lib.children ? lib.children.map((f) => ({
        key: f.key,
        label: f.label,
        _folder: f,
      })) : [],
    };
    return node;
  };
  return configFolderList.value.map(mapKey);
});

const folderCheckedKeys = computed({
  get: () => Array.from(configMountedFolderKeys.value),
  set: (keys) => {
    configMountedFolderKeys.value = new Set(keys);
  },
});

async function handleFolderCheck(keys) {
  const agent = configDrawerAgent.value;
  if (!agent?.id) return;
  const prevKeys = new Set(configMountedFolderKeys.value);
  const newKeys = new Set(keys);
  const toAdd = [...newKeys].filter((k) => !prevKeys.has(k));
  const toRemove = [...prevKeys].filter((k) => !newKeys.has(k));

  // 先更新本地状态
  configMountedFolderKeys.value = newKeys;

  for (const key of toAdd) {
    configFolderToggling.value = new Set([...configFolderToggling.value, key]);
    const [dsId, folderId] = key.split("::");
    // 从 folderList 找 entry
    const entry = findFolderEntry(key);
    if (!entry) continue;
    try {
      const res = await addKnowledgeMount(agent.id, {
        datasetId: dsId,
        folderId,
        scope: entry.scope,
        label: entry.label,
      });
      // 记录新挂载的 mountId
      if (res?.id) {
        configFolderMountIdMap.value = { ...configFolderMountIdMap.value, [key]: res.id };
      }
    } catch (e) {
      configMountedFolderKeys.value = prevKeys;
      ui.error(e.message || t("admin.agentSkills.saveFailed"));
    } finally {
      const s = new Set(configFolderToggling.value);
      s.delete(key);
      configFolderToggling.value = s;
    }
  }

  for (const key of toRemove) {
    configFolderToggling.value = new Set([...configFolderToggling.value, key]);
    const mountId = findMountId(key);
    if (!mountId) continue;
    try {
      await removeKnowledgeMount(agent.id, mountId);
    } catch (e) {
      configMountedFolderKeys.value = prevKeys;
      ui.error(e.message || t("admin.agentSkills.saveFailed"));
    } finally {
      const s = new Set(configFolderToggling.value);
      s.delete(key);
      configFolderToggling.value = s;
    }
  }
}

function findFolderEntry(key) {
  for (const lib of configFolderList.value) {
    for (const child of lib.children || []) {
      if (child.key === key) return child;
    }
  }
  return null;
}

function findMountId(key) {
  return configFolderMountIdMap.value[key] || key.split("::")[1];
}

// ── 工具 tab ──────────────────────────────────────
async function loadConfigAgentTools() {
  const agent = configDrawerAgent.value;
  if (!agent?.id) return;
  configToolsLoading.value = true;
  try {
    const res = await fetchAgentTools();
    const allTools = res?.data ?? [];
    const runtimeNames = new Set(agent.runtime_tool_names || []);
    configAgentTools.value = allTools.filter((t) => runtimeNames.has(t.tool_id));
  } catch (e) {
    configAgentTools.value = [];
  } finally {
    configToolsLoading.value = false;
  }
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

const STATUS_POLL_MS = 15_000;
let statusPollTimer = null;
let statusPollVisible = true;

function startStatusPoll() {
  if (statusPollTimer) return;
  statusPollTimer = window.setInterval(() => {
    if (!statusPollVisible) return;
    void loadAgents({ background: true });
  }, STATUS_POLL_MS);
}

function stopStatusPoll() {
  if (statusPollTimer) {
    window.clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
}

function onVisibilityChange() {
  statusPollVisible = !document.hidden;
  if (statusPollVisible) {
    void loadAgents({ background: true });
  }
}

onMounted(async () => {
  if (hydrated.value) {
    void reload({ background: !isAgentsTabCacheFresh() });
  } else {
    await reload();
  }
  document.addEventListener("visibilitychange", onVisibilityChange);
  startStatusPoll();
});

onUnmounted(() => {
  stopStatusPoll();
  document.removeEventListener("visibilitychange", onVisibilityChange);
});

defineExpose({
  reload,
  toggleSearch,
  openExternalAgentModal,
  loading: refreshing,
});
</script>

<template>
  <div class="agents-tab">
    <div class="agents-tab__header-actions">
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
  <!-- 首屏骨架：6 张卡片占位，避免白屏 -->
  <div v-if="initialLoading" class="agent-card-grid agent-card-grid--skeleton">
    <div v-for="n in 6" :key="n" class="agent-card agent-card--skeleton">
      <div class="agent-card__progress" aria-hidden="true" />
      <div class="agent-card__head">
        <div class="agent-card__identity">
          <div class="skeleton-line skeleton-line--title" />
        </div>
        <div class="skeleton-line skeleton-line--badge" />
      </div>
      <div class="agent-card__desc-wrap">
        <div class="skeleton-line skeleton-line--desc" />
        <div class="skeleton-line skeleton-line--desc skeleton-line--short" />
      </div>
      <div class="agent-card__bottom">
        <div class="skeleton-line skeleton-line--meta" />
      </div>
    </div>
  </div>
  <div v-else-if="showAgentEmpty" class="agent-card-grid agent-card-grid--empty">
    <NText depth="3">{{ t("admin.agentSkills.noSearchResults") }}</NText>
  </div>
  <div v-else class="agent-card-grid">
    <NCard
      v-for="agent in filteredAgents"
      :key="agent.id"
      size="small"
      class="agent-card"
      :class="{ 'agent-card--disabled': !agent.enabled, 'agent-card--clickable': false }"
    >
      <div
        class="agent-card__progress"
        :class="{ 'agent-card__progress--active': agent.status === 'running' }"
        aria-hidden="true"
      />
      <div class="agent-card__head">
        <div class="agent-card__identity">
          <div class="agent-card-title">{{ formatAgentDisplayName(agent.title) }}</div>
          <span
            v-if="agent.status === 'running'"
            class="agent-card__run-badge"
          >
            {{ agentStatusLabel(agent) }}
          </span>
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
          <span class="agent-card__meta-sep" aria-hidden="true">·</span>
          <span class="agent-card__meta-item">
            {{ t("admin.agentSkills.foldersCount", { count: agent.mount_count ?? 0 }) }}
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
      v-for="agent in filteredExternalAgents"
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

  <Teleport to="body">
    <NDrawer v-model:show="configDrawerOpen" :width="640" placement="right">
      <NDrawerContent
        :title="t('admin.agentSkills.configDrawerTitle', { name: configDrawerDisplayName() })"
        closable
        :native-scrollbar="false"
        body-content-style="overflow-x: hidden;"
      >
        <div class="agent-config-drawer">
          <!-- 通用设置（始终显示在 tab 上方） -->
          <section class="agent-config-drawer__section" style="margin-bottom: 16px;">
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
                  :disabled="configDrawerAgent?.id !== 'orchestrator' && !configEnabled"
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

          <!-- Tab 配置：AGENT.md / STYLE.md / 文件夹 / 技能 / 工具（仅内置智能体） -->
          <template v-if="configDrawerKind === 'builtin'">
            <n-tabs v-model:value="configActiveTab" type="line" size="small" style="margin-top: 4px;">
              <n-tab-pane name="agent-md" tab="AGENT.md">
                <div v-if="configAgentMdLoading" style="padding: 20px 0;">
                  {{ t("common.loading") }}
                </div>
                <template v-else>
                  <NInput
                    v-model:value="configAgentMdContent"
                    type="textarea"
                    :rows="16"
                    :placeholder="t('admin.agentSkills.agentConfigHint')"
                    @update:value="configAgentMdDirty = true"
                  />
                  <NSpace style="margin-top: 10px">
                    <NButton
                      type="primary"
                      size="small"
                      :loading="configAgentMdSaving"
                      :disabled="!configAgentMdDirty"
                      @click="saveConfigAgentMd"
                    >
                      {{ t("common.save") }}
                    </NButton>
                  </NSpace>
                </template>
              </n-tab-pane>
              <n-tab-pane name="style-md" tab="STYLE.md">
                <div v-if="configStyleMdLoading" style="padding: 20px 0;">
                  {{ t("common.loading") }}
                </div>
                <template v-else>
                  <NInput
                    v-model:value="configStyleMdContent"
                    type="textarea"
                    :rows="16"
                    :placeholder="t('admin.agentSkills.stylePlaceholder')"
                    @update:value="configStyleMdDirty = true"
                  />
                  <NSpace style="margin-top: 10px">
                    <NButton
                      type="primary"
                      size="small"
                      :loading="configStyleMdSaving"
                      :disabled="!configStyleMdDirty"
                      @click="saveConfigStyleMd"
                    >
                      {{ t("common.save") }}
                    </NButton>
                  </NSpace>
                </template>
              </n-tab-pane>
              <n-tab-pane name="files" :tab="t('admin.agentSkills.tabFiles')">
                <div class="agent-config-drawer__tab-content">
                  <NSpin :show="configFolderTreeLoading">
                    <template v-if="!configFolderTreeLoading">
                      <div v-if="!folderTreeData.length" style="padding: 20px 0;">
                        <NEmpty :description="t('admin.agentSkills.knowledgeMountsEmpty')" />
                      </div>
                      <template v-else>
                        <NText depth="3" class="agent-config-drawer__section-hint">
                          {{ t("admin.agentSkills.knowledgeMountsHint") }}
                        </NText>
                        <NScrollbar style="max-height: 400px;">
                          <div class="agent-config-drawer__folder-tree">
                            <div
                              v-for="lib in folderTreeData"
                              :key="lib.key"
                              class="folder-tree__library"
                            >
                              <div class="folder-tree__library-title">
                                <NText depth="2" class="folder-tree__library-label">{{ lib.label }}</NText>
                              </div>
                              <div class="folder-tree__items">
                                <div
                                  v-for="child in lib.children"
                                  :key="child.key"
                                  class="folder-tree__item"
                                  :class="{ 'folder-tree__item--toggling': configFolderToggling.has(child.key) }"
                                >
                                  <NCheckbox
                                    :checked="folderCheckedKeys.includes(child.key)"
                                    :disabled="configFolderToggling.has(child.key)"
                                    @update:checked="
                                      (v) => {
                                        const keys = v
                                          ? [...folderCheckedKeys, child.key]
                                          : folderCheckedKeys.filter((k) => k !== child.key);
                                        handleFolderCheck(keys);
                                      }
                                    "
                                  >
                                    <div class="folder-tree__item-body">
                                      <span class="folder-tree__item-label">{{ child.label }}</span>
                                      <span class="folder-tree__item-meta">
                                        {{ child._folder.document_count }} 文档
                                      </span>
                                    </div>
                                  </NCheckbox>
                                </div>
                              </div>
                            </div>
                          </div>
                        </NScrollbar>
                      </template>
                    </template>
                  </NSpin>
                </div>
              </n-tab-pane>
              <n-tab-pane name="skills" :tab="t('admin.agentSkills.tabSkills')">
                <div class="agent-config-drawer__tab-content">
                  <template v-if="configDrawerAgent?.skills_configurable">
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
                  </template>
                  <NText v-else depth="3">
                    该智能体不支持技能配置
                  </NText>
                </div>
              </n-tab-pane>
              <n-tab-pane name="tools" :tab="t('admin.agentSkills.tabTools')">
                <div class="agent-config-drawer__tab-content">
                  <NSpin :show="configToolsLoading">
                    <template v-if="!configToolsLoading">
                      <div v-if="!configAgentTools.length" style="padding: 20px 0;">
                        <NEmpty :description="t('admin.agentSkills.noToolsAvailable')" />
                      </div>
                      <div v-else class="agent-config-drawer__tools-list">
                        <NText depth="3" class="agent-config-drawer__section-hint">
                          {{ t("admin.agentSkills.agentToolsHint", { count: configAgentTools.length }) }}
                        </NText>
                        <div
                          v-for="tool in configAgentTools"
                          :key="tool.tool_id"
                          class="agent-tool-item"
                        >
                          <div class="agent-tool-item__head">
                            <span class="agent-tool-item__name">{{ tool.tool_id }}</span>
                            <NTag size="tiny" :bordered="false">{{ tool.tool_type }}</NTag>
                            <NTag size="tiny" :bordered="false">
                              {{ t(`admin.agentSkills.toolCategory.${tool.category}`, tool.category) }}
                            </NTag>
                          </div>
                          <div v-if="tool.description" class="agent-tool-item__desc">
                            {{ tool.description }}
                          </div>
                        </div>
                      </div>
                    </template>
                  </NSpin>
                </div>
              </n-tab-pane>
            </n-tabs>
          </template>
        </div>
        <template #footer>
          <NSpace justify="end" :size="10">
            <NButton @click="configDrawerOpen = false">{{ t("common.cancel") }}</NButton>
            <NButton
              type="primary"
              :loading="configSaving"
              :disabled="configDrawerKind === 'external' && configDrawerAgent?.source === 'config'"
              @click="saveAgentConfig"
            >
              {{ t("common.save") }}
            </NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>
  </Teleport>

  <AdminFormModal
    v-model:show="externalAgentModalOpen"
    :title="t('admin.agentSkills.connectExternalAgent')"
    :width="768"
  >
    <NText depth="3" class="external-agent-modal__hint">
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
    </NForm>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="externalAgentModalOpen = false">{{ t("common.cancel") }}</NButton>
        <NButton type="primary" :loading="externalAgentSaving" @click="submitExternalAgent">
          {{ t("common.save") }}
        </NButton>
      </NSpace>
    </template>
  </AdminFormModal>
</template>

<style scoped>
.agents-tab-hint {
  flex: 1;
  min-width: 0;
  margin-bottom: 0;
}

.agents-tab-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.external-agent-modal__hint {
  display: block;
  margin-bottom: 19px;
}

.agents-tab__header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin-bottom: 12px;
}

/* ── 配置抽屉 tab 内容容器（防止左右滑动） ── */
.agent-config-drawer__tab-content {
  overflow-x: hidden;
}

/* ── 文件夹树 ── */
.agent-config-drawer__folder-tree {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.folder-tree__library-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  padding: 4px 0;
  border-bottom: 1px solid var(--platform-border-soft, #e8e8e8);
}

.folder-tree__library-label {
  font-weight: 600;
  font-size: var(--platform-font-size-sm, 13px);
}

.folder-tree__items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 8px;
}

.folder-tree__item {
  display: flex;
  align-items: center;
  padding: 3px 4px;
  border-radius: 4px;
  transition: background 0.15s;
}

.folder-tree__item:hover {
  background: var(--platform-hover-bg, rgba(0,0,0,0.03));
}

.folder-tree__item--toggling {
  opacity: 0.6;
  pointer-events: none;
}

.folder-tree__item-body {
  display: flex;
  align-items: center;
  gap: 8px;
}

.folder-tree__item-label {
  font-size: var(--platform-font-size-sm, 13px);
  color: var(--platform-text, #333);
}

.folder-tree__item-meta {
  font-size: var(--platform-font-size-xs, 11px);
  color: var(--platform-text-tertiary, #999);
}

/* ── 工具列表 ── */
.agent-config-drawer__tools-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.agent-tool-item {
  border: 1px solid var(--platform-border, #e0e0e0);
  border-radius: var(--platform-card-radius, 6px);
  background: #fafafa;
  padding: 8px 10px;
}

.agent-tool-item__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.agent-tool-item__name {
  font-size: var(--platform-font-size-sm, 13px);
  font-weight: 500;
  color: var(--platform-text, #333);
  font-family: var(--font-mono, "SF Mono", "Fira Code", monospace);
}

.agent-tool-item__desc {
  margin-top: 4px;
  font-size: var(--platform-font-size-sm, 13px);
  color: var(--platform-text-tertiary, #999);
  line-height: 1.4;
}
</style>
