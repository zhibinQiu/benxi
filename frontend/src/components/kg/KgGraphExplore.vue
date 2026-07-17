<template>
  <n-space vertical>
    <n-space justify="space-between" align="center">
      <n-space align="center">
        <n-input v-model:value="focusId" placeholder="输入实体 ID 聚焦" style="width: 300px" />
        <n-input-number v-model:value="depth" :min="1" :max="5" style="width: 80px" />
        <n-button @click="loadGraph">加载子图</n-button>
        <n-button @click="loadFullGraph">全图</n-button>
      </n-space>
      <n-space>
        <n-statistic :value="graphData.nodes?.length || 0" title="节点" />
        <n-statistic :value="graphData.edges?.length || 0" title="边" />
      </n-space>
    </n-space>

    <div class="graph-canvas" ref="graphContainer">
      <n-spin :show="loading" style="display: flex; justify-content: center; align-items: center; height: 100%;">
        <div v-if="!graphData.nodes?.length && !loading" style="color: #999; text-align: center; padding: 60px;">
          图谱为空，请先创建实体
        </div>
        <div v-else ref="svgContainer" class="svg-graph"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
          @wheel.prevent="onWheel"
        ></div>
      </n-spin>
    </div>
  </n-space>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from "vue";
import { useMessage } from "naive-ui";

const props = defineProps({
  graphData: { type: Object, default: () => ({ nodes: [], edges: [] }) },
  loading: Boolean,
});

const emit = defineEmits(["refresh"]);

const message = useMessage();
const focusId = ref("");
const depth = ref(2);
const graphContainer = ref(null);
const svgContainer = ref(null);

// ── 拖拽与缩放状态 ──

const pan = ref({ x: 0, y: 0 });
const scale = ref(1);
let isDragging = false;
let dragStart = { x: 0, y: 0 };
let panStart = { x: 0, y: 0 };

function onMouseDown(e) {
  isDragging = true;
  dragStart = { x: e.clientX, y: e.clientY };
  panStart = { x: pan.value.x, y: pan.value.y };
}

function onMouseMove(e) {
  if (!isDragging) return;
  const dx = e.clientX - dragStart.x;
  const dy = e.clientY - dragStart.y;
  pan.value = { x: panStart.x + dx, y: panStart.y + dy };
  applyTransform();
}

function onMouseUp() {
  isDragging = false;
}

function onWheel(e) {
  const delta = e.deltaY > 0 ? -0.1 : 0.1;
  const newScale = Math.min(3, Math.max(0.2, scale.value + delta));
  scale.value = newScale;
  applyTransform();
}

function applyTransform() {
  const container = svgContainer.value;
  if (!container) return;
  const g = container.querySelector("svg g.graph-group");
  if (g) {
    g.setAttribute("transform", `translate(${pan.value.x}, ${pan.value.y}) scale(${scale.value})`);
  }
}

function loadGraph() {
  if (!focusId.value) {
    message.warning("请输入实体 ID");
    return;
  }
  pan.value = { x: 0, y: 0 };
  scale.value = 1;
  emit("refresh", focusId.value, depth.value);
}

function loadFullGraph() {
  focusId.value = "";
  pan.value = { x: 0, y: 0 };
  scale.value = 1;
  emit("refresh", null, depth.value);
}

// ── 图谱渲染 ──
function renderGraph() {
  const container = svgContainer.value;
  if (!container) return;

  const { nodes = [], edges = [] } = props.graphData;

  if (nodes.length === 0) {
    container.innerHTML = "";
    return;
  }

  const width = container.clientWidth || 800;
  const height = container.clientHeight || 500;
  const padding = 60;

  // 圆形布局
  const centerX = 0;
  const centerY = 0;
  const radius = Math.min(width, height) / 2 - padding;

  const nodePositions = {};
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    nodePositions[node.id] = {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  });

  let svg = `<svg width="${width}" height="${height}" style="background: #fafafa; cursor: ${isDragging ? 'grabbing' : 'grab'}; display: block;">
    <g class="graph-group" transform="translate(${pan.value.x}, ${pan.value.y}) scale(${scale.value})">`;

  // 绘制边
  edges.forEach((edge) => {
    const from = nodePositions[edge.from_entity_id];
    const to = nodePositions[edge.to_entity_id];
    if (!from || !to) return;
    const stroke = edge.inferred ? "#aaa" : "#666";
    svg += `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"
      stroke="${stroke}" stroke-width="1.5" stroke-dasharray="${edge.inferred ? '4,3' : ''}"
      opacity="0.6"/>`;
    const mx = (from.x + to.x) / 2;
    const my = (from.y + to.y) / 2;
    svg += `<text x="${mx}" y="${my - 6}" text-anchor="middle" font-size="10"
      fill="#666">${edge.type_code}</text>`;
  });

  // 绘制节点
  nodes.forEach((node) => {
    const pos = nodePositions[node.id];
    if (!pos) return;
    const color = node.type_color || "#409eff";
    svg += `<circle cx="${pos.x}" cy="${pos.y}" r="20" fill="${color}" opacity="0.9"
      stroke="#fff" stroke-width="2"/>`;
    svg += `<text x="${pos.x}" y="${pos.y + 5}" text-anchor="middle" font-size="10"
      fill="#fff" font-weight="bold">${node.name.slice(0, 6)}</text>`;
    svg += `<text x="${pos.x}" y="${pos.y - 28}" text-anchor="middle" font-size="10"
      fill="#333">${node.type_label || node.type_code}</text>`;
  });

  svg += `</g></svg>`;
  container.innerHTML = svg;
}

watch(
  () => props.graphData,
  () => nextTick(renderGraph),
  { deep: true }
);

onMounted(() => {
  nextTick(renderGraph);
});
</script>

<style scoped>
.graph-canvas {
  height: 500px;
  border: 1px solid #eee;
  border-radius: 8px;
  overflow: hidden;
  background: #fafafa;
}

.svg-graph {
  width: 100%;
  height: 100%;
  user-select: none;
}
</style>
