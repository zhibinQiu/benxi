<template>
  <div class="semantic-viz">
    <div class="semantic-viz__toolbar">
      <n-space align="center" :wrap="false">
        <n-tag size="small" :bordered="false">{{ isZh ? "语义模型" : "Schema" }}</n-tag>
        <n-text depth="3" style="font-size: 12px">
          <template v-if="viewMode === 'empty'">
            {{ isZh ? "未加载图（节约内存）" : "Graph not loaded" }}
          </template>
          <template v-else-if="isZh">
            概念 {{ displayStats.classCount }} · 关系边 {{ displayStats.edgeCount }}
            <template v-if="viewMode === 'focus'"> · 聚焦</template>
          </template>
          <template v-else>
            Class {{ displayStats.classCount }} · Edges {{ displayStats.edgeCount }}
            <template v-if="viewMode === 'focus'"> · focused</template>
          </template>
        </n-text>
      </n-space>
      <n-space>
        <n-button
          v-if="viewMode !== 'empty'"
          size="tiny"
          quaternary
          @click="clearGraph"
        >
          {{ isZh ? "清空" : "Clear" }}
        </n-button>
        <n-button size="tiny" quaternary :loading="loading" @click="reload">
          {{ isZh ? "刷新" : "Refresh" }}
        </n-button>
      </n-space>
    </div>

    <div ref="chartHost" class="semantic-viz__chart">
      <div v-if="viewMode === 'empty' && !loading" class="semantic-viz__empty">
        {{
          isZh
            ? "默认不加载图谱。点击「刷新」展示全部概念与关系，或从左侧选择一项查看关联。"
            : "Graph stays empty by default. Click Refresh for the full schema, or select an item on the left."
        }}
      </div>
    </div>

    <Transition name="sem-fade">
      <div v-if="selected && !hideDetailPanel" class="semantic-viz__panel">
        <div class="semantic-viz__panel-hd">
          <span class="semantic-viz__dot" :style="{ background: selected.color }" />
          <div>
            <div class="semantic-viz__panel-title">{{ selected.label }}</div>
            <div class="semantic-viz__panel-sub">{{ selected.type_uri || selected.code }}</div>
          </div>
          <n-button text size="tiny" @click="selected = null">关闭</n-button>
        </div>
        <div class="semantic-viz__panel-body">
          <div class="semantic-viz__stat"><span>语义 ID</span><code>{{ selected.code }}</code></div>
          <div class="semantic-viz__stat"><span>实例数</span><strong>{{ selected.entity_count || 0 }}</strong></div>
          <div v-if="selected.property_keys?.length" class="semantic-viz__sec">属性</div>
          <div v-if="selected.property_keys?.length" class="semantic-viz__tags">
            <n-tag v-for="k in selected.property_keys" :key="k" size="tiny" :bordered="false">{{ k }}</n-tag>
          </div>
          <div v-if="relatedProps.length" class="semantic-viz__sec">关联关系</div>
          <div v-for="p in relatedProps" :key="p.id" class="semantic-viz__rel">
            <span>{{ p.label }}</span>
            <n-text depth="3" style="font-size: 11px">{{ p.dir }}</n-text>
          </div>
        </div>
        <n-button block type="primary" secondary size="small" @click="emitExplore(selected)">
          查看该概念的实例 →
        </n-button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { loadEcharts } from "../../utils/echartsLoader.js";
import { useI18n } from "../../composables/useI18n";

const props = defineProps({
  hideDetailPanel: { type: Boolean, default: false },
  selectedCode: { type: String, default: "" },
  /** 'entity' | 'relation' */
  selectedKind: { type: String, default: "entity" },
  entityTypes: { type: Array, default: () => [] },
  relationTypes: { type: Array, default: () => [] },
});

const emit = defineEmits(["explore-concept", "select-concept"]);
const { locale } = useI18n();
const isZh = computed(() => locale.value === "zh");

const chartHost = ref(null);
const loading = ref(false);
/** empty | full | focus */
const viewMode = ref("empty");
const graph = ref({ nodes: [], edges: [] });
const selected = ref(null);

const displayStats = computed(() => ({
  classCount: graph.value.nodes?.length || 0,
  edgeCount: graph.value.edges?.length || 0,
}));

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

function nodeFromEntity(et) {
  return {
    id: et.code,
    code: et.code,
    label: et.label || et.code,
    kind: "class",
    color: et.color,
    icon: et.icon,
    entity_count: et.entity_count || 0,
    property_keys: Object.keys(et.property_schema || {}),
  };
}

function propertyEdges(rt, domainCodes, rangeCodes) {
  const edges = [];
  for (const src of domainCodes) {
    for (const dst of rangeCodes) {
      edges.push({
        id: `prop:${rt.code}:${src}->${dst}`,
        source: src,
        target: dst,
        kind: "property",
        label: rt.label || rt.code,
        code: rt.code,
        transitive: !!rt.transitive,
        symmetric: !!rt.symmetric,
      });
    }
  }
  return edges;
}

