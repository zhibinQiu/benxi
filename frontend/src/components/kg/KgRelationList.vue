<template>
  <div class="kg-relation-wrapper">
    <n-button class="platform-btn--create" @click="openCreate">
      <template #icon><n-icon><AddOutline /></n-icon></template>
      新建关系
    </n-button>

    <div class="kg-relation-card">
      <div class="admin-list-table">
        <n-data-table
          :columns="columns"
          :data="relations"
          :loading="loading"
          :bordered="false"
          :row-key="(row) => row.id"
          :max-height="600"
          pagination
        />
      </div>
    </div>

    <n-modal v-model:show="showModal" :title="isEdit ? '编辑关系' : '新建关系'"
      preset="card" style="width: 560px" :mask-closable="false">
      <n-form :model="form" label-placement="left" label-width="100px">
        <n-form-item label="关系类型" required>
          <n-select v-model:value="form.type_code" :options="relTypeOptions" :disabled="isEdit" filterable />
        </n-form-item>
        <n-form-item label="起点实体" required>
          <n-select v-model:value="form.from_entity_id" :options="entityOptions" :disabled="isEdit" filterable />
        </n-form-item>
        <n-form-item label="终点实体" required>
          <n-select v-model:value="form.to_entity_id" :options="entityOptions" :disabled="isEdit" filterable />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" @click="handleSave" :loading="saving">保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { h, ref, reactive, computed } from "vue";
import { useMessage, useDialog } from "naive-ui";
import { AddOutline, TrashOutline, CreateOutline } from "@vicons/ionicons5";
import { createKgRelation, deleteKgRelation, updateKgRelation } from "../../api/kg.js";

const props = defineProps({
  relations: { type: Array, default: () => [] },
  relationTypes: { type: Array, default: () => [] },
  entities: { type: Array, default: () => [] },
  loading: Boolean,
});

const emit = defineEmits(["refresh"]);

const message = useMessage();
const dialog = useDialog();

const showModal = ref(false);
const isEdit = ref(false);
const editingId = ref("");
const saving = ref(false);
const form = reactive({
  type_code: "",
  from_entity_id: "",
  to_entity_id: "",
  description: "",
});

const relTypeOptions = computed(() =>
  props.relationTypes.map((rt) => ({ label: `${rt.label} (${rt.code})`, value: rt.code }))
);

const entityOptions = computed(() =>
  props.entities.map((e) => ({
    label: `${e.name} (${e.type_label || e.type_code})`,
    value: e.id,
  }))
);

function openCreate() {
  isEdit.value = false;
  editingId.value = "";
  form.type_code = props.relationTypes.length > 0 ? props.relationTypes[0].code : "";
  form.from_entity_id = "";
  form.to_entity_id = "";
  form.description = "";
  showModal.value = true;
}

function openEdit(row) {
  isEdit.value = true;
  editingId.value = row.id;
  form.type_code = row.type_code;
  form.from_entity_id = row.from_entity_id;
  form.to_entity_id = row.to_entity_id;
  form.description = row.description || "";
  showModal.value = true;
}

function doDelete(row) {
  dialog.warning({
    title: "确认删除",
    content: `删除关系？`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await deleteKgRelation(row.id);
        message.success("已删除");
        emit("refresh");
      } catch (err) {
        message.error("删除失败: " + (err.message || ""));
      }
    },
  });
}

async function handleSave() {
  if (!form.type_code || !form.from_entity_id || !form.to_entity_id) {
    message.warning("请填写完整信息");
    return;
  }
  if (form.from_entity_id === form.to_entity_id) {
    message.warning("起点和终点不能相同");
    return;
  }
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateKgRelation(editingId.value, {
        description: form.description || "",
      });
      message.success("已更新");
    } else {
      await createKgRelation({
        type_code: form.type_code,
        from_entity_id: form.from_entity_id,
        to_entity_id: form.to_entity_id,
        description: form.description,
      });
      message.success("已创建");
    }
    showModal.value = false;
    emit("refresh");
  } catch (err) {
    message.error(isEdit.value ? "更新失败: " + (err.message || "") : "创建失败: " + (err.message || ""));
  } finally {
    saving.value = false;
  }
}

const columns = [
  {
    title: "关系类型",
    key: "type_label",
    minWidth: 200,
    ellipsis: { tooltip: true },
    render(row) {
      return h("div", { style: "display:flex;flex-direction:column;gap:2px;padding:2px 0;" }, [
        h("div", { style: "font-size:var(--platform-font-size-sm);font-weight:500;color:var(--platform-text);line-height:1.4;" }, row.type_label || row.type_code),
        h("div", { style: "font-size:var(--platform-font-size-sm);color:var(--platform-text-tertiary);line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, row.description || ""),
      ]);
    },
  },
  { title: "起点实体", key: "from_entity_name", width: 150 },
  { title: "终点实体", key: "to_entity_name", width: 150 },
  { title: "推理", key: "inferred", width: 60 },
  {
    title: "操作",
    key: "actions",
    width: 120,
    render(row) {
      return [
        h("n-button", { size: "small", quaternary: true, onClick: () => openEdit(row) },
          { icon: () => h(CreateOutline) }),
        h("n-button", { size: "small", quaternary: true, type: "error", onClick: () => doDelete(row) },
          { icon: () => h(TrashOutline) }),
      ];
    },
  },
];
</script>

<style scoped>
.kg-relation-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kg-relation-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.kg-relation-card :deep(.n-data-table-th),
.kg-relation-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.kg-relation-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.kg-relation-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}
</style>
