<script setup>
import { onMounted, ref } from "vue";
import { NAlert, NButton, NDataTable, NForm, NFormItem, NInput, NModal, NSpace, NText } from "naive-ui";
import { TrashOutline } from "@vicons/ionicons5";
import AdminFormModal from "../AdminFormModal.vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { createAipKey, deleteAipKey, fetchAipKeys } from "../../api/aipKeys";
import { renderIconActionGroup } from "../../utils/tableIconActions.js";

const ui = usePlatformUi();
const { t } = useI18n();

const loading = ref(false);
const creating = ref(false);
const rows = ref([]);
const showCreate = ref(false);
const purpose = ref("");
const createdSecret = ref("");
const showSecretModal = ref(false);

const columns = [
  {
    title: () => t("admin.agentSkills.aipKeys.colPrefix"),
    key: "key_prefix",
    width: 192,
  },
  {
    title: () => t("admin.agentSkills.aipKeys.colPurpose"),
    key: "purpose",
    ellipsis: { tooltip: true },
  },
  {
    title: () => t("admin.agentSkills.aipKeys.colCreator"),
    key: "created_by_name",
    width: 144,
  },
  {
    title: () => t("admin.agentSkills.aipKeys.colCreatedAt"),
    key: "created_at",
    width: 216,
    render: (row) =>
      row.created_at ? String(row.created_at).replace("T", " ").slice(0, 19) : "",
  },
  {
    title: () => t("common.actions"),
    key: "actions",
    width: 106,
    render: (row) =>
      renderIconActionGroup([
        {
          label: t("common.delete"),
          icon: TrashOutline,
          type: "error",
          onClick: () => onDelete(row),
        },
      ]),
  },
];

async function load() {
  loading.value = true;
  try {
    const data = await fetchAipKeys();
    rows.value = Array.isArray(data) ? data : [];
  } catch (e) {
    ui.error(e?.message || t("admin.agentSkills.aipKeys.loadFailed"));
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  purpose.value = "";
  showCreate.value = true;
}

async function submitCreate() {
  const text = purpose.value.trim();
  if (!text) {
    ui.warning(t("admin.agentSkills.aipKeys.purposeRequired"));
    return;
  }
  creating.value = true;
  try {
    const data = await createAipKey(text);
    showCreate.value = false;
    createdSecret.value = data?.secret_key || "";
    showSecretModal.value = Boolean(createdSecret.value);
    ui.success(t("admin.agentSkills.aipKeys.created"));
    await load();
  } catch (e) {
    ui.error(e?.message || t("admin.agentSkills.aipKeys.createFailed"));
  } finally {
    creating.value = false;
  }
}

async function onDelete(row) {
  await ui.confirmDelete({
    title: t("admin.agentSkills.aipKeys.deleteTitle"),
    content: t("admin.agentSkills.aipKeys.deleteConfirm", { prefix: row.key_prefix }),
    onPositive: async () => {
      await deleteAipKey(row.id);
      ui.success(t("admin.agentSkills.deleted"));
      await load();
    },
  });
}

async function copySecret() {
  if (!createdSecret.value) return;
  try {
    await navigator.clipboard.writeText(createdSecret.value);
    ui.success(t("admin.agentSkills.aipKeys.copied"));
  } catch {
    ui.warning(t("admin.agentSkills.aipKeys.copyManual"));
  }
}

onMounted(load);

defineExpose({ load, openCreate, loading });
</script>

<template>
  <div class="aip-keys-panel">
    <NText depth="3" class="aip-keys-panel__hint">
      {{ t("admin.agentSkills.aipKeys.hint") }}
    </NText>
    <NAlert type="info" :bordered="false" class="aip-keys-panel__usage">
      {{ t("admin.agentSkills.aipKeys.usageHint") }}
    </NAlert>

    <NDataTable
      :columns="columns"
      :data="rows"
      :loading="loading"
      :bordered="false"
      size="small"
    />

    <AdminFormModal v-model:show="showCreate" :title="t('admin.agentSkills.aipKeys.createTitle')">
      <NForm @submit.prevent="submitCreate">
        <NFormItem :label="t('admin.agentSkills.aipKeys.purposeLabel')" required>
          <NInput
            v-model:value="purpose"
            type="textarea"
            :placeholder="t('admin.agentSkills.aipKeys.purposePh')"
            :rows="3"
            maxlength="500"
            show-count
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showCreate = false">{{ t("common.cancel") }}</NButton>
          <NButton type="primary" :loading="creating" @click="submitCreate">
            {{ t("common.create") }}
          </NButton>
        </NSpace>
      </template>
    </AdminFormModal>

    <NModal
      v-model:show="showSecretModal"
      preset="card"
      :title="t('admin.agentSkills.aipKeys.secretTitle')"
      style="width: 672px"
      :mask-closable="false"
      :close-on-esc="false"
    >
      <NAlert type="warning" :bordered="false" style="margin-bottom: 14px">
        {{ t("admin.agentSkills.aipKeys.secretOnceHint") }}
      </NAlert>
      <NInput :value="createdSecret" readonly type="textarea" :rows="3" />
      <NSpace justify="end" style="margin-top: 14px">
        <NButton @click="copySecret">{{ t("admin.agentSkills.aipKeys.copy") }}</NButton>
        <NButton type="primary" @click="showSecretModal = false">
          {{ t("admin.agentSkills.aipKeys.secretSaved") }}
        </NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.aip-keys-panel {
  max-width: 1320px;
}
.aip-keys-panel__hint {
  display: block;
  margin-bottom: 14px;
}
.aip-keys-panel__usage {
  margin-bottom: 19px;
}
</style>
