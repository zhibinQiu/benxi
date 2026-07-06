<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  NButton,
  NCard,
  NCheckbox,
  NCheckboxGroup,
  NDivider,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NSpace,
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
  fetchAgentProfile,
  fetchAgentProfileFile,
  fetchAgentProfiles,
  fetchAgentSkillRegistry,
  patchAgentProfile,
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
const registryForPicker = ref([]);

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

const selectedSkillCount = computed(() => selectedSkillNames.value.length);

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
    persistCache();
  } catch (e) {
    ui.error(e.message || t("admin.agentSkills.saveFailed"));
  } finally {
    agentPreviewSaving.value = false;
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
  openExternalAgentModal,
  loading: refreshing,
});
</script>

<template>
  <NText depth="3" class="agents-tab-hint">
    {{ t("admin.agentSkills.agentsHint") }}
  </NText>
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
  <div v-else class="agent-card-grid">
    <NCard
      v-for="agent in agents"
      :key="agent.id"
      size="small"
      class="agent-card agent-card--clickable"
      :class="{ 'agent-card--disabled': !agent.enabled }"
      @click="openAgentDetail(agent)"
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

  <NDrawer v-model:show="agentDetailOpen" :width="864" placement="right">
    <NDrawerContent
      :title="t('admin.agentSkills.agentDetailTitle', { name: agentDetail?.title || '' })"
      closable
    >
      <div v-if="agentDetailLoading">{{ t("common.loading") }}</div>
      <template v-else-if="agentDetail">
        <NText depth="3">{{ agentDetail.description }}</NText>
        <NText depth="3" style="display: block; margin: 14px 0">
          {{ t("admin.agentSkills.agentConfigHint") }}
        </NText>
        <NSpace style="margin: 0 0 14px" :size="10" wrap>
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
            <NSpace style="margin-top: 10px">
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

  <NDrawer v-model:show="configDrawerOpen" :width="504" placement="right">
    <NDrawerContent
      :title="t('admin.agentSkills.configDrawerTitle', { name: configDrawerDisplayName() })"
      closable
      :native-scrollbar="false"
      body-content-style="padding: 19px 24px 14px; display: flex; flex-direction: column; gap: 0;"
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

        <template v-if="configDrawerKind === 'builtin' && configDrawerAgent?.skills_configurable">
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
.external-agent-modal__hint {
  display: block;
  margin-bottom: 19px;
}
</style>
