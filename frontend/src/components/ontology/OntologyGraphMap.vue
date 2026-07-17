<template>
  <div class="onto-map" ref="containerRef" @mouseup="onDragEnd" @mousemove="onDragMove" @mouseleave="onDragEnd">

    <svg class="onto-map__svg" viewBox="0 0 600 480" preserveAspectRatio="xMidYMid meet">

      <!-- ── 关系连线 ── -->
      <g v-for="(rel, ri) in relationPaths" :key="'rel-'+ri">
        <marker :id="`arrow-${ri}`" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" :fill="rel.color" opacity="0.6"/>
        </marker>
        <path
          :d="rel.path"
          :stroke="rel.color"
          :stroke-width="relHovered === rel.code ? 3 : 1.2"
          fill="none"
          :opacity="relHovered === rel.code ? 0.9 : 0.2"
          class="onto-map__rel-path"
          @mouseenter="relHovered = rel.code"
          @mouseleave="relHovered = null"
          @click.stop="openRel(rel)"
        />
        <text
          :x="rel.labelX" :y="rel.labelY"
          :fill="rel.color"
          font-size="6.5" font-weight="700" text-anchor="middle"
          :opacity="relHovered === rel.code ? 0.95 : 0.2"
          class="onto-map__rel-label"
        >{{ rel.label }}</text>
      </g>

      <!-- ── 实体节点 ── -->
      <g v-for="(et, ei) in nodes" :key="'et-'+ei"
        class="onto-map__node-group"
        :class="{ 'onto-map__node-group--active': activeEntityCode === et.code }"
        @mousedown.stop="onNodeMouseDown($event, et)"
        @touchstart.stop.prevent="onTouchStart($event, et)"
      >
        <circle :cx="et.x" :cy="et.y" r="30" :fill="et.color" opacity="0.05"/>
        <circle :cx="et.x" :cy="et.y" r="24" :fill="et.color" opacity="0.1" stroke="none"/>
        <circle :cx="et.x" :cy="et.y" r="24"
          fill="none" :stroke="et.color"
          :stroke-width="activeEntityCode === et.code ? 3 : 1.5"
          :opacity="activeEntityCode === et.code ? 0.95 : 0.4"
          class="onto-map__node-ring"
        />
        <!-- icon -->
        <text :x="et.x" :y="et.y - 2" font-size="13" text-anchor="middle" dominant-baseline="central"
          fill="currentColor" :opacity="activeEntityCode === et.code ? 1 : 0.65" class="onto-map__node-icon"
        >{{ et.icon }}</text>
        <!-- label -->
        <text :x="et.x" :y="et.y + 15" :fill="et.color" font-size="7" font-weight="700" text-anchor="middle"
          :opacity="activeEntityCode === et.code ? 1 : 0.65" class="onto-map__node-label"
        >{{ et.label }}</text>
        <!-- count badge -->
        <g v-if="et.entity_count">
          <rect :x="et.x + 16" :y="et.y - 25" width="16" height="10" rx="5" :fill="et.color" opacity="0.2"/>
          <text :x="et.x + 24" :y="et.y - 19" :fill="et.color" font-size="5.5" font-weight="700" text-anchor="middle">{{ et.entity_count }}</text>
        </g>
      </g>

      <!-- ── 公理栏 ── -->
      <g transform="translate(20, 440)">
        <rect x="0" y="0" width="560" height="34" rx="6" fill="var(--platform-bg-elevated)" opacity="0.35"/>
        <text x="10" y="14" fill="var(--platform-text-secondary)" font-size="8" font-weight="700">
          公理规则 <tspan font-size="6" fill="var(--platform-text-quaternary)" font-weight="400">Cypher 推理规则</tspan>
        </text>
        <template v-if="axiomRows.length">
          <text v-for="(ax, ai) in axiomRows" :key="'ax-'+ai"
            :x="10 + (ax.col * 185)" y="27"
            fill="var(--platform-text-tertiary)" font-size="6.5"
          >
            <tspan :fill="ax.active ? '#34d399' : '#f87171'" font-weight="700">{{ ax.active ? '●' : '○' }}</tspan>
            {{ ax.name }}
          </text>
        </template>
        <text v-else x="10" y="27" fill="var(--platform-text-quaternary)" font-size="6">尚无公理规则</text>
      </g>

      <!-- ── 空态 ── -->
      <g v-if="!entityTypes.length && !loading">
        <text x="300" y="200" fill="var(--platform-text-tertiary)" font-size="13" text-anchor="middle" opacity="0.5">
          尚未初始化本体定义
        </text>
        <text x="300" y="224" fill="var(--platform-text-quaternary)" font-size="9" text-anchor="middle" opacity="0.35">
          请先初始化默认本体或手动创建实体类型
        </text>
      </g>
    </svg>

    <!-- ── 详情浮层 ── -->
    <Transition name="onto-overlay">
      <div v-if="activeDetail" class="onto-map__overlay" @click.self="activeDetail = null">
        <div class="onto-map__card">

          <!-- 实体类型 -->
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

          <!-- 关系类型 -->
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

