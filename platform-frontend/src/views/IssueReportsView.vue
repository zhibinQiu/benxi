<script setup>
import { computed, h, onMounted, ref } from "vue";
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NInput,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
} from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  createIssueReport,
  deleteIssueReport,
  fetchIssueReports,
  updateIssueReport,
} from "../api/issueReports.js";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";

const ui = usePlatformUi();
const { t } = useI18n();
const { isSystemAdmin } = useAuth();

const loading = ref(false);
const saving = ref(false);
const items = ref([]);
const statusFilter = ref("");
const showCreateModal = ref(false);
const newDescription = ref("");

const statusOptions = computed(() => [
  { label: t("issueReports.statusAll"), value: "" },
  { label: t("issueReports.statusOpen"), value: "open" },
  { label: t("issueReports.statusFixed"), value: "fixed" },
]);

const adminStatusOptions = computed(() => [
  { label: t("issueReports.statusOpen"), value: "open" },
  { label: t("issueReports.statusFixed"), value: "fixed" },
]);

function formatTime(iso) {
  if (!iso) return t("issueReports.emDash");
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusLabel(status) {
  return status === "fixed" ? t("issueReports.statusFixed") : t("issueReports.statusOpen");
}

function statusTagType(status) {
  return status === "fixed" ? "success" : "warning";
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchIssueReports(statusFilter.value || undefined);
    items.value = Array.isArray(data) ? data : [];
  } catch (e) {
    ui.error(e.message || t("issueReports.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function submitIssue() {
  const description = newDescription.value.trim();
  if (!description) {
    ui.warning(t("issueReports.descriptionRequired"));
    return;
  }
  saving.value = true;
  try {
    await createIssueReport({ description });
    showCreateModal.value = false;
    newDescription.value = "";
    ui.success(t("issueReports.submitted"));
    await load();
  } catch (e) {
    ui.error(e.message || t("issueReports.submitFailed"));
  } finally {
    saving.value = false;
  }
}

async function onStatusChange(row, status) {
  if (!isSystemAdmin.value || row.status === status) return;
  try {
    await updateIssueReport(row.id, { status });
    ui.success(
      status === "fixed" ? t("issueReports.markedFixed") : t("issueReports.markedOpen")
    );
    await load();
  } catch (e) {
    ui.error(e.message || t("issueReports.updateFailed"));
  }
}

function confirmDelete(row) {
  ui.confirmDelete({
    title: t("issueReports.confirmDeleteTitle"),
    content: t("issueReports.confirmDeleteContent"),
    onPositive: async () => {
      try {
        await deleteIssueReport(row.id);
        ui.success(t("issueReports.deleted"));
        await load();
      } catch (e) {
        ui.error(e.message || t("issueReports.deleteFailed"));
      }
    },
  });
}

const columns = computed(() => {
  const cols = [
    {
      title: t("issueReports.colDescription"),
      key: "description",
      minWidth: 280,
      ellipsis: { tooltip: true },
    },
    {
      title: t("issueReports.colReporter"),
      key: "reporter_name",
      width: 120,
      ellipsis: { tooltip: true },
    },
    {
      title: t("issueReports.colStatus"),
      key: "status",
      width: 130,
      render(row) {
        if (isSystemAdmin.value) {
          return h(NSelect, {
            size: "small",
            value: row.status,
            options: adminStatusOptions.value,
            consistentMenuWidth: false,
            onUpdateValue: (value) => onStatusChange(row, value),
          });
        }
        return h(
          NTag,
          { size: "small", type: statusTagType(row.status), bordered: false },
          { default: () => statusLabel(row.status) }
        );
      },
    },
    {
      title: t("issueReports.colCreatedAt"),
      key: "created_at",
      width: 176,
      render: (row) => formatTime(row.created_at),
    },
  ];
  if (items.value.some((row) => row.status === "fixed")) {
    cols.push({
      title: t("issueReports.colFixedAt"),
      key: "fixed_at",
      width: 176,
      render: (row) =>
        row.status === "fixed" ? formatTime(row.fixed_at) : t("issueReports.emDash"),
    });
  }
  if (isSystemAdmin.value) {
    cols.push({
      title: t("issueReports.colActions"),
      key: "actions",
      width: 80,
      render(row) {
        return h(
          NButton,
          {
            size: "small",
            quaternary: true,
            type: "error",
            onClick: () => confirmDelete(row),
          },
          { default: () => t("issueReports.delete") }
        );
      },
    });
  }
  return cols;
});

onMounted(load);
</script>

<template>
  <div class="issue-reports-page feature-page">
    <n-spin :show="loading">
      <n-card size="small">
        <template #header>
          <div class="issue-reports-page__header">
            <div>
              <n-text strong>{{ t("issueReports.title") }}</n-text>
              <n-text depth="3" class="issue-reports-page__hint">
                {{ t("issueReports.hint") }}
              </n-text>
            </div>
            <n-space :size="12" align="center">
              <ListRefreshButton :loading="loading" @click="load" />
              <n-select
                v-model:value="statusFilter"
                :options="statusOptions"
                size="small"
                style="width: 120px"
                @update:value="load"
              />
              <n-button type="primary" size="small" @click="showCreateModal = true">
                {{ t("issueReports.register") }}
              </n-button>
            </n-space>
          </div>
        </template>

        <n-data-table
          v-if="items.length"
          :columns="columns"
          :data="items"
          :bordered="false"
          size="small"
          :scroll-x="900"
          :pagination="{ pageSize: LIST_PAGE_SIZE }"
        />
        <n-empty v-else :description="t('issueReports.empty')" style="padding: 32px 0" />
      </n-card>
    </n-spin>

    <n-modal
      v-model:show="showCreateModal"
      preset="card"
      :title="t('issueReports.modalTitle')"
      :style="{ width: 'min(560px, calc(100vw - 32px))' }"
      :mask-closable="!saving"
    >
      <n-input
        v-model:value="newDescription"
        type="textarea"
        :placeholder="t('issueReports.descriptionPlaceholder')"
        :autosize="{ minRows: 5, maxRows: 12 }"
        maxlength="8000"
        show-count
      />
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="saving" @click="showCreateModal = false">
            {{ t("common.cancel") }}
          </n-button>
          <n-button type="primary" :loading="saving" @click="submitIssue">
            {{ t("issueReports.submit") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.issue-reports-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.issue-reports-page__hint {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.5;
}
</style>
