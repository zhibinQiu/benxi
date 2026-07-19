<template>
  <div class="axioms-wrapper">
    <div class="axioms-toolbar">
      <n-button type="primary" @click="openCreate">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新建公理
      </n-button>
      <n-button @click="handleRunAll" :loading="runningAll">
        <template #icon><n-icon><PlayOutline /></n-icon></template>
        执行所有活跃公理
      </n-button>
    </div>

    <div class="axioms-card">
      <div class="admin-list-table">
        <n-data-table
          :columns="columns"
          :data="axioms"
          :loading="loading"
          :bordered="false"
          :row-key="(row) => row.name"
          pagination
          :max-height="tableMaxHeight"
        />
      </div>
    </div>

    <n-modal v-model:show="showModal" :title="isEdit ? '编辑公理' : '新建公理'"
      preset="card" style="width: 700px" :mask-closable="false">
      <n-form :model="form" label-placement="left" label-width="100px">
        <n-form-item label="名称" required>
          <n-input v-model:value="form.name" :disabled="isEdit" placeholder="如：reg_transitive_constrain" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" type="textarea" :rows="2" />
        </n-form-item>
        <n-form-item label="Cypher 规则" required>
          <n-input v-model:value="form.cypher_rule" type="textarea" :rows="6"
            placeholder="MATCH ... RETURN ..." />
        </n-form-item>
        <n-form-item label="启用">
          <n-switch v-model:value="form.active" />
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
import { h, ref, reactive, onMounted, onUnmounted } from "vue";
import { useMessage, useDialog } from "naive-ui";
import { AddOutline, TrashOutline, CreateOutline, PlayOutline } from "@vicons/ionicons5";
import {
  createOntologyAxiom,
  updateOntologyAxiom,
  deleteOntologyAxiom,
  runOntologyAxiom,
  runAllOntologyAxioms,
} from "../../api/ontology.js";

const props = defineProps({
  axioms: { type: Array, default: () => [] },
  loading: Boolean,
});

const emit = defineEmits(["refresh"]);

const message = useMessage();
const dialog = useDialog();

const showModal = ref(false);
const isEdit = ref(false);
const saving = ref(false);
const runningAll = ref(false);

// 自适应表格高度
const tableMaxHeight = ref(400);
let resizeObs = null;
function calcTableHeight() {
  const el = document.querySelector(".axioms-wrapper");
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const avail = window.innerHeight - rect.top - 60;
  tableMaxHeight.value = Math.max(200, avail);
}
onMounted(() => {
  calcTableHeight();
  resizeObs = new ResizeObserver(calcTableHeight);
  const el = document.querySelector(".axioms-wrapper");
  if (el) resizeObs.observe(el);
});
onUnmounted(() => { resizeObs?.disconnect(); });

const form = reactive({
  name: "",
  description: "",
  cypher_rule: "",
  active: true,
});
const editingName = ref("");

function openCreate() {
  isEdit.value = false;
  editingName.value = "";
  form.name = "";
  form.description = "";
  form.cypher_rule = "";
  form.active = true;
  showModal.value = true;
}

function openEdit(row) {
  isEdit.value = true;
  editingName.value = row.name;
  form.name = row.name;
  form.description = row.description || "";
  form.cypher_rule = row.cypher_rule || "";
  form.active = row.active !== false;
  showModal.value = true;
}

function doDelete(row) {
  dialog.warning({
    title: "确认删除",
    content: `删除公理 "${row.name}"？`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await deleteOntologyAxiom(row.name);
        message.success("已删除");
        emit("refresh");
      } catch (err) {
        message.error("删除失败: " + (err.message || ""));
      }
    },
  });
}

function doRun(row) {
  runOntologyAxiom(row.name)
    .then((res) => {
      const data = res || {};
      if (data.success) {
        message.success(`执行成功，影响 ${data.affected_count || 0} 条`);
      } else {
        message.warning(`执行失败: ${data.error}`);
      }
      emit("refresh");
    })
    .catch((err) => {
      message.error("执行失败: " + (err.message || ""));
    });
}

async function handleRunAll() {
  runningAll.value = true;
  try {
    const res = await runAllOntologyAxioms();
    const results = res || [];
    const ok = results.filter((r) => r.success).length;
    const fail = results.filter((r) => !r.success).length;
    message.success(`执行完成：成功 ${ok} / 失败 ${fail}`);
    emit("refresh");
  } catch (err) {
    message.error("批量执行失败: " + (err.message || ""));
  } finally {
    runningAll.value = false;
  }
}

async function handleSave() {
  if (!form.name || !form.cypher_rule) {
    message.warning("请填写名称和 Cypher 规则");
    return;
  }
  saving.value = true;
  try {
    const body = {
      name: form.name,
      description: form.description,
      cypher_rule: form.cypher_rule,
      active: form.active,
    };
    if (isEdit.value) {
      await updateOntologyAxiom(editingName.value, body);
      message.success("已更新");
    } else {
      await createOntologyAxiom(body);
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
  { title: "启用", key: "active", width: 60 },
  { title: "上次执行", key: "last_run_result", width: 120 },
  {
    title: "操作",
    key: "actions",
    width: 180,
    render(row) {
      return h("n-space", null, {
        default: () => [
          h("n-button", { size: "small", quaternary: true, onClick: () => doRun(row) },
            { default: () => "执行", icon: () => h(PlayOutline) }),
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
.axioms-wrapper {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: hidden;
}

.axioms-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.axioms-card {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-card-radius);
  background: #fcfcfc;
  padding: 0 16px;
}

.axioms-card :deep(.n-data-table-th),
.axioms-card :deep(.n-data-table-td) {
  padding: 6px 12px;
}

.axioms-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--platform-border-strong);
  vertical-align: middle;
}

.axioms-card :deep(.n-data-table-tr:last-child .n-data-table-td) {
  border-bottom: none;
}

.axioms-card .admin-list-table {
  height: 100%;
  overflow: auto;
}
</style>
