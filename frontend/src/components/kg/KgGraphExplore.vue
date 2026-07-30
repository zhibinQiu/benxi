<template>
  <div class="kg-explore">
    <div class="kg-explore__toolbar">
      <n-space align="center">
        <n-tag size="small" :bordered="false">实例图谱</n-tag>
        <n-text depth="3" style="font-size: 12px">
          节点 {{ graphData.nodes?.length || 0 }} · 边 {{ graphData.edges?.length || 0 }}
        </n-text>
      </n-space>
      <n-space align="center">
        <n-button
          v-if="graphData.nodes?.length"
          size="tiny"
          quaternary
          @click="clearLocal"
        >
          清空
        </n-button>
        <n-button size="tiny" quaternary :loading="loading" @click="loadFullGraph">
          刷新
        </n-button>
      </n-space>
    </div>

    <div ref="chartHost" class="kg-explore__chart">
      <div v-if="!graphData.nodes?.length && !loading" class="kg-explore__empty">
        默认不加载图谱。点击「刷新」展示全部实体与关系，或从左侧选择实体查看关联。
      </div>
    </div>

    <Transition name="kg-fade">
      <div v-if="selected && !hideDetailPanel" class="kg-explore__panel">
        <div class="kg-explore__panel-hd">
          <span class="kg-explore__dot" :style="{ background: selected.type_color || '#64748b' }" />
          <div>
            <div class="kg-explore__panel-title">{{ selected.name }}</div>
            <div class="kg-explore__panel-sub">{{ selected.type_label || selected.type_code }}</div>
          </div>
          <n-button text size="tiny" @click="selected = null">关闭</n-button>
        </div>
        <div class="kg-explore__panel-body">
          <div class="kg-explore__stat"><span>实体 ID</span><code>{{ selected.id }}</code></div>
          <div class="kg-explore__stat"><span>类型 code</span><code>{{ selected.type_code }}</code></div>
          <div class="kg-explore__stat"><span>语义 URI</span><code class="kg-explore__uri">{{ selected.type_uri || '—' }}</code></div>
        </div>
        <n-space vertical :size="8">
          <n-button block size="small" secondary @click="focusNeighbors">以该实体为中心展开</n-button>
          <n-button block type="primary" secondary size="small" @click="emitTraceConcept">
            追溯所属概念 →
          </n-button>
        </n-space>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { loadEcharts } from "../../utils/echartsLoader.js";

const props = defineProps({
  graphData: { type: Object, default: () => ({ nodes: [], edges: [] }) },
  loading: Boolean,
  hideDetailPanel: { type: Boolean, default: false },
  selectedId: { type: String, default: "" },
});

const emit = defineEmits(["refresh", "focus-entity", "trace-concept", "select-entity"]);

const focusId = ref("");
const depth = ref(2);
const chartHost = ref(null);
const selected = ref(null);

let chart = null;

const COLOR_MAP = {
  blue: "#3b82f6",
  green: "#22c55e",
  purple: "#a855f7",
  orange: "#f97316",
  pink: "#ec4899",
  yellow: "#eab308",
  teal: "#14b8a6",
  indigo: "#6366f1",
  cyan: "#06b6d4",
  gray: "#94a3b8",
};

function resolveColor(c) {
  if (!c) return COLOR_MAP.blue;
  if (String(c).startsWith("#")) return c;
  return COLOR_MAP[c] || COLOR_MAP.blue;
}

function loadGraph() {
  if (!focusId.value) return;
  emit("refresh", focusId.value, depth.value);
}

function loadFullGraph() {
  focusId.value = "";
  emit("refresh", null, depth.value);
}

function clearLocal() {
  focusId.value = "";
  selected.value = null;
  chart?.clear();
  emit("refresh", "__clear__", 0);
}

function focusNeighbors() {
  if (!selected.value) return;
  focusId.value = selected.value.id;
  emit("refresh", selected.value.id, depth.value);
  emit("focus-entity", selected.value.id);
}

function emitTraceConcept() {
  if (!selected.value) return;
  emit("trace-concept", {
    code: selected.value.type_code,
    label: selected.value.type_label,
    type_uri: selected.value.type_uri,
    entity_id: selected.value.id,
    entity_name: selected.value.name,
  });
}

