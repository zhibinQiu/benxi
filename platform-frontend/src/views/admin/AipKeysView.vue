<script setup>
import { h, onMounted, ref } from "vue";
import {
  NAlert,
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSpace,
  NText,
} from "naive-ui";
import { usePlatformUi } from "../../composables/usePlatformUi";
import ListRefreshButton from "../../components/ListRefreshButton.vue";
import { createAipKey, deleteAipKey, fetchAipKeys } from "../../api/aipKeys";

const ui = usePlatformUi();
const loading = ref(false);
const creating = ref(false);
const rows = ref([]);
const showCreate = ref(false);
const purpose = ref("");
const createdSecret = ref("");
const showSecretModal = ref(false);

const columns = [
  { title: "密钥前缀", key: "key_prefix", width: 160 },
  { title: "用途", key: "purpose", ellipsis: { tooltip: true } },
  { title: "创建人", key: "created_by_name", width: 120 },
  {
    title: "创建时间",
    key: "created_at",
    width: 180,
    render: (row) => (row.created_at ? String(row.created_at).replace("T", " ").slice(0, 19) : ""),
  },
  {
    title: "操作",
    key: "actions",
    width: 100,
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          type: "error",
          tertiary: true,
          onClick: () => onDelete(row),
        },
        { default: () => "删除" }
      ),
  },
];

async function load() {
  loading.value = true;
  try {
    const data = await fetchAipKeys();
    rows.value = Array.isArray(data) ? data : [];
  } catch (e) {
    ui.message.error(e?.message || "加载失败");
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
    ui.message.warning("请填写密钥用途");
    return;
  }
  creating.value = true;
  try {
    const data = await createAipKey(text);
    showCreate.value = false;
    createdSecret.value = data?.secret_key || "";
    showSecretModal.value = Boolean(createdSecret.value);
    ui.message.success("密钥已创建");
    await load();
  } catch (e) {
    ui.message.error(e?.message || "创建失败");
  } finally {
    creating.value = false;
  }
}

async function onDelete(row) {
  await ui.confirmDelete({
    title: "删除 AIP 密钥",
    content: `确定删除「${row.key_prefix}」？删除后使用该密钥的调用将立即失效。`,
    onPositive: async () => {
      await deleteAipKey(row.id);
      ui.message.success("已删除");
      await load();
    },
  });
}

async function copySecret() {
  if (!createdSecret.value) return;
  try {
    await navigator.clipboard.writeText(createdSecret.value);
    ui.message.success("已复制到剪贴板");
  } catch {
    ui.message.warning("请手动复制密钥");
  }
}

onMounted(load);
</script>

<template>
  <div class="aip-keys-view">
    <div class="aip-keys-view__toolbar">
      <NSpace align="center">
        <NText strong>AIP 身份密钥</NText>
        <NText depth="3">用于外部系统调用 /api/v1/aip/*（GB/Z 185.3）</NText>
      </NSpace>
      <NSpace>
        <ListRefreshButton :loading="loading" @click="load" />
        <NButton type="primary" @click="openCreate">新建密钥</NButton>
      </NSpace>
    </div>

    <NAlert type="info" :bordered="false" style="margin-bottom: 16px">
      调用时在请求头使用 <code>Authorization: Bearer sk-aip-…</code>，或在 interact 请求体中填写
      <code>auth_token</code>。密钥明文仅在创建时显示一次。
    </NAlert>

    <NDataTable
      :columns="columns"
      :data="rows"
      :loading="loading"
      :bordered="false"
      size="small"
    />

    <NModal
      v-model:show="showCreate"
      preset="card"
      title="新建 AIP 密钥"
      style="width: 520px"
      :mask-closable="false"
    >
      <NForm @submit.prevent="submitCreate">
        <NFormItem label="用途" required>
          <NInput
            v-model:value="purpose"
            type="textarea"
            placeholder="例如：ERP 系统调用检索研究智能体"
            :rows="3"
            maxlength="500"
            show-count
          />
        </NFormItem>
        <NSpace justify="end">
          <NButton @click="showCreate = false">取消</NButton>
          <NButton type="primary" :loading="creating" @click="submitCreate">创建</NButton>
        </NSpace>
      </NForm>
    </NModal>

    <NModal
      v-model:show="showSecretModal"
      preset="card"
      title="请妥善保存密钥"
      style="width: 560px"
      :mask-closable="false"
      :close-on-esc="false"
    >
      <NAlert type="warning" :bordered="false" style="margin-bottom: 12px">
        此密钥只显示一次，关闭后将无法再次查看完整内容。
      </NAlert>
      <NInput :value="createdSecret" readonly type="textarea" :rows="3" />
      <NSpace justify="end" style="margin-top: 12px">
        <NButton @click="copySecret">复制</NButton>
        <NButton type="primary" @click="showSecretModal = false">我已保存</NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.aip-keys-view {
  padding: 16px 20px;
  max-width: 1100px;
}
.aip-keys-view__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
</style>
