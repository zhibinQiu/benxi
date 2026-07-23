<template>
  <div class="onto-map" ref="containerRef" @mouseup="onDragEnd" @mousemove="onDragMove" @mouseleave="onDragEnd">

    <svg class="onto-map__svg" viewBox="0 0 900 700" preserveAspectRatio="xMidYMid meet">

      <!-- ── DEFS ── -->
      <defs>
        <pattern id="onto-grid" width="36" height="36" patternUnits="userSpaceOnUse">
          <path d="M 36 0 L 0 0 0 36" fill="none" class="onto-map__grid-line"/>
        </pattern>
        <filter id="onto-shadow" x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.18"/>
        </filter>
      </defs>

      <!-- ── 背景 ── -->
      <rect width="900" height="700" class="onto-map__canvas" rx="10"/>
      <rect width="900" height="700" fill="url(#onto-grid)" rx="10" opacity="0.55"/>

      <!-- ── 关系连线（先画，节点在上层） ── -->
      <g v-for="(rel, ri) in relationPaths" :key="'rel-'+ri">
        <marker :id="`arrow-${ri}`" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
          <path d="M0,1.5 L8,5 L0,8.5 Z" :fill="rel.color"/>
        </marker>
        <!-- 宽底边增强可见性 -->
        <path
          :d="rel.path"
          :stroke="rel.color"
          stroke-width="8" fill="none" stroke-linecap="round"
          :opacity="relHovered === rel.code ? 0.28 : 0.12"
        />
        <!-- 主边 -->
        <path
          :d="rel.path"
          :stroke="rel.color"
          :stroke-width="relHovered === rel.code ? 3.5 : 2.25"
          fill="none" stroke-linecap="round"
          :opacity="relHovered === rel.code ? 1 : 0.78"
          class="onto-map__rel-path"
          :marker-end="`url(#arrow-${ri})`"
          @mouseenter="relHovered = rel.code"
          @mouseleave="relHovered = null"
          @click.stop="openRel(rel)"
        />
        <!-- 标签芯片 -->
        <g
          class="onto-map__rel-chip"
          :opacity="relHovered === rel.code ? 1 : 0.92"
          @mouseenter="relHovered = rel.code"
          @mouseleave="relHovered = null"
          @click.stop="openRel(rel)"
        >
          <rect
            :x="rel.labelX - rel.labelW / 2 - 8" :y="rel.labelY - 11"
            :width="rel.labelW + 16" height="22" rx="11"
            class="onto-map__chip-bg"
            :stroke="rel.color"
            stroke-width="1.25"
          />
          <text
            :x="rel.labelX" :y="rel.labelY + 4"
            :fill="rel.color"
            font-size="12" font-weight="700" text-anchor="middle"
            class="onto-map__rel-label"
          >{{ rel.label }}</text>
        </g>
      </g>

      <!-- ── 实体节点 ── -->
      <g v-for="(et, ei) in nodes" :key="'et-'+ei"
        class="onto-map__node-group"
        :class="{ 'onto-map__node-group--active': activeEntityCode === et.code }"
        filter="url(#onto-shadow)"
        @mousedown.stop="onNodeMouseDown($event, et)"
        @touchstart.stop.prevent="onTouchStart($event, et)"
      >
        <!-- 外光晕 -->
        <circle
          :cx="et.x" :cy="et.y" r="42"
          :fill="et.color"
          :opacity="activeEntityCode === et.code ? 0.22 : 0.12"
        />
        <!-- 主圆：实色填充 + 白边，保证任意主题下可读 -->
        <circle
          :cx="et.x" :cy="et.y" r="28"
          :fill="et.color"
          class="onto-map__node-fill"
          :stroke-width="activeEntityCode === et.code ? 3.5 : 2.5"
        />
        <!-- icon -->
        <text
          :x="et.x" :y="et.y + 1"
          font-size="22" text-anchor="middle" dominant-baseline="central"
          class="onto-map__node-icon"
        >{{ et.icon }}</text>
        <!-- 标签：明确放在节点下方，避免与圆重叠 -->
        <rect
          :x="et.x - Math.max(et.labelW / 2 + 10, 36)"
          :y="et.y + 34"
          :width="Math.max(et.labelW + 20, 72)"
          height="22" rx="11"
          class="onto-map__label-bg"
          :stroke="et.color"
          stroke-width="1.2"
        />
        <text
          :x="et.x" :y="et.y + 49"
          :fill="et.color"
          font-size="12" font-weight="700" text-anchor="middle"
          class="onto-map__node-label"
        >{{ et.label }}</text>
        <!-- count badge -->
        <g v-if="et.entity_count">
          <rect
            :x="et.x + 14" :y="et.y - 34"
            :width="badgeWidth(et.entity_count)" height="18" rx="9"
            :fill="et.color"
          />
          <text
            :x="et.x + 14 + badgeWidth(et.entity_count) / 2"
            :y="et.y - 21"
            fill="#fff" font-size="10" font-weight="800" text-anchor="middle"
          >{{ et.entity_count }}</text>
        </g>
      </g>

      <!-- ── 公理栏 ── -->
      <g transform="translate(20, 632)">
        <rect x="0" y="0" width="860" height="52" rx="10" class="onto-map__axiom-panel"/>
        <text x="16" y="20" class="onto-map__axiom-title" font-size="12" font-weight="700">
          公理规则
          <tspan font-size="10" font-weight="500" class="onto-map__axiom-sub"> · Cypher 推理规则</tspan>
        </text>
        <template v-if="axiomRows.length">
          <text v-for="(ax, ai) in axiomRows" :key="'ax-'+ai"
            :x="16 + (ax.col * 280)" y="40"
            font-size="12" class="onto-map__axiom-item"
          >
            <tspan :fill="ax.active ? '#12b76a' : '#f04438'" font-weight="800">{{ ax.active ? '●' : '○' }}</tspan>
            {{ ax.name }}
          </text>
        </template>
        <text v-else x="16" y="40" font-size="11" class="onto-map__axiom-empty">尚无公理规则</text>
      </g>

      <!-- ── 空态 ── -->
      <g v-if="!entityTypes.length && !loading">
        <text x="450" y="300" font-size="16" text-anchor="middle" class="onto-map__empty-title">
          尚未初始化本体定义
        </text>
        <text x="450" y="328" font-size="13" text-anchor="middle" class="onto-map__empty-desc">
          请先初始化默认本体或手动创建实体类型
        </text>
      </g>
    </svg>

    <div class="onto-map__hint">拖拽调整 · 点击详情</div>

    <!-- ── 详情浮层 ── -->
    <Transition name="onto-overlay">
      <div v-if="activeDetail" class="onto-map__overlay" @click.self="activeDetail = null">
        <div class="onto-map__card">

          <template v-if="activeDetail.type === 'entity'">
            <div class="onto-map__card-hd">
              <span class="onto-map__card-dot" :style="{ background: activeDetail.data.color }"/>
              <div class="onto-map__card-title">{{ activeDetail.data.label }}</div>
              <button class="onto-map__card-close" @click="activeDetail = null">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 2l8 8M10 2l-8 8"/></svg>
              </button>
            </div>
            <div class="onto-map__card-sub">{{ activeDetail.data.code }}</div>
            <div class="onto-map__card-body">
              <div class="onto-map__card-stat">
                <span>实体数</span><strong>{{ activeDetail.data.entity_count }}</strong>
              </div>
              <div class="onto-map__card-sec">属性定义</div>
              <div v-if="!Object.keys(activeDetail.data.property_schema || {}).length" class="onto-map__card-empty">无自定义属性</div>
              <div v-for="(p, pn) in activeDetail.data.property_schema" :key="pn" class="onto-map__card-p">
                <span class="onto-map__card-pn">{{ pn }}</span>
                <span class="onto-map__card-pt">{{ p.type }}</span>
                <span v-if="p.required" class="onto-map__card-pr">必需</span>
              </div>
              <div class="onto-map__card-sec">关联关系</div>
              <div v-if="!entityRels.length" class="onto-map__card-empty">无关联关系</div>
              <div v-for="(r, ri) in entityRels" :key="ri" class="onto-map__card-rel" :style="{ borderLeftColor: r.color }">
                <span class="onto-map__card-rn">{{ r.label }}</span>
                <span class="onto-map__card-rd">{{ r.dir }}</span>
              </div>
            </div>
            <button class="onto-map__card-btn" @click="$emit('navigate', 'entity-types')">查看「实体类型」标签 →</button>
          </template>

          <template v-if="activeDetail.type === 'relation'">
            <div class="onto-map__card-hd">
              <span class="onto-map__card-dot" style="background:#a78bfa"/>
              <div class="onto-map__card-title">{{ activeDetail.data.label }}</div>
              <button class="onto-map__card-close" @click="activeDetail = null">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 2l8 8M10 2l-8 8"/></svg>
              </button>
            </div>
            <div class="onto-map__card-sub">{{ activeDetail.data.code }}</div>
            <div class="onto-map__card-body">
              <div class="onto-map__card-stat">
                <span>方向</span>
                <strong>{{ activeDetail.data.domain_types.join(', ') || '任意' }} → {{ activeDetail.data.range_types.join(', ') || '任意' }}</strong>
              </div>
              <div class="onto-map__card-stat">
                <span>关系数</span><strong>{{ activeDetail.data.relation_count }}</strong>
              </div>
              <div class="onto-map__card-tags">
                <span v-if="activeDetail.data.transitive" class="onto-map__card-tg">传递</span>
                <span v-if="activeDetail.data.symmetric" class="onto-map__card-tg">对称</span>
                <span v-if="activeDetail.data.inverse_of" class="onto-map__card-tg">逆: {{ activeDetail.data.inverse_of }}</span>
              </div>
            </div>
            <button class="onto-map__card-btn" @click="$emit('navigate', 'relation-types')">查看「关系类型」标签 →</button>
          </template>

        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from "vue";