async function render() {
  if (!chartHost.value) return;
  const nodes = props.graphData?.nodes || [];
  const edges = props.graphData?.edges || [];
  if (!nodes.length) {
    chart?.clear();
    return;
  }

  const echarts = await loadEcharts();
  if (!chart) {
    chart = echarts.init(chartHost.value, undefined, { renderer: "canvas" });
    chart.on("click", (params) => {
      if (params.dataType !== "node") return;
      // 用当前 props / raw，避免 render 闭包里的 nodes 过期导致点选失效
      const id = params.data?.id;
      const node =
        params.data?.raw ||
        (props.graphData?.nodes || []).find((n) => n.id === id);
      if (!node) return;
      selected.value = {
        ...node,
        type_color: resolveColor(node.type_color),
      };
      emit("select-entity", selected.value);
    });
  }

  const categories = [];
  const catIndex = new Map();
  nodes.forEach((n) => {
    const key = n.type_code || "unknown";
    if (!catIndex.has(key)) {
      catIndex.set(key, categories.length);
      categories.push({ name: n.type_label || key });
    }
  });

  chart.setOption(
    {
      tooltip: {
        formatter(p) {
          if (p.dataType === "edge") {
            return `${p.data.source} —${p.data.name || ""}→ ${p.data.target}`;
          }
          const n = p.data?.raw || {};
          return `<b>${p.name}</b><br/>${n.type_label || n.type_code || ""}<br/>${n.type_uri || ""}`;
        },
      },
      legend: categories.length > 1 ? [{ data: categories.map((c) => c.name), type: "scroll" }] : undefined,
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          categories,
          data: nodes.map((n) => ({
            id: n.id,
            name: n.name,
            category: catIndex.get(n.type_code || "unknown"),
            symbolSize: props.selectedId === n.id ? 34 : 26,
            itemStyle: {
              color: resolveColor(n.type_color),
              borderColor: props.selectedId === n.id ? "#0f172a" : undefined,
              borderWidth: props.selectedId === n.id ? 3 : 0,
            },
            raw: n,
          })),
          links: edges.map((e) => ({
            source: e.from_entity_id,
            target: e.to_entity_id,
            name: e.type_label || e.type_code,
            lineStyle: {
              color: e.inferred ? "#94a3b8" : "#64748b",
              type: e.inferred ? "dashed" : "solid",
              curveness: 0.12,
            },
            label: { show: true, formatter: e.type_label || e.type_code, fontSize: 10 },
          })),
          label: { show: true, position: "bottom", fontSize: 11 },
          force: {
            repulsion: 260,
            edgeLength: [60, 140],
            gravity: 0.06,
          },
          emphasis: { focus: "adjacency" },
        },
      ],
    },
    true
  );
}

function onResize() {
  chart?.resize();
}

watch(
  () => props.graphData,
  () => nextTick(render),
  { deep: true }
);

watch(
  () => props.selectedId,
  () => nextTick(render)
);

onMounted(() => {
  nextTick(render);
  window.addEventListener("resize", onResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", onResize);
  chart?.dispose();
  chart = null;
});

defineExpose({
  setFocus(id) {
    focusId.value = id || "";
  },
  resize: () => chart?.resize(),
});
</script>

<style scoped>
.kg-explore {
  position: relative;
  height: 100%;
  min-height: 480px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--platform-border, #e5e7eb);
  border-radius: var(--platform-radius, 8px);
  background: var(--platform-bg-base, #fff);
  overflow: hidden;
}
.kg-explore__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 8px 12px;
  border-bottom: 1px solid var(--platform-border, #e5e7eb);
}
.kg-explore__chart {
  position: relative;
  flex: 1;
  min-height: 420px;
  width: 100%;
}
.kg-explore__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--platform-text-tertiary);
  font-size: 13px;
  pointer-events: none;
}
.kg-explore__panel {
  position: absolute;
  right: 12px;
  top: 56px;
  width: 300px;
  background: var(--platform-bg-elevated, #fff);
  border: 1px solid var(--platform-border, #e5e7eb);
  border-radius: 10px;
  padding: 14px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.12);
  z-index: 5;
}
.kg-explore__panel-hd {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.kg-explore__dot {
  width: 6px;
  height: 28px;
  border-radius: 3px;
  flex-shrink: 0;
}
.kg-explore__panel-title {
  font-weight: 680;
  font-size: 14px;
}
.kg-explore__panel-sub {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}
.kg-explore__panel-body {
  margin: 12px 0;
}
.kg-explore__stat {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 0;
  font-size: 12px;
  color: var(--platform-text-tertiary);
  border-bottom: 1px solid color-mix(in srgb, var(--platform-text) 6%, transparent);
}
.kg-explore__stat code {
  color: var(--platform-text);
  font-size: 11px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kg-explore__uri {
  word-break: break-all;
  white-space: normal !important;
  max-width: 180px;
}
.kg-fade-enter-active,
.kg-fade-leave-active {
  transition: opacity 0.18s ease;
}
.kg-fade-enter-from,
.kg-fade-leave-to {
  opacity: 0;
}
</style>
