<template>
  <div class="onto-workbench">
    <aside class="onto-workbench__left">
      <n-tabs
        v-model:value="listKind"
        type="line"
        size="small"
        class="onto-workbench__tabs"
      >
        <n-tab-pane name="entity" :tab="`概念 ${entityTypes.length}`" display-directive="if">
          <div class="onto-workbench__pane">
            <n-input
              v-model:value="keyword"
              size="small"
              clearable
              placeholder="搜索概念…"
            />
            <n-button block size="small" secondary @click="startCreate">+ 新建概念</n-button>
            <div class="onto-workbench__list">
              <button
                v-for="item in filteredList"
                :key="item.code"
                type="button"
                class="onto-workbench__item"
                :class="{ 'is-active': selectedCode === item.code }"
                @click="selectItem(item)"
              >
                <span class="onto-workbench__dot" :style="{ background: colorOf(item.color) }" />
                <span class="onto-workbench__item-main">
                  <span class="onto-workbench__item-label">{{ item.label }}</span>
                  <span class="onto-workbench__item-code">{{ item.code }}</span>
                </span>
                <span class="onto-workbench__count">{{ item.entity_count || 0 }}</span>
              </button>
              <div v-if="!filteredList.length" class="onto-workbench__empty">无匹配项</div>
            </div>
          </div>
        </n-tab-pane>
        <n-tab-pane name="relation" :tab="`关系 ${relationTypes.length}`" display-directive="if">
          <div class="onto-workbench__pane">
            <n-input
              v-model:value="keyword"
              size="small"
              clearable
              placeholder="搜索关系…"
            />
            <n-button block size="small" secondary @click="startCreate">+ 新建关系类型</n-button>
            <div class="onto-workbench__list">
              <button
                v-for="item in filteredList"
                :key="item.code"
                type="button"
                class="onto-workbench__item"
                :class="{ 'is-active': selectedCode === item.code }"
                @click="selectItem(item)"
              >
                <span class="onto-workbench__item-main">
                  <span class="onto-workbench__item-label">{{ item.label }}</span>
                  <span class="onto-workbench__item-code">{{ item.code }}</span>
                </span>
                <span class="onto-workbench__count">{{ item.relation_count || 0 }}</span>
              </button>
              <div v-if="!filteredList.length" class="onto-workbench__empty">无匹配项</div>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
    </aside>

    <main class="onto-workbench__center">
      <SemanticModelViz
        ref="vizRef"
        hide-detail-panel
        :entity-types="entityTypes"
        :relation-types="relationTypes"
        :selected-code="selectedCode"
        :selected-kind="listKind"
        @select-concept="onSelectFromGraph"
        @explore-concept="(p) => emit('explore-concept', p)"
      />
    </main>

    <aside class="onto-workbench__right">
      <div class="onto-workbench__right-hd">
        <div class="onto-workbench__right-hd-main">
          <strong>{{ editing ? (isCreate ? "新建" : "编辑") : "属性" }}</strong>
          <n-text depth="3" style="font-size: 12px">
            {{ listKind === "entity" ? "实体类型" : "关系类型" }}
          </n-text>
        </div>
        <n-button size="tiny" secondary @click="showDiscover = true">LLM 发现本体</n-button>
      </div>

      <div v-if="!editing" class="onto-workbench__placeholder-wrap">
        <div class="onto-workbench__placeholder">
          从左侧选择一项，或点击「新建」
        </div>
        <FieldBindingsPanel />
      </div>

      <n-form
        v-else
        :model="form"
        label-placement="top"
        size="small"
        class="onto-workbench__form"
      >
        <n-form-item label="标识 code" required>
          <n-input v-model:value="form.code" :disabled="!isCreate" placeholder="snake_case" />
        </n-form-item>
        <n-form-item label="显示名" required>
          <n-input v-model:value="form.label" />
        </n-form-item>

        <template v-if="listKind === 'entity'">
          <n-form-item label="颜色">
            <n-select v-model:value="form.color" :options="colorOptions" />
          </n-form-item>
          <n-form-item label="图标">
            <n-input v-model:value="form.icon" />
          </n-form-item>
          <n-form-item label="排序">
            <n-input-number v-model:value="form.sort_order" :min="1" :max="999" style="width:100%" />
          </n-form-item>
          <n-form-item label="属性模式">
            <PropertyEditor v-model:value="form.property_schema" />
          </n-form-item>
          <ConceptFieldBindingsEditor
            v-if="!isCreate && form.code"
            :concept="form.code"
            :property-schema="form.property_schema"
          />
        </template>

        <template v-else>
          <n-form-item label="起点类型 (domain)">
            <n-select
              v-model:value="form.domain_types"
              multiple
              filterable
              :options="entityTypeOptions"
              placeholder="可选多个"
            />
          </n-form-item>
          <n-form-item label="终点类型 (range)">
            <n-select
              v-model:value="form.range_types"
              multiple
              filterable
              :options="entityTypeOptions"
              placeholder="可选多个"
            />
          </n-form-item>
          <n-form-item label="传递 / 对称">
            <n-space>
              <n-checkbox v-model:checked="form.transitive">传递</n-checkbox>
              <n-checkbox v-model:checked="form.symmetric">对称</n-checkbox>
            </n-space>
          </n-form-item>
          <n-form-item label="互逆关系">
            <n-input v-model:value="form.inverse_of" placeholder="可选 code" />
          </n-form-item>
          <n-form-item label="排序">
            <n-input-number v-model:value="form.sort_order" :min="1" :max="999" style="width:100%" />
          </n-form-item>
        </template>

        <n-space justify="space-between" style="margin-top: 8px">
          <n-button v-if="!isCreate" type="error" secondary size="small" :loading="saving" @click="handleDelete">
            删除
          </n-button>
          <span v-else />
          <n-space>
            <n-button size="small" @click="editing = false">取消</n-button>
            <n-button type="primary" size="small" :loading="saving" @click="handleSave">保存</n-button>
          </n-space>
        </n-space>

        <n-button
          v-if="!isCreate && listKind === 'entity'"
          block
          secondary
          size="small"
          style="margin-top: 12px"
          @click="emit('explore-concept', { code: form.code, label: form.label })"
        >
          查看该概念的实例 →
        </n-button>
      </n-form>
    </aside>

    <n-drawer v-model:show="showDiscover" :width="520" placement="right">
      <n-drawer-content title="LLM 发现本体（TBox）" closable>
        <OntologyDiscoverPanel @applied="onDiscoverApplied" />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import PropertyEditor from "./PropertyEditor.vue";
