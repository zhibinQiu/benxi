<script setup>
defineOptions({ name: "AutomationView" });
import { computed, h, onMounted, ref } from "vue";
import {
  NButton,
  NDataTable,
  NDatePicker,
  NEmpty,
  NForm,
  NFormItem,
  NGrid,
  NGi,
  NInput,
  NSelect,
  NSpace,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
} from "naive-ui";
import {
  AddOutline,
  CreateOutline,
  PlayOutline,
  RefreshOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import AdminFormModal from "../components/AdminFormModal.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import IconAction from "../components/IconAction.vue";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { isRouteAbortError } from "../api/http.js";
import {
  createAutomation,
  deleteAutomation,
  fetchAutomationOverview,
  runAutomationNow,
  updateAutomation,
} from "../api/automations.js";
import { renderIconActionGroup } from "../utils/tableIconActions.js";

const ui = usePlatformUi();
const { t } = useI18n();

const loading = ref(false);
const saving = ref(false);
const formOpen = ref(false);
const editingId = ref(null);
const activeTab = ref("configured");
const automations = ref([]);
const runs = ref([]);
/** 手动「立即执行」进行中的任务 id → true */
const runningById = ref({});
const form = ref({
  name: "",
  prompt: "",
  frequency: "daily",
  range: null,
  enabled: true,
});

const formTitle = computed(() =>
  editingId.value ? t("automation.edit") : t("automation.create")
);

const frequencyOptions = computed(() => [
  { label: t("automation.freqOnce"), value: "once" },
  { label: t("automation.freqHourly"), value: "hourly" },
  { label: t("automation.freqDaily"), value: "daily" },
  { label: t("automation.freqWeekly"), value: "weekly" },
  { label: t("automation.freqMonthly"), value: "monthly" },
]);

function formatTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function freqLabel(freq) {
  const map = {
    once: t("automation.freqOnce"),
    hourly: t("automation.freqHourly"),
    daily: t("automation.freqDaily"),
    weekly: t("automation.freqWeekly"),
    monthly: t("automation.freqMonthly"),
  };
  return map[freq] || freq;
}

function statusTag(status) {
  const type =
    status === "succeeded"
      ? "success"
      : status === "failed" || status === "cancelled"
        ? "error"
        : status === "running"
          ? "info"
          : "warning";
  const label =
    {
      succeeded: t("automation.statusSucceeded"),
      failed: t("automation.statusFailed"),
      running: t("automation.statusRunning"),
      pending: t("automation.statusPending"),
      cancelled: t("automation.statusCancelled"),
    }[status] || status;
  return h(NTag, { size: "small", type, bordered: false }, { default: () => label });
}

function resetForm() {
  editingId.value = null;
  form.value = {
    name: "",
    prompt: "",
    frequency: "daily",
    range: null,
    enabled: true,
  };
}

function toRangeValue(startsAt, endsAt) {
  if (!startsAt && !endsAt) return null;
  const start = startsAt ? new Date(startsAt).getTime() : null;
  const end = endsAt ? new Date(endsAt).getTime() : null;
  if (start == null || end == null || Number.isNaN(start) || Number.isNaN(end)) {
    return null;
  }
  return [start, end];
}

function openCreate() {
  resetForm();
  formOpen.value = true;
}

function openEdit(row) {
  editingId.value = row.id;
  form.value = {
    name: row.name || "",
    prompt: row.prompt || "",
    frequency: row.frequency || "daily",
    range: toRangeValue(row.starts_at, row.ends_at),
    enabled: !!row.enabled,
  };
  formOpen.value = true;
}

function closeForm() {
  formOpen.value = false;
  resetForm();
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchAutomationOverview();
    automations.value = Array.isArray(data?.automations) ? data.automations : [];
    runs.value = Array.isArray(data?.runs) ? data.runs : [];
  } catch (e) {
    if (isRouteAbortError(e) || e?.code === "ROUTE_ABORT") return;
    ui.error(e.message || t("automation.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function submitForm() {
  const name = form.value.name.trim();
  const prompt = form.value.prompt.trim();
  if (!name || !prompt) {
    ui.warning(t("automation.namePromptRequired"));
    return;
  }
  const range = form.value.range;
  const body = {
    name,
    prompt,
    frequency: form.value.frequency,
    enabled: form.value.enabled,
    starts_at: range?.[0] ? new Date(range[0]).toISOString() : null,
    ends_at: range?.[1] ? new Date(range[1]).toISOString() : null,
  };
  saving.value = true;
  try {
    if (editingId.value) {
      await updateAutomation(editingId.value, body);
      ui.success(t("automation.updateOk"));
    } else {
      await createAutomation(body);
      ui.success(t("automation.createOk"));
    }
    closeForm();
    await load();
    activeTab.value = "configured";
  } catch (e) {
    ui.error(
      e.message ||
        (editingId.value ? t("automation.updateFailed") : t("automation.createFailed"))
    );
  } finally {
    saving.value = false;
  }
}

async function toggleEnabled(row, enabled) {
  try {
    await updateAutomation(row.id, { enabled });
    await load();
  } catch (e) {
    ui.error(e.message || t("automation.updateFailed"));
  }
}

function onDelete(row) {
  ui.confirmDelete({
    title: t("automation.deleteTitle"),
    content: t("automation.deleteConfirm", { name: row.name }),
    onPositive: async () => {
      await deleteAutomation(row.id);
      ui.success(t("automation.deleteOk"));
      await load();
    },
  });
}

async function onRunNow(row) {
  const id = row.id;
  if (runningById.value[id]) return;
  runningById.value = { ...runningById.value, [id]: true };
  try {
    await runAutomationNow(id);
    ui.success(t("automation.runQueued"));
    await load();
  } catch (e) {
    if (isRouteAbortError(e) || e?.code === "ROUTE_ABORT") return;
    ui.error(e.message || t("automation.runFailed"));
  } finally {
    const next = { ...runningById.value };
    delete next[id];
    runningById.value = next;
  }
}

const automationColumns = computed(() => [
  { title: t("automation.colName"), key: "name", ellipsis: { tooltip: true } },
  {
    title: t("automation.colFrequency"),
    key: "frequency",
    width: 100,
    render: (row) => freqLabel(row.frequency),
  },
  {
    title: t("automation.colNextRun"),
    key: "next_run_at",
    width: 170,
    render: (row) => formatTime(row.next_run_at),
  },
  {
    title: t("automation.colLastRun"),
    key: "last_run_at",
    width: 170,
    render: (row) => formatTime(row.last_run_at),
  },
  {
    title: t("automation.colEnabled"),
    key: "enabled",
    width: 90,
    render: (row) =>
      h(NSwitch, {
        value: row.enabled,
        size: "small",
        onUpdateValue: (v) => toggleEnabled(row, v),
      }),
  },
  {
    title: t("common.actions"),
    key: "actions",
    width: 132,
    render: (row) => {
      const running = !!runningById.value[row.id];
      return renderIconActionGroup([
        {
          label: t("common.edit"),
          icon: CreateOutline,
          disabled: running,
          onClick: () => openEdit(row),
        },
        {
          label: running ? t("automation.statusRunning") : t("automation.runNow"),
          icon: running ? RefreshOutline : PlayOutline,
          type: "primary",
          loading: running,
          onClick: () => onRunNow(row),
        },
        {
          label: t("common.delete"),
          icon: TrashOutline,
          type: "error",
          disabled: running,
          onClick: () => onDelete(row),
        },
      ]);
    },
  },
]);

const runColumns = computed(() => [
  {
    title: t("automation.colName"),
    key: "automation_name",
    ellipsis: { tooltip: true },
  },
  {
    title: t("automation.colStatus"),
    key: "status",
    width: 100,
    render: (row) => statusTag(row.status),
  },
  {
    title: t("automation.colStarted"),
    key: "started_at",
    width: 170,
    render: (row) => formatTime(row.started_at),
  },
  {
    title: t("automation.colResult"),
    key: "result_summary",
    ellipsis: { tooltip: true },
    render: (row) => row.result_summary || row.error || "—",
  },
]);

onMounted(load);
</script>

<template>
  <FeatureSubsystemShell :show-intro="false" fill>
    <div class="automation-view">
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane name="configured" :tab="t('automation.tabConfigured')">
          <div class="automation-card__header">
            <div class="automation-card__title-row">
              <div class="automation-card__hint">
                {{ t("automation.toolbarHint.configured") }}
              </div>
              <div class="automation-card__actions">
                <IconAction
                  :label="t('automation.create')"
                  :icon="AddOutline"
                  @click="openCreate"
                />
                <IconAction
                  :label="t('common.refresh')"
                  :icon="RefreshOutline"
                  :loading="loading"
                  @click="load"
                />
              </div>
            </div>
          </div>
          <div class="automation-card">
            <div class="admin-list-table">
              <n-data-table
                v-if="automations.length"
                :columns="automationColumns"
                :data="automations"
                :bordered="false"
                size="small"
                :loading="loading"
              />
              <n-empty
                v-else
                :description="t('automation.emptyConfigured')"
                style="padding: 38px 0"
              />
            </div>
          </div>
        </n-tab-pane>

        <n-tab-pane name="runs" :tab="t('automation.tabRuns')">
          <div class="automation-card__header">
            <div class="automation-card__title-row">
              <div class="automation-card__hint">
                {{ t("automation.toolbarHint.runs") }}
              </div>
              <div class="automation-card__actions">
                <IconAction
                  :label="t('common.refresh')"
                  :icon="RefreshOutline"
                  :loading="loading"
                  @click="load"
                />
              </div>
            </div>
          </div>
          <div class="automation-card">
            <div class="admin-list-table">
              <n-data-table
                v-if="runs.length"
                :columns="runColumns"
                :data="runs"
                :bordered="false"
                size="small"
                :loading="loading"
              />
              <n-empty
                v-else
                :description="t('automation.emptyRuns')"
                style="padding: 38px 0"
              />
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>

      <AdminFormModal
        v-model:show="formOpen"
        :title="formTitle"
        :width="720"
        @update:show="(v) => { if (!v) resetForm(); }"
      >
        <n-form label-placement="top" class="automation-create-form">
          <n-grid :cols="24" :x-gap="12" :y-gap="0">
            <n-gi :span="16">
              <n-form-item :label="t('automation.fieldName')" required>
                <n-input
                  v-model:value="form.name"
                  :placeholder="t('automation.namePlaceholder')"
                />
              </n-form-item>
            </n-gi>
            <n-gi :span="8">
              <n-form-item :label="t('automation.fieldFrequency')">
                <n-select
                  v-model:value="form.frequency"
                  :options="frequencyOptions"
                />
              </n-form-item>
            </n-gi>
            <n-gi :span="24">
              <n-form-item :label="t('automation.fieldPrompt')" required>
                <n-input
                  v-model:value="form.prompt"
                  type="textarea"
                  :rows="4"
                  :placeholder="t('automation.promptPlaceholder')"
                />
              </n-form-item>
            </n-gi>
            <n-gi :span="16">
              <n-form-item :label="t('automation.fieldRange')">
                <n-date-picker
                  v-model:value="form.range"
                  type="datetimerange"
                  clearable
                  style="width: 100%"
                />
              </n-form-item>
            </n-gi>
            <n-gi :span="8">
              <n-form-item :label="t('automation.fieldEnabled')">
                <n-switch v-model:value="form.enabled" />
              </n-form-item>
            </n-gi>
          </n-grid>
        </n-form>
        <template #footer>
          <n-space justify="end">
            <n-button :disabled="saving" @click="closeForm">
              {{ t("common.cancel") }}
            </n-button>
            <n-button type="primary" :loading="saving" @click="submitForm">
              {{ t("common.save") }}
            </n-button>
          </n-space>
        </template>
      </AdminFormModal>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.automation-view {
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
}

.automation-view :deep(.n-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.automation-view :deep(.n-tabs-nav) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--platform-bg);
}

.automation-view :deep(.n-tabs-tab--active) {
  color: var(--platform-accent) !important;
}

.automation-view :deep(.n-tabs-tab):hover {
  color: var(--platform-accent) !important;
}

.automation-view :deep(.n-tabs-bar) {
  display: none;
}

.automation-view :deep(.n-tabs .n-tabs-tab-panes) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.automation-view :deep(.n-tab-pane) {
  height: auto;
  min-height: 100%;
}

.automation-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.automation-card__header {
  margin: 0 0 8px;
  padding-left: 16px;
}

.automation-card__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.automation-card__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

.automation-card__actions :deep(.icon-action) {
  width: 22px !important;
  height: 22px !important;
}

.automation-card__actions :deep(.n-icon),
.automation-card__actions :deep(.n-icon svg) {
  font-size: 13px !important;
  width: 13px;
  height: 13px;
}

.automation-card__hint {
  margin: 0;
  min-width: 0;
  flex: 1;
  font-size: var(--platform-font-size-sm);
  font-weight: 400;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}

.automation-card :deep(.n-data-table-th),
.automation-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.automation-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-light);
  vertical-align: middle;
}

.automation-create-form :deep(.n-form-item) {
  margin-bottom: 8px;
}
</style>
