<script setup>
import { computed, h, onMounted, ref } from "vue";
import {
  NButton,
  NDataTable,
  NEmpty,
  NIcon,
  NInput,
  NPagination,
  NSelect,
  NSpace,
  NSpin,
  NTag,
} from "naive-ui";
import { RefreshOutline } from "@vicons/ionicons5";
import AdminFormModal from "../components/AdminFormModal.vue";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  createIssueReport,
  deleteIssueReport,
  fetchIssueReports,
  updateIssueReport,
} from "../api/issueReports.js";
import { useClientListPagination } from "../composables/useClientListPagination.js";

const ui = usePlatformUi();
const { t } = useI18n();
const { isSystemAdmin } = useAuth();

const loading = ref(false);
const saving = ref(false);
const items = ref([]);
const {
  page,
  pageSize,
  total,
  pagedItems,
  onPageChange,
  resetPage,
} = useClientListPagination(items);
const displayInfo = computed(() => {
  if (!total.value) return "";
  const start = (page.value - 1) * pageSize.value + 1;
  const end = Math.min(page.value * pageSize.value, total.value);
  return `${total.value}条数据中的 ${start}-${end} 条`;
});
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
    resetPage();
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
      minWidth: 336,
      ellipsis: { tooltip: true },
    },
    {
      title: t("issueReports.colReporter"),
      key: "reporter_name",
      width: 144,
      ellipsis: { tooltip: true },
    },
    {
      title: t("issueReports.colStatus"),
      key: "status",
      width: 156,
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
      width: 211,
      render: (row) => formatTime(row.created_at),
    },
  ];
  if (items.value.some((row) => row.status === "fixed")) {
    cols.push({
      title: t("issueReports.colFixedAt"),
      key: "fixed_at",
      width: 211,
      render: (row) =>
        row.status === "fixed" ? formatTime(row.fixed_at) : t("issueReports.emDash"),
    });
  }
  if (isSystemAdmin.value) {
    cols.push({
      title: t("issueReports.colActions"),
      key: "actions",
      width: 96,
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
    <div class="issue-reports-card">
      <div class="issue-reports-card__toolbar">
        <div class="issue-reports-card__toolbar-left">
          <n-button
            quaternary
            circle
            size="small"
            class="tool-icon-btn"
            :class="{ 'tool-icon-btn--spinning': loading }"
            :aria-label="t('common.refresh')"
            :disabled="loading"
            @click="load"
          >
            <template #icon>
              <n-icon :size="14"><RefreshOutline /></n-icon>
            </template>
          </n-button>
        </div>
        <div class="issue-reports-card__toolbar-right">
          <n-select
            v-model:value="statusFilter"
            :options="statusOptions"
            size="small"
            style="width: 144px"
            @update:value="load"
          />
          <n-button type="primary" size="small" @click="showCreateModal = true">
            {{ t("issueReports.register") }}
          </n-button>
        </div>
      </div>
      <n-spin :show="loading" local>
        <div class="admin-list-table">
          <n-data-table
            v-if="items.length"
            :columns="columns"
            :data="pagedItems"
            :bordered="false"
            size="small"
            :scroll-x="900"
            :pagination="false"
          />
          <n-empty v-else :description="t('issueReports.empty')" style="padding: 38px 0" />
        </div>
        <div v-if="items.length" class="issue-reports-table-footer">
          <span class="issue-reports-table-footer__info">{{ displayInfo }}</span>
          <div class="issue-reports-table-footer__pages">
            <NPagination
              :page="page"
              :page-size="pageSize"
              :item-count="total"
              :page-slot="7"
              @update:page="onPageChange"
            />
          </div>
        </div>
      </n-spin>
    </div>

    <AdminFormModal
      v-model:show="showCreateModal"
      :title="t('issueReports.modalTitle')"
      width="min(672px, calc(100vw - 38px))"
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
    </AdminFormModal>
  </div>
</template>

<style scoped>
.issue-reports-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.issue-reports-card__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0 8px;
}

.issue-reports-card__toolbar-left {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.issue-reports-card__toolbar-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 标准工具栏 24px 圆形刷新按钮 */
.issue-reports-card .tool-icon-btn {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  min-width: 0;
  min-height: 0;
  padding: 0;
  border: none;
  box-shadow: none;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  --n-height: 24px;
  --n-icon-size: 14px;
  background: color-mix(in srgb, var(--platform-bg-tertiary) 52%, transparent);
  color: var(--platform-text-tertiary);
}

.issue-reports-card .tool-icon-btn:hover {
  color: var(--platform-accent);
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
}

.issue-reports-card .tool-icon-btn--spinning :deep(.n-icon) {
  animation: tool-spin 0.6s linear infinite;
}

@keyframes tool-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.issue-reports-card :deep(.n-data-table-th),
.issue-reports-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.issue-reports-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.issue-reports-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}

.issue-reports-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-top: 1px solid var(--platform-border-strong);
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
}

.issue-reports-table-footer__pages :deep(.n-pagination) {
  justify-content: flex-end;
}

.issue-reports-table-footer__pages :deep(.n-pagination-item) {
  font-size: var(--platform-font-size-sm);
}
</style>