import SemanticModelViz from "./SemanticModelViz.vue";
import OntologyDiscoverPanel from "./OntologyDiscoverPanel.vue";
import FieldBindingsPanel from "./FieldBindingsPanel.vue";
import ConceptFieldBindingsEditor from "./ConceptFieldBindingsEditor.vue";
import {
  createOntologyEntityType,
  updateOntologyEntityType,
  deleteOntologyEntityType,
  createOntologyRelationType,
  updateOntologyRelationType,
  deleteOntologyRelationType,
} from "../../api/ontology.js";

const props = defineProps({
  entityTypes: { type: Array, default: () => [] },
  relationTypes: { type: Array, default: () => [] },
  loading: Boolean,
});

const emit = defineEmits(["refresh", "explore-concept"]);

const ui = usePlatformUi();
const vizRef = ref(null);
const listKind = ref("entity");
const keyword = ref("");
const selectedCode = ref("");
const editing = ref(false);
const isCreate = ref(false);
const saving = ref(false);
const showDiscover = ref(false);

function onDiscoverApplied() {
  showDiscover.value = false;
  emit("refresh");
}

onBeforeUnmount(() => {
  showDiscover.value = false;
});

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
];

const COLOR_MAP = Object.fromEntries(
  colorOptions.map((c) => [c.value, ({
    blue: "#3b82f6",
    green: "#22c55e",
    purple: "#a855f7",
    orange: "#f97316",
    pink: "#ec4899",
    yellow: "#eab308",
    cyan: "#06b6d4",
    indigo: "#6366f1",
    gray: "#94a3b8",
  })[c.value]])
);

function colorOf(c) {
  if (!c) return COLOR_MAP.blue;
  if (String(c).startsWith("#")) return c;
  return COLOR_MAP[c] || COLOR_MAP.blue;
}

const form = reactive({
  code: "",
  label: "",
  color: "blue",
  icon: "help-circle",
  sort_order: 100,
  property_schema: {},
  domain_types: [],
  range_types: [],
  transitive: false,
  symmetric: false,
  inverse_of: "",
});

const entityTypeOptions = computed(() =>
  props.entityTypes.map((et) => ({ label: `${et.label} (${et.code})`, value: et.code }))
);

const filteredList = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  const rows = listKind.value === "entity" ? props.entityTypes : props.relationTypes;
  if (!q) return rows;
  return rows.filter(
    (r) =>
      String(r.code || "").toLowerCase().includes(q) ||
      String(r.label || "").toLowerCase().includes(q)
  );
});

watch(listKind, () => {
  selectedCode.value = "";
  editing.value = false;
  keyword.value = "";
});

function resetForm() {
  form.code = "";
  form.label = "";
  form.color = "blue";
  form.icon = "help-circle";
  form.sort_order = 100;
  form.property_schema = {};
  form.domain_types = [];
  form.range_types = [];
  form.transitive = false;
  form.symmetric = false;
  form.inverse_of = "";
}

function fillEntity(row) {
  form.code = row.code;
  form.label = row.label || "";
  form.color = row.color || "blue";
  form.icon = row.icon || "help-circle";
  form.sort_order = row.sort_order || 100;
  form.property_schema = { ...(row.property_schema || {}) };
}

function fillRelation(row) {
  form.code = row.code;
  form.label = row.label || "";
  form.domain_types = [...(row.domain_types || [])];
  form.range_types = [...(row.range_types || [])];
  form.transitive = !!row.transitive;
  form.symmetric = !!row.symmetric;
  form.inverse_of = row.inverse_of || "";
  form.sort_order = row.sort_order || 100;
}

