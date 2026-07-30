<template>
  <div class="concept-bindings">
    <div class="concept-bindings__hd">
      <span>问数映射（可选）</span>
      <n-button size="tiny" quaternary :loading="loading" @click="reload">刷新</n-button>
    </div>
    <n-text depth="3" style="font-size: 11px; display: block; margin-bottom: 8px">
      仅在需要查事务库时配置「属性→表.列」。文档抽取的概念可不配，走图谱/检索即可。
    </n-text>
    <div v-if="!propKeys.length" class="concept-bindings__empty">
      请先在属性模式中定义属性
    </div>
    <div v-for="key in propKeys" :key="key" class="concept-bindings__item">
      <div class="concept-bindings__prop">
        <code>{{ concept }}.{{ key }}</code>
      </div>
      <n-space vertical :size="6" style="width: 100%">
        <n-select
          size="small"
          :value="draft[key]?.table_name || null"
          clearable
          filterable
          placeholder="表"
          :options="tableOptions"
          @update:value="(v) => onTable(key, v)"
        />
        <n-select
          size="small"
          :value="draft[key]?.column_name || null"
          clearable
          filterable
          placeholder="列"
          :options="columnOptions(draft[key]?.table_name)"
          :disabled="!draft[key]?.table_name"
          @update:value="(v) => onColumn(key, v)"
        />
        <n-select
          size="small"
          :value="draft[key]?.join_template || null"
          clearable
          filterable
          tag
          placeholder="联查模板（可选）"
          :options="joinTemplateOptions"
          @update:value="(v) => onJoin(key, v)"
        />
        <n-space justify="end">
          <n-button size="tiny" type="primary" secondary :loading="savingKey === key" @click="save(key)">
            保存映射
          </n-button>
        </n-space>
      </n-space>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import {
  fetchFieldBindingSchema,
  fetchFieldBindings,
  updateFieldBinding,
  upsertFieldBinding,
} from "../../api/ontology.js";

const props = defineProps({
  concept: { type: String, required: true },
  propertySchema: { type: Object, default: () => ({}) },
});

const ui = usePlatformUi();
const loading = ref(false);
const savingKey = ref("");
const rows = ref([]);
const draft = reactive({});
/** 后端白名单表→列（自省结果） */
const tableColumns = ref({});
const joinTemplates = ref([]);

const tableOptions = computed(() =>
  Object.keys(tableColumns.value || {}).map((t) => ({ label: t, value: t }))
);

const joinTemplateOptions = computed(() =>
  (joinTemplates.value || []).map((t) => ({ label: t, value: t }))
);

const propKeys = computed(() => Object.keys(props.propertySchema || {}));

function columnOptions(table) {
  const cols = tableColumns.value?.[table] || [];
  return cols.map((c) => ({ label: c, value: c }));
}

function syncDraft() {
  for (const key of propKeys.value) {
    const hit = rows.value.find(
      (r) => r.concept === props.concept && r.property_key === key
    );
    draft[key] = {
      id: hit?.id || "",
      table_name: hit?.table_name || "",
      column_name: hit?.column_name || "",
      join_template: hit?.join_template || "",
    };
  }
}

async function reload() {
  if (!props.concept) return;
  loading.value = true;
  try {
    const [schema, res] = await Promise.all([
      fetchFieldBindingSchema().catch(() => null),
      fetchFieldBindings().catch(() => []),
    ]);
    if (schema?.tables) {
      tableColumns.value = schema.tables;
      joinTemplates.value = schema.join_templates || [];
    }
    const list = Array.isArray(res) ? res : [];
    rows.value = list.filter((r) => r.concept === props.concept);
    syncDraft();
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    rows.value = [];
    syncDraft();
  } finally {
    loading.value = false;
  }
}

function onTable(key, v) {
  if (!draft[key]) draft[key] = {};
  draft[key].table_name = v || "";
  draft[key].column_name = "";
}

function onColumn(key, v) {
  if (!draft[key]) draft[key] = {};
  draft[key].column_name = v || "";
}

function onJoin(key, v) {
  if (!draft[key]) draft[key] = {};
  draft[key].join_template = v || "";
}

async function save(key) {
  const d = draft[key] || {};
  savingKey.value = key;
  try {
    const body = {
      concept: props.concept,
      property_key: key,
      source: "sql",
      table_name: d.table_name || "",
      column_name: d.column_name || "",
      join_template: d.join_template || "",
      enabled: true,
      status: "active",
      notes: "手动映射",
    };
    let updated;
    if (d.id) {
      updated = await updateFieldBinding(d.id, body);
    } else {
      updated = await upsertFieldBinding(body);
    }
    draft[key] = {
      id: updated.id,
      table_name: updated.table_name || "",
      column_name: updated.column_name || "",
      join_template: updated.join_template || "",
    };
    ui.success(`已保存 ${props.concept}.${key}`);
    await reload();
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error(err.message || "保存失败");
  } finally {
    savingKey.value = "";
  }
}

watch(
  () => [props.concept, props.propertySchema],
  () => reload(),
  { immediate: true, deep: true }
);
</script>

<style scoped>
.concept-bindings {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--platform-border, #e5e7eb);
}
.concept-bindings__hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
}
.concept-bindings__item {
  padding: 8px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--platform-text) 4%, transparent);
}
.concept-bindings__prop {
  font-size: 12px;
  margin-bottom: 6px;
}
.concept-bindings__empty {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}
</style>