const emit = defineEmits(["navigate"]);
const props = defineProps({
  entityTypes: { type: Array, default: () => [] },
  relationTypes: { type: Array, default: () => [] },
  axioms: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
});

// ── 详情状态 ──
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

// ── 图标 ──
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

// ── 节点位置（可拖拽） ──
const CX = 280, CY = 180;
const nodePositions = reactive({});

function initPositions() {
  const items = props.entityTypes || [];
  const count = items.length;
  items.forEach((et, i) => {
    if (nodePositions[et.code]) return;
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    const r = Math.max(90, Math.min(170, 80 + count * 10));
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
    return { ...et, icon: resolveIcon(et), x: pos.x, y: pos.y };
  })
);

// ── 关系路径 ──
const relationPaths = computed(() => {
  const em = new Map(nodes.value.map((e) => [e.code, e]));
  return (props.relationTypes || []).map((rel) => {
    const src = em.get(rel.domain_types?.[0]);
    const dst = em.get(rel.range_types?.[0]);
    if (!src || !dst) return null;
    const mx = (src.x + dst.x) / 2, my = (src.y + dst.y) / 2;
    const dx = dst.x - src.x, dy = dst.y - src.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const nx = -dy / dist * 18, ny = dx / dist * 18;
    const cpx = mx + nx, cpy = my + ny;
    return {
      ...rel,
      color: src.color || "#888",
      path: `M${src.x},${src.y} Q${cpx},${cpy} ${dst.x},${dst.y}`,
      labelX: cpx + nx * 0.15, labelY: cpy + ny * 0.15,
    };
  }).filter(Boolean);
});

// ── 选中实体的关联关系 ──
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

// ── 公理 ──
const axiomRows = computed(() =>
  ((props.axioms || [])).map((ax, i) => ({ ...ax, row: Math.floor(i / 3), col: i % 3 }))
);

// ── 拖拽（区分拖拽和点击） ──
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
    clicked = true; // 移动了 → 不是点击
  }
  const pos = nodePositions[draggingNode.value];
  if (pos) {
    pos.x = Math.max(40, Math.min(560, p.x - ddx));
    pos.y = Math.max(40, Math.min(390, p.y - ddy));
  }
}

function onDragEnd(e) {
  const code = draggingNode.value;
  draggingNode.value = null;
  // 是拖拽还是点击？
  if (code && !clicked) {
    const et = (props.entityTypes || []).find((x) => x.code === code);
    if (et) openEntityDetail(et);
  }
  clicked = false;
}

// touch
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
  min-height: 480px;
  user-select: none;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse 60% 40% at 50% 40%, color-mix(in srgb, var(--platform-accent) 4%, transparent), transparent 75%),
    radial-gradient(ellipse 40% 30% at 50% 70%, color-mix(in srgb, var(--platform-accent) 2%, transparent), transparent 70%);
  border-radius: var(--platform-radius);
}

.onto-map__svg {
  width: 100%;
  height: 100%;
  max-height: 490px;
  overflow: visible;
  cursor: grab;
}
.onto-map__svg:active { cursor: grabbing; }

/* 关系 */
.onto-map__rel-path { cursor: pointer; transition: opacity 0.2s ease, stroke-width 0.2s ease; }
.onto-map__rel-label { transition: opacity 0.2s ease; }

/* 节点 */
.onto-map__node-group { cursor: pointer; transition: filter 0.15s ease; }
.onto-map__node-group:hover { filter: brightness(1.35); }
.onto-map__node-group--active { filter: brightness(1.5); }
.onto-map__node-ring { transition: stroke-width 0.15s ease, opacity 0.15s ease; }
.onto-map__node-icon,
.onto-map__node-label { pointer-events: none; transition: opacity 0.15s ease; }

/* ── 遮罩浮层 ── */
.onto-map__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.25);
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

/* 浮层动画 */
.onto-overlay-enter-active,
.onto-overlay-leave-active { transition: opacity 0.2s ease; }
.onto-overlay-enter-active .onto-map__card,
.onto-overlay-leave-active .onto-map__card { transition: transform 0.2s ease; }
.onto-overlay-enter-from,
.onto-overlay-leave-to { opacity: 0; }
.onto-overlay-enter-from .onto-map__card { transform: scale(0.92); }
.onto-overlay-leave-to .onto-map__card { transform: scale(0.92); }
</style>