defineEmits(["navigate"]);
const props = defineProps({
  entityTypes: { type: Array, default: () => [] },
  relationTypes: { type: Array, default: () => [] },
  axioms: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
});

const activeDetail = ref(null);
const activeEntityCode = ref(null);
const relHovered = ref(null);

function openEntityDetail(et) {
  activeEntityCode.value = et.code;
  activeDetail.value = { type: "entity", data: et };
}
function openRel(rel) {
  activeDetail.value = { type: "relation", data: rel };
}

function measureLabelW(label) {
  let w = 0;
  for (const ch of String(label || "")) {
    w += ch.charCodeAt(0) > 127 ? 12 : 7.5;
  }
  return Math.max(w, 24);
}

function badgeWidth(n) {
  const s = String(n);
  return Math.max(22, 10 + s.length * 7);
}

const ICON_MAP = {
  organization: "🏢", department: "🏢", user: "👤", person: "👤",
  document: "📄", doc: "📄", file: "📄",
  regulation: "📋", standard: "📋", rule: "📋",
  concept: "💡", term: "💡",
  category: "📁", tag: "🏷️",
  meeting: "📅", event: "📅",
  project: "📊", task: "✅",
  knowledge: "🧠", knowledge_point: "🧠",
  product: "📦", service: "🔧",
  customer: "🤝", partner: "🤝",
  business: "🏢", "document-text": "📄", scale: "⚖️",
  "folder-open": "📂", analytics: "📈", build: "🔧",
  code: "💻", robot: "🤖", bookmark: "🔖",
  default: "🔵",
};
function resolveIcon(et) {
  if (et.icon && et.icon !== "help-circle") return ICON_MAP[et.icon] || ICON_MAP[et.code] || "🔵";
  return ICON_MAP[et.code] || "🔵";
}

