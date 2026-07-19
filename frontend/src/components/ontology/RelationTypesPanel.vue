<template>
  <div class="relation-types-wrapper">
    <div class="relation-types-toolbar">
      <n-button type="primary" @click="openCreate">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新建关系类型
      </n-button>
    </div>

    <div class="relation-types-card">
      <div class="admin-list-table">
        <n-data-table
          :columns="columns"
          :data="relationTypes"
          :loading="loading"
          :bordered="false"
          :row-key="(row) => row.code"
          pagination
          :max-height="tableMaxHeight"
        />
      </div>
    </div>

    <n-modal v-model:show="showModal" :title="isEdit ? '编辑关系类型' : '新建关系类型'"
      preset="card" style="width: 640px" :mask-closable="false">
      <n-form :model="form" label-placement="left" label-width="120px">
        <n-form-item label="标识 code" :rule="codeRule">
          <n-input v-model:value="form.code" :disabled="isEdit" placeholder="小写字母、数字、下划线" />
        </n-form-item>
        <n-form-item label="显示名" required>
          <n-input v-model:value="form.label" placeholder="如：约束" />
        </n-form-item>
        <n-form-item label="起点类型">
          <n-dynamic-tags v-model:value="form.domain_types" placeholder="输入实体类型 code" />
        </n-form-item>
        <n-form-item label="终点类型">
          <n-dynamic-tags v-model:value="form.range_types" placeholder="输入实体类型 code" />
        </n-form-item>
        <n-form-item label="传递性">
          <n-switch v-model:value="form.transitive" />
        </n-form-item>
        <n-form-item label="对称性">
          <n-switch v-model:value="form.symmetric" />
        </n-form-item>
        <n-form-item label="互逆关系">
          <n-input v-model:value="form.inverse_of" placeholder="如：constrained_by" />
        </n-form-item>
        <n-form-item label="排序">
          <n-input-number v-model:value="form.sort_order" :min="1" :max="999" />
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
import { h, ref, reactive, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useMessage, useDialog } from "naive-ui";
import { AddOutline, TrashOutline, CreateOutline, EyeOutline } from "@vicons/ionicons5";
import {
  createOntologyRelationType,
  updateOntologyRelationType,
  deleteOntologyRelationType,
} from "../../api/ontology.js";

const props = defineProps({
  relationTypes: { type: Array, default: () => [] },
  loading: Boolean,
});

const emit = defineEmits(["refresh"]);

const router = useRouter();
const message = useMessage();
const dialog = useDialog();

const showModal = ref(false);
const isEdit = ref(false);
const saving = ref(false);
const form = reactive({
  code: "",
  label: "",
  domain_types: [],
  range_types: [],
  transitive: false,
  symmetric: false,
  inverse_of: "",
  sort_order: 100,
});
const editingCode = ref("");

// 自适应表格高度
const tableMaxHeight = ref(400);
let resizeObs = null;
function calcTableHeight() {
  const el = document.querySelector(".relation-types-wrapper");
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const avail = window.innerHeight - rect.top - 60;
  tableMaxHeight.value = Math.max(200, avail);
}
onMounted(() => {
  calcTableHeight();
  resizeObs = new ResizeObserver(calcTableHeight);
  const el = document.querySelector(".relation-types-wrapper");
  if (el) resizeObs.observe(el);
});
onUnmounted(() => { resizeObs?.disconnect(); });

const codeRule = {
  pattern: /^[a-z][a-z0-9_]*$/,
  message: "仅小写字母、数字、下划线，字母开头",
  trigger: "blur",
};

function openCreate() {
  isEdit.value = false;
  editingCode.value = "";
  form.code = "";
  form.label = "";
  form.domain_types = [];
  form.range_types = [];
  form.transitive = false;
  form.symmetric = false;
  form.inverse_of = "";
  form.sort_order = 100;
  showModal.value = true;
}

function openEdit(row) {
  isEdit.value = true;
  editingCode.value = row.code;
  form.code = row.code;
  form.label = row.label;
  form.domain_types = [...(row.domain_types || [])];
  form.range_types = [...(row.range_types || [])];
  form.transitive = !!row.transitive;
  form.symmetric = !!row.symmetric;
  form.inverse_of = row.inverse_of || "";
  form.sort_order = row.sort_order || 100;
  showModal.value = true;
}

function doDelete(row) {
  dialog.warning({
    title: "确认删除",
    content: `删除关系类型 "${row.label} (${row.code})"? 如仍有实例将无法删除。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await deleteOntologyRelationType(row.code);
        message.success("已删除");
        emit("refresh");
      } catch (err) {
        message.error("删除失败: " + (err.message || ""));
      }
    },
  });
}

async function handleSave() {
  if (!form.code || !form.label) {
    message.warning("请填写 code 和 label");
    return;
  }
  saving.value = true;
  try {
    const body = {
      code: form.code,
      label: form.label,
      domain_types: form.domain_types,
      range_types: form.range_types,
      transitive: form.transitive,
      symmetric: form.symmetric,
      inverse_of: form.inverse_of || null,
      sort_order: form.sort_order,
    };
    if (isEdit.value) {
      await updateOntologyRelationType(editingCode.value, body);
      message.success("已更新");
    } else {
      await createOntologyRelationType(body);
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
    title: "显示名",
    key: "label",
    minWidth: 200,
    ellipsis: { tooltip: true },
    render(row) {
      return h("div", { style: "display:flex;flex-direction:column;gap:2px;padding:2px 0;" }, [
        h("div", { style: "font-size:var(--platform-font-size-sm);font-weight:500;color:var(--platform-text);line-height:1.4;" }, row.label),
        h("div", { style: "font-size:var(--platform-font-size-sm);color:var(--platform-text-tertiary);line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, row.code || ""),
      ]);
    },
  },
  { title: "起点类型", key: "domain_types", width: 120 },
  { title: "终点类型", key: "range_types", width: 120 },
  { title: "传递", key: "transitive", width: 60 },
  { title: "对称", key: "symmetric", width: 60 },
  { title: "互逆", key: "inverse_of", width: 100 },
  {
    title: "关系数",
    key: "relation_count",
    width: 70,
    render(row) {
      const count = row.relation_count ?? 0;
      if (count === 0) return String(count);
      return h(
        "a",
        {
          style: { color: "var(--platform-primary, #2080f0)", cursor: "pointer", textDecoration: "underline" },
          onClick: () => router.push({ name: "kg", query: { relationType: row.code } }),
        },
        String(count)
      );
    },
  },
  { title: "排序", key: "sort_order", width: 60 },
  {
    title: "操作",
    key: "actions",
    width: 180,
    render(row) {
      return h("n-space", null, {
        default: () => [
          h("n-button", {
              size: "small", quaternary: true,
              onClick: () => router.push({ name: "kg", query: { relationType: row.code } }),
            },
            { default: () => "查看实例", icon: () => h(EyeOutline) }),
          h("n-button", { size: "small", quaternary: true, onClick: () => openEdit(row) },
            { default: () => "编辑", icon: () => h(CreateOutline) }),
          h("n-button", { size: "small", quaternary: true, type: "error", onClick: () => doDelete(row) },
            { default: () => "删除", icon: () => h(TrashOutline) }),
        ],
      });
    },
  },
];
</script>

<style scoped>
.relation-types-wrapper {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: hidden;
}

.relation-types-toolbar {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.relation-types-card {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 0 16px;
}

.relation-types-card :deep(.n-data-table-th),
.relation-types-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.relation-types-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.relation-types-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}

.relation-types-card .admin-list-table {
  height: 100%;
  overflow: auto;
}
</style>