/** 完整语义图：全部概念 + 全部关系边（本地由列表构建，不请求 schema-graph） */
function buildFullGraph() {
  const nodes = props.entityTypes.map(nodeFromEntity);
  const codeSet = new Set(nodes.map((n) => n.id));
  const edges = [];
  for (const rt of props.relationTypes) {
    const domains = (rt.domain_types || []).filter((c) => codeSet.has(c));
    const ranges = (rt.range_types || []).filter((c) => codeSet.has(c));
    // 无 domain/range 时跳过，避免空边
    if (!domains.length || !ranges.length) continue;
    edges.push(...propertyEdges(rt, domains, ranges));
  }
  return { nodes, edges };
}

/** 仅与某概念相关的子图 */
function buildFocusEntityGraph(code) {
  const et = props.entityTypes.find((e) => e.code === code);
  if (!et) return { nodes: [], edges: [] };

  const relatedCodes = new Set([code]);
  const edges = [];
  for (const rt of props.relationTypes) {
    const domains = rt.domain_types || [];
    const ranges = rt.range_types || [];
    const asDomain = domains.includes(code);
    const asRange = ranges.includes(code);
    if (!asDomain && !asRange) continue;
    const srcs = asDomain ? [code] : domains.filter((c) => props.entityTypes.some((e) => e.code === c));
    const dsts = asRange ? [code] : ranges.filter((c) => props.entityTypes.some((e) => e.code === c));
    for (const src of srcs) relatedCodes.add(src);
    for (const dst of dsts) relatedCodes.add(dst);
    edges.push(...propertyEdges(rt, srcs, dsts));
  }

  const nodes = props.entityTypes
    .filter((e) => relatedCodes.has(e.code))
    .map(nodeFromEntity);
  return { nodes, edges };
}

/** 仅与某关系类型相关的子图：domain ∪ range */
function buildFocusRelationGraph(code) {
  const rt = props.relationTypes.find((r) => r.code === code);
  if (!rt) return { nodes: [], edges: [] };
  const domains = rt.domain_types || [];
  const ranges = rt.range_types || [];
  const codes = new Set([...domains, ...ranges]);
  const nodes = props.entityTypes
    .filter((e) => codes.has(e.code))
    .map(nodeFromEntity);
  // 若 domain/range 引用了尚未在列表中的类型，补孤立节点
  for (const c of codes) {
    if (!nodes.some((n) => n.id === c)) {
      nodes.push({
        id: c,
        code: c,
        label: c,
        kind: "class",
        color: "gray",
        entity_count: 0,
        property_keys: [],
      });
    }
  }
  const edges =
    domains.length && ranges.length ? propertyEdges(rt, domains, ranges) : [];
  return { nodes, edges };
}

const relatedProps = computed(() => {
  if (!selected.value) return [];
  const code = selected.value.code;
  return (graph.value.edges || [])
    .filter((e) => e.kind === "property" && (e.source === code || e.target === code))
    .map((e) => ({
      id: e.id,
      label: e.label || e.code,
      dir: e.source === code ? `→ ${e.target}` : `← ${e.source}`,
    }));
});

let chart = null;

function applyGraph(next, mode) {
  graph.value = next || { nodes: [], edges: [] };
  viewMode.value = mode;
}

function clearGraph() {
  selected.value = null;
  applyGraph({ nodes: [], edges: [] }, "empty");
  chart?.clear();
}

/** 刷新：展示全部概念与关系 */
async function reload() {
  loading.value = true;
  try {
    applyGraph(buildFullGraph(), "full");
    await nextTick();
    await render();
  } finally {
    loading.value = false;
  }
}

/** 按左侧选择聚焦关联子图 */
async function focusSelection(kind, code) {
  if (!code) {
    // 取消选择时不自动清图：保留当前 full/focus，由用户点清空
    return;
  }
  loading.value = true;
  try {
    const next =
      kind === "relation" ? buildFocusRelationGraph(code) : buildFocusEntityGraph(code);
    applyGraph(next, "focus");
    const focusNode = (next.nodes || []).find((n) => n.id === code);
    if (focusNode && kind === "entity") {
      selected.value = { ...focusNode, color: resolveColor(focusNode.color) };
    } else {
      selected.value = null;
    }
    await nextTick();
    await render();
  } finally {
    loading.value = false;
  }
}

function emitExplore(node) {
  emit("explore-concept", {
    code: node.code,
    label: node.label,
    type_uri: node.type_uri,
  });
}