const CX = 450, CY = 290;
const nodePositions = reactive({});

function initPositions() {
  const items = props.entityTypes || [];
  const count = items.length;
  items.forEach((et, i) => {
    if (nodePositions[et.code]) return;
    const angle = (i / Math.max(count, 1)) * Math.PI * 2 - Math.PI / 2;
    // 节点变大后留更多间距，避免标签挤在一起
    const r = Math.max(150, Math.min(270, 140 + count * 16));
    nodePositions[et.code] = { x: CX + Math.cos(angle) * r, y: CY + Math.sin(angle) * r };
  });
  const codes = new Set(items.map((e) => e.code));
  Object.keys(nodePositions).forEach((k) => { if (!codes.has(k)) delete nodePositions[k]; });
}
initPositions();
watch(() => props.entityTypes, initPositions, { deep: true });

const nodes = computed(() =>
  (props.entityTypes || []).map((et) => {
    const pos = nodePositions[et.code] || { x: CX, y: CY };
    const label = et.label || et.code || "";
    return {
      ...et,
      icon: resolveIcon(et),
      x: pos.x,
      y: pos.y,
      labelW: measureLabelW(label),
      color: et.color || "#6366f1",
    };
  })
);

const relationPaths = computed(() => {
  const em = new Map(nodes.value.map((e) => [e.code, e]));
  return (props.relationTypes || []).map((rel) => {
    const src = em.get(rel.domain_types?.[0]);
    const dst = em.get(rel.range_types?.[0]);
    if (!src || !dst) return null;
    const mx = (src.x + dst.x) / 2, my = (src.y + dst.y) / 2;
    const dx = dst.x - src.x, dy = dst.y - src.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    // 缩短端点，避免箭头扎进节点圆心
    const pad = 32;
    const sx = src.x + (dx / dist) * pad;
    const sy = src.y + (dy / dist) * pad;
    const ex = dst.x - (dx / dist) * pad;
    const ey = dst.y - (dy / dist) * pad;
    const nx = -dy / dist * 28, ny = dx / dist * 28;
    const cpx = mx + nx, cpy = my + ny;
    const label = rel.label || rel.code || "";
    return {
      ...rel,
      color: src.color || "#888",
      path: `M${sx},${sy} Q${cpx},${cpy} ${ex},${ey}`,
      labelX: cpx + nx * 0.08,
      labelY: cpy + ny * 0.08,
      labelW: measureLabelW(label),
    };
  }).filter(Boolean);
});

