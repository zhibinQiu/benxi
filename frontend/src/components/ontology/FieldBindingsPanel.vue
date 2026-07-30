<template>
  <div class="field-bindings">
    <div class="field-bindings__hd">
      <n-text depth="3" style="font-size: 12px">
        可选：事务库问数接线（文档抽取概念可不配）
      </n-text>
      <n-button size="tiny" secondary :loading="loading" @click="runDiscover">
        重新发现
      </n-button>
    </div>
    <div v-if="!rows.length && !loading" class="field-bindings__empty">
      暂无 SQL 映射（正常：纯文档本体不需要）
    </div>
    <div v-for="row in rows" :key="row.id" class="field-bindings__row">
      <div class="field-bindings__main">
        <code>{{ row.concept }}.{{ row.property_key }}</code>
        <span class="field-bindings__arrow">→</span>
        <span v-if="row.join_template">join:{{ row.join_template }}</span>
        <span v-else>{{ row.table_name }}.{{ row.column_name }}</span>
      </div>
      <n-space :size="4" align="center">
        <n-tag size="tiny" :bordered="false">{{ row.origin }}</n-tag>
        <n-tag
          size="tiny"
          :type="row.status === 'pending' ? 'warning' : 'success'"
          :bordered="false"
        >
          {{ row.status }}
        </n-tag>
        <n-switch
          size="small"
          :value="row.enabled"
          @update:value="(v) => toggle(row, v)"
        />
        <n-button
          v-if="row.status === 'pending'"
          size="tiny"
          quaternary
          type="primary"
          @click="confirm(row)"
        >
          确认
        </n-button>
      </n-space>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import {
  discoverFieldBindings,
  fetchFieldBindings,
  updateFieldBinding,
} from "../../api/ontology.js";

const ui = usePlatformUi();
const rows = ref([]);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const res = await fetchFieldBindings();
    rows.value = Array.isArray(res) ? res : res?.items || res || [];
    if (!Array.isArray(rows.value)) rows.value = [];
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    // 映射可选：失败时静默为空，不打断本体编辑
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

async function runDiscover() {
  loading.value = true;
  try {
    const res = await discoverFieldBindings();
    rows.value = res?.items || [];
    ui.success(
      `发现完成：新建 ${res?.created || 0}，更新 ${res?.updated || 0}`
    );
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("自动发现失败: " + (err.message || ""));
  } finally {
    loading.value = false;
  }
}

async function toggle(row, enabled) {
  try {
    const updated = await updateFieldBinding(row.id, { enabled });
    Object.assign(row, updated);
  } catch (err) {
    ui.error(err.message || "更新失败");
  }
}

async function confirm(row) {
  try {
    const updated = await updateFieldBinding(row.id, {
      status: "active",
      enabled: true,
    });
    Object.assign(row, updated);
    ui.success("已确认映射");
  } catch (err) {
    ui.error(err.message || "确认失败");
  }
}

onMounted(load);

defineExpose({ reload: load, discover: runDiscover });
</script>

<style scoped>
.field-bindings {
  margin-top: 12px;
  border-top: 1px solid var(--platform-border, #e5e7eb);
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 220px;
  overflow: auto;
}
.field-bindings__hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.field-bindings__row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--platform-text) 4%, transparent);
  font-size: 12px;
}
.field-bindings__main {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex-wrap: wrap;
}
.field-bindings__arrow {
  color: var(--platform-text-tertiary);
}
.field-bindings__empty {
  font-size: 12px;
  color: var(--platform-text-tertiary);
  padding: 8px 0;
}
</style>