async function render() {
  if (!chartHost.value) return;
  const nodesRaw = graph.value.nodes || [];
  const edgesRaw = graph.value.edges || [];

  if (!nodesRaw.length) {
    chart?.clear();
    return;
  }

  const echarts = await loadEcharts();
  if (!chart) {
    chart = echarts.init(chartHost.value, undefined, { renderer: "canvas" });
    chart.on("click", (params) => {
      if (params.dataType !== "node") return;
      const node = (graph.value.nodes || []).find((n) => n.id === params.data.id);
      if (!node) return;
      selected.value = { ...node, color: resolveColor(node.color) };
      emit("select-concept", selected.value);
    });
  }

  const nodes = nodesRaw.map((n) => ({
    id: n.id,
    name: n.label || n.code,
    value: Math.max(1, n.entity_count || 1),
    symbolSize: 28 + Math.min(24, (n.entity_count || 0) * 2),
    category: 0,
    itemStyle: {
      color: resolveColor(n.color),
      borderColor: props.selectedCode && props.selectedCode === n.code ? "#0f172a" : undefined,
      borderWidth: props.selectedCode && props.selectedCode === n.code ? 3 : 0,
    },
    label: { show: true, formatter: "{b}" },
    raw: n,
  }));

  const links = edgesRaw.map((e) => ({
    source: e.source,
    target: e.target,
    name: e.label || e.code,
    lineStyle: {
      color: e.kind === "subClassOf" ? "#94a3b8" : "#64748b",
      type: e.kind === "subClassOf" ? "dashed" : "solid",
      width: e.kind === "subClassOf" ? 1.5 : 2,
      curveness: 0.15,
    },
    label: {
      show: true,
      formatter: e.label || e.code,
      fontSize: 10,
    },
  }));

  chart.setOption(
    {
      tooltip: {
        formatter(p) {
          if (p.dataType === "edge") {
            return `${p.data.source} —${p.data.name || ""}→ ${p.data.target}`;
          }
          const n = p.data?.raw || {};
          return `<b>${p.name}</b><br/>code: ${n.code || p.data.id}<br/>实例: ${n.entity_count || 0}`;
        },
      },
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          data: nodes,
          links,
          categories: [{ name: "Class" }],
          label: {
            show: true,
            position: "bottom",
            fontSize: 11,
            color: "var(--platform-text, #334155)",
          },
          force: {
            repulsion: 320,
            edgeLength: [80, 160],
            gravity: 0.08,
          },
          emphasis: {
            focus: "adjacency",
            lineStyle: { width: 3 },
          },
        },
      ],
    },
    true
  );
}

function onResize() {
  chart?.resize();
}

onMounted(() => {
  // 默认不加载图，节约内存与请求
  window.addEventListener("resize", onResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", onResize);
  chart?.dispose();
  chart = null;
});

watch(
  () => [props.selectedCode, props.selectedKind],
  ([code, kind]) => {
    if (code) focusSelection(kind || "entity", code);
  }
);

watch(
  () => [props.entityTypes, props.relationTypes],
  () => {
    if (viewMode.value === "full") {
      applyGraph(buildFullGraph(), "full");
      nextTick(render);
    } else if (viewMode.value === "focus" && props.selectedCode) {
      focusSelection(props.selectedKind || "entity", props.selectedCode);
    }
  },
  { deep: true }
);

defineExpose({
  reload,
  clearGraph,
  focusSelection,
  resize: () => {
    chart?.resize();
  },
});
</script>

<style scoped>
.semantic-viz {
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
.semantic-viz__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--platform-border, #e5e7eb);
}
.semantic-viz__chart {
  position: relative;
  flex: 1;
  min-height: 420px;
  width: 100%;
}
.semantic-viz__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  text-align: center;
  color: var(--platform-text-tertiary);
  font-size: 13px;
  line-height: 1.6;
  pointer-events: none;
}
.semantic-viz__panel {
  position: absolute;
  right: 12px;
  top: 52px;
  width: 280px;
  max-height: calc(100% - 72px);
  overflow: auto;
  background: var(--platform-bg-elevated, #fff);
  border: 1px solid var(--platform-border, #e5e7eb);
  border-radius: 10px;
  padding: 14px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.12);
  z-index: 5;
}
.semantic-viz__panel-hd {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.semantic-viz__dot {
  width: 6px;
  height: 28px;
  border-radius: 3px;
  flex-shrink: 0;
}
.semantic-viz__panel-title {
  font-weight: 680;
  font-size: 14px;
  color: var(--platform-text);
}
.semantic-viz__panel-sub {
  font-size: 11px;
  color: var(--platform-text-tertiary);
  word-break: break-all;
  margin-top: 2px;
}
.semantic-viz__panel-body {
  margin: 12px 0;
  font-size: 12px;
}
.semantic-viz__stat {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--platform-text) 6%, transparent);
  color: var(--platform-text-tertiary);
}
.semantic-viz__stat code,
.semantic-viz__stat strong {
  color: var(--platform-text);
  font-size: 11px;
}
.semantic-viz__sec {
  margin-top: 10px;
  margin-bottom: 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--platform-text-secondary);
}
.semantic-viz__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.semantic-viz__rel {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.sem-fade-enter-active,
.sem-fade-leave-active {
  transition: opacity 0.18s ease;
}
.sem-fade-enter-from,
.sem-fade-leave-to {
  opacity: 0;
}
</style>
