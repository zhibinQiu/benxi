<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { NButton, NIcon, NTooltip } from "naive-ui";
import {
  AddOutline,
  LocateOutline,
  LockClosedOutline,
  LockOpenOutline,
  RemoveOutline,
  ScanOutline,
} from "@vicons/ionicons5";

const props = defineProps({
  layout: {
    type: Object,
    default: () => ({ nodes: [], edges: [], width: 400, height: 240 }),
  },
  selectedId: { type: String, default: null },
  typeColor: { type: Function, required: true },
});

const emit = defineEmits(["select"]);

const DRAG_THRESHOLD = 4;

const canvasRef = ref(null);
const transform = ref({ x: 40, y: 40, scale: 1 });
const dragOffsets = ref({});
const pinnedPositions = ref({});
const interaction = ref(null);
const lastNodeDragAt = ref(0);

const hasPinned = computed(() => Object.keys(pinnedPositions.value).length > 0);
const hasManualLayout = computed(
  () =>
    hasPinned.value ||
    Object.keys(dragOffsets.value).some((id) => {
      const o = dragOffsets.value[id];
      return o && (o.dx !== 0 || o.dy !== 0);
    })
);

const displayNodes = computed(() =>
  (props.layout.nodes || []).map((node) => {
    const pinned = pinnedPositions.value[node.id];
    if (pinned) {
      return { ...node, x: pinned.x, y: pinned.y, pinned: true };
    }
    const offset = dragOffsets.value[node.id] || { dx: 0, dy: 0 };
    return {
      ...node,
      x: node.x + offset.dx,
      y: node.y + offset.dy,
      pinned: false,
    };
  })
);

const MIN_SCALE = 0.2;
const MAX_SCALE = 3;

const graphSize = computed(() => ({
  width: Math.max(props.layout.width || 400, 320),
  height: Math.max(props.layout.height || 240, 200),
}));

const displayEdges = computed(() => {
  const posMap = Object.fromEntries(displayNodes.value.map((n) => [n.id, n]));
  return (props.layout.edges || [])
    .filter((e) => posMap[e.from_entity_id] && posMap[e.to_entity_id])
    .map((e) => {
      const from = posMap[e.from_entity_id];
      const to = posMap[e.to_entity_id];
      const x1 = from.x + from.w;
      const y1 = from.y + from.h / 2;
      const x2 = to.x;
      const y2 = to.y + to.h / 2;
      return {
        ...e,
        x1,
        y1,
        x2,
        y2,
        mx: (x1 + x2) / 2,
        my: (y1 + y2) / 2 - 10,
        active:
          props.selectedId === e.from_entity_id ||
          props.selectedId === e.to_entity_id,
      };
    });
});

const transformStyle = computed(
  () =>
    `translate(${transform.value.x}px, ${transform.value.y}px) scale(${transform.value.scale})`
);

function clientToGraph(clientX, clientY) {
  const el = canvasRef.value;
  if (!el) return { x: 0, y: 0 };
  const rect = el.getBoundingClientRect();
  const localX = clientX - rect.left;
  const localY = clientY - rect.top;
  return {
    x: (localX - transform.value.x) / transform.value.scale,
    y: (localY - transform.value.y) / transform.value.scale,
  };
}

function onPointerDown(event) {
  if (event.button !== 0) return;
  const target = event.target?.closest?.("[data-kg-node]");
  if (target) {
    const nodeId = target.getAttribute("data-kg-node");
    const node = displayNodes.value.find((n) => n.id === nodeId);
    if (!node) return;
    const pt = clientToGraph(event.clientX, event.clientY);
    interaction.value = {
      kind: "node",
      nodeId,
      moved: false,
      isPinned: Boolean(pinnedPositions.value[nodeId]),
      startClient: { x: event.clientX, y: event.clientY },
      grab: { x: pt.x - node.x, y: pt.y - node.y },
    };
    target.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    return;
  }
  interaction.value = {
    kind: "pan",
    startClient: { x: event.clientX, y: event.clientY },
    startTransform: { ...transform.value },
  };
}