const entityRels = computed(() => {
  if (!activeDetail.value || activeDetail.value.type !== "entity") return [];
  const code = activeDetail.value.data.code;
  return (props.relationTypes || [])
    .filter((r) => (r.domain_types || []).includes(code) || (r.range_types || []).includes(code))
    .map((r) => {
      const isDomain = (r.domain_types || []).includes(code);
      return {
        ...r,
        color: activeDetail.value.data.color,
        dir: isDomain ? `→ ${r.range_types.join(", ") || "?"}` : `← ${r.domain_types.join(", ") || "?"}`,
      };
    });
});

const AXIOMS_PER_ROW = 3;
const axiomRows = computed(() =>
  ((props.axioms || [])).map((ax, i) => ({ ...ax, row: Math.floor(i / AXIOMS_PER_ROW), col: i % AXIOMS_PER_ROW }))
);

const draggingNode = ref(null);
let ddx = 0, ddy = 0, clicked = false, startX = 0, startY = 0;
let svgEl = null;

function getPt(e) {
  if (!svgEl) svgEl = document.querySelector(".onto-map__svg");
  if (!svgEl) return { x: 0, y: 0 };
  const pt = svgEl.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const ctm = svgEl.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const sp = pt.matrixTransform(ctm.inverse());
  return { x: sp.x, y: sp.y };
}

function onNodeMouseDown(e, et) {
  if (activeDetail.value) return;
  clicked = false;
  const p = getPt(e);
  startX = p.x; startY = p.y;
  draggingNode.value = et.code;
  const pos = nodePositions[et.code];
  if (pos) { ddx = p.x - pos.x; ddy = p.y - pos.y; }
}

function onDragMove(e) {
  if (!draggingNode.value) return;
  const p = getPt(e);
  if (Math.abs(p.x - startX) > 4 || Math.abs(p.y - startY) > 4) {
    clicked = true;
  }
  const pos = nodePositions[draggingNode.value];
  if (pos) {
    pos.x = Math.max(70, Math.min(830, p.x - ddx));
    pos.y = Math.max(70, Math.min(560, p.y - ddy));
  }
}