function selectItem(item) {
  selectedCode.value = item.code;
  isCreate.value = false;
  editing.value = true;
  resetForm();
  if (listKind.value === "entity") fillEntity(item);
  else fillRelation(item);
}

function onSelectFromGraph(node) {
  listKind.value = "entity";
  const found = props.entityTypes.find((e) => e.code === node.code);
  if (found) selectItem(found);
  else {
    selectedCode.value = node.code;
    isCreate.value = false;
    editing.value = true;
    resetForm();
    fillEntity(node);
  }
}

function startCreate() {
  selectedCode.value = "";
  isCreate.value = true;
  editing.value = true;
  resetForm();
}

async function handleSave() {
  if (!form.code || !form.label) {
    ui.warning("请填写 code 与显示名");
    return;
  }
  saving.value = true;
  try {
    if (listKind.value === "entity") {
      const body = {
        code: form.code,
        label: form.label,
        color: form.color,
        icon: form.icon,
        sort_order: form.sort_order,
        property_schema: form.property_schema,
      };
      if (isCreate.value) await createOntologyEntityType(body);
      else await updateOntologyEntityType(form.code, body);
    } else {
      const body = {
        code: form.code,
        label: form.label,
        domain_types: form.domain_types || [],
        range_types: form.range_types || [],
        transitive: form.transitive,
        symmetric: form.symmetric,
        inverse_of: form.inverse_of || null,
        sort_order: form.sort_order,
      };
      if (isCreate.value) await createOntologyRelationType(body);
      else await updateOntologyRelationType(form.code, body);
    }
    ui.success(isCreate.value ? "已创建" : "已保存");
    isCreate.value = false;
    selectedCode.value = form.code;
    emit("refresh");
    await nextTick();
    // 保存后按当前选中项聚焦关联子图，不自动拉全图
    vizRef.value?.focusSelection?.(listKind.value, form.code);
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("保存失败: " + (err.message || ""));
  } finally {
    saving.value = false;
  }
}

function handleDelete() {
  const code = form.code;
  const label = form.label;
  ui.confirmDelete({
    title: "确认删除",
    content: `删除「${label} (${code})」？`,
    onPositive: async () => {
      if (listKind.value === "entity") await deleteOntologyEntityType(code);
      else await deleteOntologyRelationType(code);
      ui.success("已删除");
      editing.value = false;
      selectedCode.value = "";
      emit("refresh");
      vizRef.value?.clearGraph?.();
    },
  });
}

function resize() {
  vizRef.value?.resize?.();
}

function reloadViz() {
  // 仅在用户已打开全图时随数据刷新；不自动拉图
  if (vizRef.value?.reload && selectedCode.value) {
    vizRef.value.focusSelection?.(listKind.value, selectedCode.value);
  }
}

defineExpose({ resize, reloadViz });
</script>

<style scoped>
.onto-workbench {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 320px;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.onto-workbench__left,
.onto-workbench__right {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--platform-border, #e5e7eb);
  border-radius: var(--platform-radius, 8px);
  background: var(--platform-bg-base, #fff);
  padding: 10px;
  overflow: hidden;
}
.onto-workbench__tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.onto-workbench__tabs :deep(.n-tabs-nav) {
  flex-shrink: 0;
}
.onto-workbench__tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.onto-workbench__tabs :deep(.n-tab-pane) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.onto-workbench__tabs :deep(.n-tabs-content) {
  flex: 1;
  min-height: 0;
}
.onto-workbench__pane {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
}
.onto-workbench__center {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  isolation: isolate;
}
.onto-workbench__center :deep(.semantic-viz) {
  min-height: 0;
  height: 100%;
}
.onto-workbench__list {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
}
.onto-workbench__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  color: var(--platform-text);
}
.onto-workbench__item:hover {
  background: color-mix(in srgb, var(--platform-text) 5%, transparent);
}
.onto-workbench__item.is-active {
  border-color: color-mix(in srgb, var(--platform-primary, #3b82f6) 45%, transparent);
  background: color-mix(in srgb, var(--platform-primary, #3b82f6) 8%, transparent);
}
.onto-workbench__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.onto-workbench__item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.onto-workbench__item-label {
  font-size: 13px;
  font-weight: 560;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.onto-workbench__item-code {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.onto-workbench__count {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.onto-workbench__empty,
.onto-workbench__placeholder {
  color: var(--platform-text-tertiary);
  font-size: 13px;
  padding: 16px 4px;
}
.onto-workbench__placeholder-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: auto;
}
.onto-workbench__right-hd {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  flex-shrink: 0;
}
.onto-workbench__right-hd-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.onto-workbench__form {
  flex: 1;
  overflow: auto;
  padding-right: 2px;
}
@media (max-width: 1100px) {
  .onto-workbench {
    grid-template-columns: 200px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
  }
  .onto-workbench__right {
    grid-column: 1 / -1;
    max-height: 360px;
  }
}
</style>