function onPointerMove(event) {
  const state = interaction.value;
  if (!state) return;
  if (state.kind === "pan") {
    const dx = event.clientX - state.startClient.x;
    const dy = event.clientY - state.startClient.y;
    transform.value = {
      ...state.startTransform,
      x: state.startTransform.x + dx,
      y: state.startTransform.y + dy,
    };
    return;
  }
  if (state.kind === "node") {
    const dx = event.clientX - state.startClient.x;
    const dy = event.clientY - state.startClient.y;
    if (!state.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    state.moved = true;
    const pt = clientToGraph(event.clientX, event.clientY);
    const nx = pt.x - state.grab.x;
    const ny = pt.y - state.grab.y;
    if (state.isPinned || pinnedPositions.value[state.nodeId]) {
      pinnedPositions.value = {
        ...pinnedPositions.value,
        [state.nodeId]: { x: nx, y: ny },
      };
      return;
    }
    const base = props.layout.nodes.find((n) => n.id === state.nodeId);
    if (!base) return;
    dragOffsets.value = {
      ...dragOffsets.value,
      [state.nodeId]: {
        dx: nx - base.x,
        dy: ny - base.y,
      },
    };
  }
}

function onPointerUp() {
  if (interaction.value?.kind === "node" && interaction.value.moved) {
    lastNodeDragAt.value = Date.now();
  }
  interaction.value = null;
}

function pinAllPositions() {
  const next = { ...pinnedPositions.value };
  for (const node of displayNodes.value) {
    next[node.id] = { x: node.x, y: node.y };
  }
  pinnedPositions.value = next;
  dragOffsets.value = {};
}

function unpinAll() {
  pinnedPositions.value = {};
  dragOffsets.value = {};
}

function onNodeDblClick(nodeId) {
  if (Date.now() - lastNodeDragAt.value < 320) return;
  emit("select", nodeId);
}

function onWheel(event) {
  event.preventDefault();
  const el = canvasRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;
  const prev = transform.value.scale;
  const factor = event.deltaY > 0 ? 0.92 : 1.08;
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev * factor));
  const ratio = next / prev;
  transform.value = {
    scale: next,
    x: mx - (mx - transform.value.x) * ratio,
    y: my - (my - transform.value.y) * ratio,
  };
}

function zoomBy(factor) {
  const el = canvasRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const mx = rect.width / 2;
  const my = rect.height / 2;
  const prev = transform.value.scale;
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev * factor));
  const ratio = next / prev;
  transform.value = {
    scale: next,
    x: mx - (mx - transform.value.x) * ratio,
    y: my - (my - transform.value.y) * ratio,
  };
}

function fitView() {
  const el = canvasRef.value;
  const nodes = displayNodes.value;
  if (!el || !nodes.length) return;
  const rect = el.getBoundingClientRect();
  const padding = 48;
  const minX = Math.min(...nodes.map((n) => n.x));
  const minY = Math.min(...nodes.map((n) => n.y));
  const maxX = Math.max(...nodes.map((n) => n.x + n.w));
  const maxY = Math.max(...nodes.map((n) => n.y + n.h));
  const contentW = Math.max(maxX - minX, 1);
  const contentH = Math.max(maxY - minY, 1);
  const scale = Math.min(
    (rect.width - padding * 2) / contentW,
    (rect.height - padding * 2) / contentH,
    1.4
  );
  const clamped = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
  transform.value = {
    scale: clamped,
    x: (rect.width - contentW * clamped) / 2 - minX * clamped,
    y: (rect.height - contentH * clamped) / 2 - minY * clamped,
  };
}

function resetView() {
  dragOffsets.value = {};
  pinnedPositions.value = {};
  transform.value = { x: 40, y: 40, scale: 1 };
  fitView();
}

