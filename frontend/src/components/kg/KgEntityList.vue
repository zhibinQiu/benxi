<template>
  <div class="kg-entity-wrapper">
    <n-button class="platform-btn--create" @click="openCreate">
      <template #icon><n-icon><AddOutline /></n-icon></template>
      新建实体
    </n-button>

    <div class="kg-entity-card">
      <div class="admin-list-table">
        <n-data-table
          :columns="columns"
          :data="entities"
          :loading="loading"
          :bordered="false"
          :row-key="(row) => row.id"
          :max-height="600"
          pagination
        />
      </div>
    </div>

    <n-modal v-model:show="showModal" :title="isEdit ? '编辑实体' : '新建实体'"
      preset="card" style="width: 560px" :mask-closable="false">
      <n-form :model="form" label-placement="left" label-width="100px">
        <n-form-item label="实体类型" required>
          <n-select v-model:value="form.type_code" :options="typeOptions"
            :disabled="isEdit" filterable />
        </n-form-item>
        <n-form-item label="名称" required>
          <n-input v-model:value="form.name" placeholder="实体名称" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" type="textarea" :rows="2" />
        </n-form-item>
        <n-form-item v-if="!isEdit" label="来源">
          <n-select v-model:value="form.source_type" :options="sourceOptions" />
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
import { AddOutline, TrashOutline, CreateOutline, EyeOutline } from "@vicons/ionicons5";
import { createKgEntity, updateKgEntity, deleteKgEntity } from "../../api/kg.js";

const props = defineProps({
  entities: { type: Array, default: () => [] },
  entityTypes: { type: Array, default: () => [] },
  loading: Boolean,
});

const emit = defineEmits(["refresh", "focusEntity"]);

const message = useMessage();
const dialog = useDialog();

const showModal = ref(false);
const isEdit = ref(false);
const saving = ref(false);
const form = reactive({
  type_code: "",
  name: "",
  description: "",
  source_type: "manual",
});
const editingId = ref("");

const typeOptions = computed(() =>
  props.entityTypes.map((et) => ({ label: `${et.label} (${et.code})`, value: et.code }))
);

const sourceOptions = [
  { label: "手动创建", value: "manual" },
  { label: "LLM 抽取", value: "extraction" },
];

function openCreate() {
  isEdit.value = false;
  editingId.value = "";
  form.type_code = props.entityTypes.length > 0 ? props.entityTypes[0].code : "";
  form.name = "";
  form.description = "";
  form.source_type = "manual";
  showModal.value = true;
}

function openEdit(row) {
  isEdit.value = true;
  editingId.value = row.id;
  form.type_code = row.type_code;
  form.name = row.name;
  form.description = row.description || "";
  showModal.value = true;
}

function doDelete(row) {
  dialog.warning({
    title: "确认删除",
    content: `删除实体 "${row.name}"？相关关系也将被删除。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await deleteKgEntity(row.id);
        message.success("已删除");
        emit("refresh");
      } catch (err) {
        message.error("删除失败: " + (err.message || ""));
      }
    },
  });
}

function doFocus(row) {
  emit("focusEntity", row.id);
}

async function handleSave() {
  if (!form.type_code || !form.name) {
    message.warning("请选择类型并填写名称");
    return;
  }
  saving.value = true;
  try {
    if (isEdit.value) {
      await updateKgEntity(editingId.value, {
        name: form.name,
        description: form.description,
      });
      message.success("已更新");
    } else {
      await createKgEntity({
        type_code: form.type_code,
        name: form.name,
        description: form.description,
        source_type: form.source_type,
      });
      message.success("已创建");
    }
    showModal.value = false;
    emit("refresh");
  } catch (err) {
    message.error("保存失败: " + (err.message || ""));
  } finally {
    saving.value = false;
  }
}

const columns = [
  {
    title: "名称",
    key: "name",
    minWidth: 220,
    ellipsis: { tooltip: true },
    render(row) {
      return h("div", { style: "display:flex;flex-direction:column;gap:2px;padding:2px 0;" }, [
        h("div", { style: "font-size:var(--platform-font-size-sm);font-weight:500;color:var(--platform-text);line-height:1.4;" }, row.name),
        h("div", { style: "font-size:var(--platform-font-size-sm);color:var(--platform-text-tertiary);line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, row.description || ""),
      ]);
    },
  },
  {
    title: "类型",
    key: "type_code",
    width: 100,
    render(row) {
      return h("n-tag", { size: "small", color: { color: row.type_color, textColor: "#fff" } },
        { default: () => row.type_label || row.type_code });
    },
  },
  { title: "来源", key: "source_type", width: 80 },
  { title: "创建时间", key: "created_at", width: 160 },
  {
    title: "操作",
    key: "actions",
    width: 170,
    render(row) {
      return h("n-space", null, {
        default: () => [
          h("n-button", { size: "small", quaternary: true, onClick: () => doFocus(row) },
            { icon: () => h(EyeOutline) }),
          h("n-button", { size: "small", quaternary: true, onClick: () => openEdit(row) },
            { icon: () => h(CreateOutline) }),
          h("n-button", { size: "small", quaternary: true, type: "error", onClick: () => doDelete(row) },
            { icon: () => h(TrashOutline) }),
        ],
      });
    },
  },
];
</script>

<style scoped>
.kg-entity-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kg-entity-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 12px 16px;
  padding-top: 0;
}

.kg-entity-card :deep(.n-data-table-th),
.kg-entity-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.kg-entity-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.kg-entity-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}
</style>