function onDragEnd() {
  const code = draggingNode.value;
  draggingNode.value = null;
  if (code && !clicked) {
    const et = (props.entityTypes || []).find((x) => x.code === code);
    if (et) openEntityDetail(et);
  }
  clicked = false;
}

function onTouchStart(e, et) {
  if (activeDetail.value) return;
  const t = e.touches[0];
  clicked = false;
  const p = getPt({ clientX: t.clientX, clientY: t.clientY });
  startX = p.x; startY = p.y;
  draggingNode.value = et.code;
  const pos = nodePositions[et.code];
  if (pos) { ddx = p.x - pos.x; ddy = p.y - pos.y; }
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("touchend", onTouchEnd, { passive: false });
}
function onTouchMove(e) {
  e.preventDefault();
  const t = e.touches[0];
  if (Math.abs(t.clientX - startX) > 4 || Math.abs(t.clientY - startY) > 4) clicked = true;
  onDragMove({ clientX: t.clientX, clientY: t.clientY });
}
function onTouchEnd() {
  const code = draggingNode.value;
  draggingNode.value = null;
  if (code && !clicked) {
    const et = (props.entityTypes || []).find((x) => x.code === code);
    if (et) openEntityDetail(et);
  }
  clicked = false;
  document.removeEventListener("touchmove", onTouchMove);
  document.removeEventListener("touchend", onTouchEnd);
}
</script>