function focusNode(nodeId) {
  const node = displayNodes.value.find((n) => n.id === nodeId);
  const el = canvasRef.value;
  if (!node || !el) return;
  const rect = el.getBoundingClientRect();
  const scale = transform.value.scale;
  transform.value = {
    scale,
    x: rect.width / 2 - (node.x + node.w / 2) * scale,
    y: rect.height / 2 - (node.y + node.h / 2) * scale,
  };
}

watch(
  () => props.layout.nodes?.length || 0,
  (len, prev) => {
    if (len > 0 && !prev) fitView();
  }
);

defineExpose({ fitView, resetView, focusNode });

if (typeof window !== "undefined") {
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
}

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
  }
});
</script>

<template>
  <div class="kg-canvas">
    <div
      ref="canvasRef"
      class="kg-canvas__viewport"
      :class="{
        'kg-canvas__viewport--dragging':
          interaction?.kind === 'pan' ||
          (interaction?.kind === 'node' && interaction?.moved),
      }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @wheel.prevent="onWheel"
    >
      <div class="kg-canvas__grid" aria-hidden="true" />
      <div class="kg-canvas__stage" :style="{ transform: transformStyle }">
        <svg
          class="kg-canvas__svg"
          :width="graphSize.width"
          :height="graphSize.height"
        >
          <defs>
            <marker
              id="kg-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="7"
              refY="4"
              orient="auto"
            >
              <path d="M0,0 L8,4 L0,8 Z" fill="var(--kg-edge-color, #94a3b8)" />
            </marker>
            <marker
              id="kg-arrow-active"
              markerWidth="8"
              markerHeight="8"
              refX="7"
              refY="4"
              orient="auto"
            >
              <path d="M0,0 L8,4 L0,8 Z" fill="var(--platform-accent, #2563eb)" />
            </marker>
          </defs>
          <g v-for="edge in displayEdges" :key="edge.id">
            <line
              :x1="edge.x1"
              :y1="edge.y1"
              :x2="edge.x2"
              :y2="edge.y2"
              class="kg-canvas__edge"
              :class="{ active: edge.active }"
              :marker-end="edge.active ? 'url(#kg-arrow-active)' : 'url(#kg-arrow)'"
            />
            <text :x="edge.mx" :y="edge.my" class="kg-canvas__edge-label">
              {{ edge.relation_type_label }}
            </text>
          </g>
          <g
            v-for="node in displayNodes"
            :key="node.id"
            class="kg-canvas__node"
            :class="{
              active: selectedId === node.id,
              pinned: node.pinned,
              dragging: interaction?.kind === 'node' && interaction?.nodeId === node.id && interaction?.moved,
            }"
            :transform="`translate(${node.x}, ${node.y})`"
            :data-kg-node="node.id"
            @dblclick.stop="onNodeDblClick(node.id)"
          >
            <rect
              :width="node.w"
              :height="node.h"
              rx="8"
              class="kg-canvas__node-box"
            />
            <circle
              cx="12"
              cy="18"
              r="5"
              :fill="typeColor(node.type_color)"
            />
            <text x="24" y="22" class="kg-canvas__node-label">
              {{ node.name.length > 14 ? `${node.name.slice(0, 13)}…` : node.name }}
            </text>
            <circle
              v-if="node.pinned"
              :cx="node.w - 10"
              cy="10"
              r="3"
              class="kg-canvas__node-pin"
            />
          </g>
        </svg>
      </div>
    </div>

    <div class="kg-canvas__controls">
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary circle @click="zoomBy(1.15)">
            <template #icon><n-icon :component="AddOutline" /></template>
          </n-button>
        </template>
        放大
      </n-tooltip>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary circle @click="zoomBy(0.87)">
            <template #icon><n-icon :component="RemoveOutline" /></template>
          </n-button>
        </template>
        缩小
      </n-tooltip>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary circle @click="fitView">
            <template #icon><n-icon :component="ScanOutline" /></template>
          </n-button>
        </template>
        适应窗口
      </n-tooltip>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button
            size="tiny"
            quaternary
            circle
            :type="hasManualLayout ? 'primary' : 'default'"
            @click="pinAllPositions"
          >
            <template #icon><n-icon :component="LockClosedOutline" /></template>
          </n-button>
        </template>
        固定当前布局
      </n-tooltip>
      <n-tooltip v-if="hasPinned" trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary circle @click="unpinAll">
            <template #icon><n-icon :component="LockOpenOutline" /></template>
          </n-button>
        </template>
        解除全部固定
      </n-tooltip>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-button size="tiny" quaternary circle @click="resetView">
            <template #icon><n-icon :component="LocateOutline" /></template>
          </n-button>
        </template>
        重置布局
      </n-tooltip>
    </div>

    <div class="kg-canvas__hint">
      滚轮缩放 · 空白拖拽平移 · 按住节点拖拽 · 双击节点进入
      <span v-if="hasPinned" class="kg-canvas__hint-pinned">已固定 {{ Object.keys(pinnedPositions).length }} 个节点</span>
    </div>
  </div>
