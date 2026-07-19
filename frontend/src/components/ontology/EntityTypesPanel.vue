<template>
  <div class="entity-types-wrapper">
    <div class="entity-types-toolbar">
      <n-button type="primary" @click="openCreate">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新建实体类型
      </n-button>
    </div>

    <div class="entity-types-card">
      <div class="admin-list-table">
        <n-data-table
          :columns="columns"
          :data="entityTypes"
          :loading="loading"
          :bordered="false"
          :row-key="(row) => row.code"
          pagination
          :max-height="tableMaxHeight"
        />
      </div>
    </div>

    <!-- 编辑/创建弹窗 -->
    <n-modal v-model:show="showModal" :title="isEdit ? '编辑实体类型' : '新建实体类型'"
      preset="card" style="width: 620px" :mask-closable="false">
      <n-form :model="form" label-placement="left" label-width="100px">
        <n-form-item label="标识 code" :rule="codeRule">
          <n-input v-model:value="form.code" :disabled="isEdit" placeholder="小写字母、数字、下划线" />
        </n-form-item>
        <n-form-item label="显示名" required>
          <n-input v-model:value="form.label" placeholder="如：法规/标准" />
        </n-form-item>
        <n-form-item label="颜色">
          <n-select v-model:value="form.color" :options="colorOptions" />
        </n-form-item>
        <n-form-item label="图标">
          <n-input v-model:value="form.icon" placeholder="ionicons5 图标名" />
        </n-form-item>
        <n-form-item label="排序">
          <n-input-number v-model:value="form.sort_order" :min="1" :max="999" />
        </n-form-item>
        <n-form-item label="属性模式">
          <property-editor v-model:value="form.property_schema" />
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
import { useI18n } from "../../composables/useI18n";
import { useMessage, useDialog } from "naive-ui";
import { AddOutline, TrashOutline, CreateOutline, EyeOutline } from "@vicons/ionicons5";
import PropertyEditor from "./PropertyEditor.vue";
import {
  createOntologyEntityType,
  updateOntologyEntityType,
  deleteOntologyEntityType,
} from "../../api/ontology.js";

const props = defineProps({
  entityTypes: { type: Array, default: () => [] },
  loading: Boolean,
});

const emit = defineEmits(["refresh"]);

const router = useRouter();
const { t } = useI18n();
const message = useMessage();
const dialog = useDialog();

const colorOptions = [
  { label: "蓝色", value: "blue" },
  { label: "绿色", value: "green" },
  { label: "紫色", value: "purple" },
  { label: "橙色", value: "orange" },
  { label: "粉色", value: "pink" },
  { label: "黄色", value: "yellow" },
  { label: "青色", value: "cyan" },
  { label: "靛蓝", value: "indigo" },
  { label: "灰色", value: "gray" },
  { label: "红色", value: "red" },
];

const showModal = ref(false);
const isEdit = ref(false);
const saving = ref(false);
const form = reactive({
  code: "",
  label: "",
  color: "blue",
  icon: "help-circle",
  sort_order: 100,
  property_schema: {},
});
const editingCode = ref("");

// 自适应表格高度
const tableMaxHeight = ref(400);
let resizeObs = null;
function calcTableHeight() {
  const el = document.querySelector(".entity-types-wrapper");
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const avail = window.innerHeight - rect.top - 60;
  tableMaxHeight.value = Math.max(200, avail);
}
onMounted(() => {
  calcTableHeight();
  resizeObs = new ResizeObserver(calcTableHeight);
  const el = document.querySelector(".entity-types-wrapper");
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
  form.color = "blue";
  form.icon = "help-circle";
  form.sort_order = 100;
  form.property_schema = {};
  showModal.value = true;
}

function openEdit(row) {
  isEdit.value = true;
  editingCode.value = row.code;
  form.code = row.code;
  form.label = row.label;
  form.color = row.color || "blue";
  form.icon = row.icon || "help-circle";
  form.sort_order = row.sort_order || 100;
  form.property_schema = { ...(row.property_schema || {}) };
  showModal.value = true;
}

function doDelete(row) {
  dialog.warning({
    title: "确认删除",
    content: `删除实体类型 "${row.label} (${row.code})"？如仍有实体使用此类型将无法删除。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await deleteOntologyEntityType(row.code);
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
      color: form.color,
      icon: form.icon,
      sort_order: form.sort_order,
      property_schema: form.property_schema,
    };
    if (isEdit.value) {
      await updateOntologyEntityType(editingCode.value, body);
      message.success("已更新");
    } else {
      await createOntologyEntityType(body);
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
  {
    title: "颜色",
    key: "color",
    width: 80,
    render(row) {
      return h("span", {
        style: {
          display: "inline-block",
          width: "20px",
          height: "20px",
          borderRadius: "4px",
          backgroundColor: row.color,
          border: "1px solid #ccc",
        },
      });
    },
  },
  { title: "图标", key: "icon", width: 100 },
  { title: "属性数", key: "property_count", width: 80 },
  {
    title: "实体数",
    key: "entity_count",
    width: 80,
    render(row) {
      const count = row.entity_count ?? 0;
      if (count === 0) return String(count);
      return h(
        "a",
        {
          style: { color: "var(--platform-primary, #2080f0)", cursor: "pointer", textDecoration: "underline" },
          onClick: () => router.push({ name: "kg", query: { entityType: row.code } }),
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
          h(
            "n-button",
            {
              size: "small",
              quaternary: true,
              onClick: () => router.push({ name: "kg", query: { entityType: row.code } }),
            },
            { default: () => "查看实例", icon: () => h(EyeOutline) }
          ),
          h(
            "n-button",
            {
              size: "small",
              quaternary: true,
              onClick: () => openEdit(row),
            },
            { default: () => "编辑", icon: () => h(CreateOutline) }
          ),
          h(
            "n-button",
            {
              size: "small",
              quaternary: true,
              type: "error",
              onClick: () => doDelete(row),
            },
            { default: () => "删除", icon: () => h(TrashOutline) }
          ),
        ],
      });
    },
  },
];
</script>

<style scoped>
.entity-types-wrapper {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: hidden;
}

.entity-types-toolbar {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.entity-types-card {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 0 16px;
}

.entity-types-card :deep(.n-data-table-th),
.entity-types-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.entity-types-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.entity-types-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}

.entity-types-card .admin-list-table {
  height: 100%;
  overflow: auto;
}
</style>