<style scoped>
.onto-map {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 520px;
  user-select: none;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--platform-bg-base, #fff);
  border-radius: var(--platform-radius);
  border: 1px solid var(--platform-border, #e5e7eb);
}

.onto-map__svg {
  width: 100%;
  height: 100%;
  max-height: none;
  overflow: visible;
  cursor: grab;
}
.onto-map__svg:active { cursor: grabbing; }

/* 主题感知画布色 */
.onto-map__canvas {
  fill: var(--platform-bg-elevated, #fafbfc);
}
.onto-map__grid-line {
  stroke: var(--platform-text, #111);
  stroke-opacity: 0.07;
  stroke-width: 0.6;
}
.onto-map__chip-bg,
.onto-map__label-bg {
  fill: var(--platform-bg-elevated, #fff);
}
.onto-map__axiom-panel {
  fill: var(--platform-bg-elevated, #fff);
  stroke: var(--platform-border-strong, #d0d5dd);
  stroke-width: 1.25;
}
.onto-map__axiom-title { fill: var(--platform-text, #101828); }
.onto-map__axiom-sub { fill: var(--platform-text-tertiary, #667085); }
.onto-map__axiom-item { fill: var(--platform-text-secondary, #475467); }
.onto-map__axiom-empty { fill: var(--platform-text-quaternary, #98a2b3); }
.onto-map__empty-title { fill: var(--platform-text-secondary, #667085); }
.onto-map__empty-desc { fill: var(--platform-text-tertiary, #98a2b3); }

.onto-map__node-fill {
  stroke: var(--platform-bg-elevated, #fff);
}

.onto-map__rel-path { cursor: pointer; transition: opacity 0.15s ease, stroke-width 0.15s ease; }
.onto-map__rel-chip { cursor: pointer; }
.onto-map__rel-label { pointer-events: none; }

.onto-map__node-group { cursor: pointer; transition: filter 0.15s ease; }
.onto-map__node-group:hover { filter: brightness(1.12) saturate(1.15); }
.onto-map__node-group--active { filter: brightness(1.18) saturate(1.2); }
.onto-map__node-icon,
.onto-map__node-label { pointer-events: none; }
.onto-map__node-icon {
  /* emoji 自带颜色，加轻阴影提高浅色底上的可读性 */
  filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.25));
}

.onto-map__hint {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  pointer-events: none;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  color: var(--platform-text-secondary);
  background: color-mix(in srgb, var(--platform-bg-elevated) 92%, transparent);
  border: 1px solid var(--platform-border);
  backdrop-filter: blur(8px);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

/* ── 遮罩浮层 ── */
.onto-map__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.32);
  z-index: 30;
  backdrop-filter: blur(3px);
}

.onto-map__card {
  width: 320px;
  max-height: 80vh;
  background: var(--platform-bg-elevated);
  border: 1px solid color-mix(in srgb, var(--platform-text) 10%, transparent);
  border-radius: 12px;
  padding: 20px 22px;
  box-shadow: 0 8px 48px rgba(0, 0, 0, 0.3);
  overflow-y: auto;
  position: relative;
}
.onto-map__card-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-right: 24px;
}
.onto-map__card-dot { flex-shrink: 0; width: 6px; height: 28px; border-radius: 3px; }
.onto-map__card-title { font-size: 15px; font-weight: 680; color: var(--platform-text); line-height: 1.3; }
.onto-map__card-close {
  position: absolute; top: 12px; right: 12px;
  width: 26px; height: 26px;
  border: none; background: transparent;
  color: var(--platform-text-quaternary);
  cursor: pointer; border-radius: 5px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.onto-map__card-close:hover { background: color-mix(in srgb, var(--platform-text) 10%, transparent); color: var(--platform-text-secondary); }
.onto-map__card-sub {
  font-size: 11px; color: var(--platform-text-tertiary);
  font-family: "SF Mono", "Fira Code", monospace;
  margin: 3px 0 0 16px;
}
.onto-map__card-body { margin-top: 14px; font-size: 11px; }
.onto-map__card-stat {
  display: flex; justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--platform-text) 6%, transparent);
  color: var(--platform-text-tertiary);
}
.onto-map__card-stat strong { color: var(--platform-text); font-weight: 660; }
.onto-map__card-sec {
  font-size: 9px; font-weight: 700; color: var(--platform-text-secondary);
  margin-top: 12px; margin-bottom: 6px; letter-spacing: 0.06em;
}
.onto-map__card-empty { font-size: 10px; color: var(--platform-text-quaternary); font-style: italic; padding: 3px 0; }
.onto-map__card-p {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 8px; border-radius: 4px;
  background: color-mix(in srgb, var(--platform-text) 4%, transparent);
  margin-bottom: 3px;
}
.onto-map__card-pn { font-weight: 600; color: var(--platform-text); flex: 1; font-size: 10px; }
.onto-map__card-pt {
  font-size: 8px; color: var(--platform-text-tertiary);
  background: color-mix(in srgb, var(--platform-text) 8%, transparent);
  padding: 1px 6px; border-radius: 3px;
}
.onto-map__card-pr { font-size: 7px; color: #ef4444; font-weight: 700; }
.onto-map__card-rel {
  padding: 5px 8px; border-left: 2px solid; border-radius: 0 4px 4px 0;
  background: color-mix(in srgb, var(--platform-text) 3%, transparent);
  margin-bottom: 3px;
  display: flex; justify-content: space-between;
}
.onto-map__card-rn { font-weight: 600; color: var(--platform-text); font-size: 10px; }
.onto-map__card-rd { font-size: 9px; color: var(--platform-text-tertiary); }
.onto-map__card-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.onto-map__card-tg {
  font-size: 9px; font-weight: 600; padding: 3px 8px; border-radius: 4px;
  background: color-mix(in srgb, #a78bfa 14%, transparent); color: #a78bfa;
}
.onto-map__card-btn {
  display: block; width: 100%;
  margin-top: 14px; padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--platform-accent) 30%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--platform-accent) 8%, transparent);
  color: var(--platform-accent);
  font-size: 11px; font-weight: 600; cursor: pointer;
  text-align: center;
  transition: background 0.2s, border-color 0.2s;
}
.onto-map__card-btn:hover { background: color-mix(in srgb, var(--platform-accent) 18%, transparent); border-color: var(--platform-accent); }

.onto-overlay-enter-active,
.onto-overlay-leave-active { transition: opacity 0.2s ease; }
.onto-overlay-enter-active .onto-map__card,
.onto-overlay-leave-active .onto-map__card { transition: transform 0.2s ease; }
.onto-overlay-enter-from,
.onto-overlay-leave-to { opacity: 0; }
.onto-overlay-enter-from .onto-map__card { transform: scale(0.92); }
.onto-overlay-leave-to .onto-map__card { transform: scale(0.92); }
</style>