</template>

<style scoped>
.kg-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  --kg-edge-color: color-mix(in srgb, var(--platform-text-tertiary) 70%, transparent);
}

.kg-canvas__viewport {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
  cursor: grab;
  border-radius: 0;
  background: color-mix(in srgb, var(--platform-bg) 88%, #fff);
}

.kg-canvas__viewport--dragging {
  cursor: grabbing;
}

.kg-canvas__grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(
    circle,
    color-mix(in srgb, var(--platform-border) 55%, transparent) 1px,
    transparent 1px
  );
  background-size: 20px 20px;
  pointer-events: none;
}

.kg-canvas__stage {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  will-change: transform;
}

.kg-canvas__svg {
  display: block;
  overflow: visible;
}

.kg-canvas__edge {
  stroke: var(--kg-edge-color);
  stroke-width: 1.5;
  fill: none;
}

.kg-canvas__edge.active {
  stroke: var(--platform-accent);
  stroke-width: 2;
}

.kg-canvas__edge-label {
  font-size: 10px;
  fill: var(--platform-text-tertiary);
  text-anchor: middle;
  pointer-events: none;
}

.kg-canvas__node {
  cursor: grab;
}

.kg-canvas__node.dragging {
  cursor: grabbing;
}

.kg-canvas__node-box {
  fill: var(--platform-surface, #fff);
  stroke: color-mix(in srgb, var(--platform-border) 90%, transparent);
  stroke-width: 1;
  filter: drop-shadow(0 2px 6px color-mix(in srgb, #000 6%, transparent));
}

.kg-canvas__node.active .kg-canvas__node-box {
  stroke: var(--platform-accent);
  stroke-width: 2;
  fill: color-mix(in srgb, var(--platform-accent) 6%, var(--platform-surface, #fff));
}

.kg-canvas__node.pinned .kg-canvas__node-box {
  stroke-dasharray: 4 3;
  stroke: color-mix(in srgb, var(--platform-accent) 70%, var(--platform-border));
}

.kg-canvas__node-pin {
  fill: var(--platform-accent);
  pointer-events: none;
}

.kg-canvas__node-label {
  font-size: 12px;
  font-weight: 500;
  fill: var(--platform-text-primary);
  pointer-events: none;
  user-select: none;
}

.kg-canvas__hint-pinned {
  margin-left: 8px;
  color: var(--platform-accent);
}

.kg-canvas__controls {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  border: 1px solid var(--platform-border);
  background: color-mix(in srgb, var(--platform-surface, #fff) 92%, transparent);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 16px color-mix(in srgb, #000 8%, transparent);
}

.kg-canvas__hint {
  position: absolute;
  left: 12px;
  bottom: 10px;
  font-size: 11px;
  color: var(--platform-text-tertiary);
  padding: 4px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--platform-surface, #fff) 88%, transparent);
  border: 1px solid var(--platform-border);
  pointer-events: none;
}
</style>
