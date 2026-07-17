<template>
  <div
    class="arch-wrapper"
    :class="{ 'arch-wrapper--dragging': isDragging, 'arch-wrapper--login': loginMode }"
    ref="wrapperRef"
    @mousedown="onPointerDown"
    @mousemove="onPointerMove"
    @mouseup="onPointerUp"
    @mouseleave="onPointerUp"
    @touchstart.prevent="onTouchStart"
    @touchmove.prevent="onTouchMove"
    @touchend="onPointerUp"
  >
    <div class="arch-bg-glow" />

    <!-- 粒子层 -->
    <canvas ref="particleCanvas" class="arch-particles" />

    <!-- 3D 锥体 -->
    <div class="arch-scene">
      <div class="arch-cone">
        <!-- 锥体侧面壁 -->
        <div v-for="w in coneWalls" :key="w.id" class="arch-cone-wall" :style="w.style" />
        <!-- 棱线 -->
        <div v-for="r in coneRibs" :key="r.id" class="arch-cone-rib" :style="r.style" />

        <!-- 每层 -->
        <template v-for="(layer, li) in layers" :key="li">
          <div class="arch-ring" :style="ringStyle(layer)" />
          <div class="arch-ring-face" :style="ringFaceStyle(layer)" />
          <div class="arch-ring-glow" :style="ringGlowStyle(layer)" />

          <!-- 节点 -->
          <div
            v-for="(node, ni) in layer.nodes"
            :key="`${li}-${ni}`"
            class="arch-node"
            :class="{ 'arch-node--hovered': !loginMode && hoveredNode === node }"
            :style="nodeStyle(layer, ni, li)"
            @mouseenter="loginMode ? null : onNodeEnter(node)"
            @mouseleave="loginMode ? null : onNodeLeave"
            @click.stop="loginMode ? null : onNodeClick(node, layer)"
          >
            <div class="arch-node__inner" :style="{ background: layer.color }">
              <span class="arch-node__icon">{{ node.icon }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 提示（仅非登录模式） -->
    <div v-if="!loginMode" class="arch-hint-icon">↔</div>
    <div v-if="!loginMode" class="arch-hint">拖拽旋转 · 点击节点查看详情</div>

    <!-- 信息面板（仅非登录模式） -->
    <Transition name="arch-panel-slide">
      <div v-if="!loginMode && activeNode" class="arch-info-panel" @click.stop>
        <button class="arch-info-panel__close" @click="activeNode = null">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l10 10M12 2L2 12"/></svg>
        </button>
        <div class="arch-info-panel__header">
          <span class="arch-info-panel__icon">{{ activeNode.icon }}</span>
          <div>
            <div class="arch-info-panel__title">{{ activeNode.label }}</div>
            <div class="arch-info-panel__layer" :style="{ color: activeLayer?.color }">{{ activeLayer?.name }}</div>
          </div>
        </div>
        <p class="arch-info-panel__desc">{{ activeNode.description }}</p>
      </div>
    </Transition>

    <!-- 图例（仅非登录模式） -->
    <div v-if="!loginMode" class="arch-legend">
      <div v-for="(layer, li) in layers" :key="li" class="arch-legend__item">
        <span class="arch-legend__bar" :style="{ background: layer.color }" />
        <div>
          <div class="arch-legend__label">{{ layer.name }}</div>
          <div class="arch-legend__desc">{{ layer.description }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from "vue";

const props = defineProps({
  loginMode: { type: Boolean, default: false },
});

// ── 颜色 ──
const COLORS = {
  infra: "#0ea5e9", skill: "#8b5cf6", semantic: "#f59e0b", agent: "#10b981",
};

// ── 分层数据（从下到上：正Y → 负Y = 底部 → 顶部）──
const layers = ref([
  {
    id: "infra", name: "平台设施层", color: COLORS.infra,
    radius: 210, yOffset: 180,
    description: "文档库、IAM 等数据与权限基石",
    nodes: [
      { label: "文档库", icon: "📄", desc: "分级 scope 文档管理，支持版本控制、单文档 ACL、回收站。" },
      { label: "IAM", icon: "🔐", desc: "用户/部门/角色管理，JWT 无状态鉴权，RBAC 功能权限。" },
      { label: "PostgreSQL", icon: "🗄️", desc: "主数据存储，事务保障 schema migrate。" },
      { label: "MinIO", icon: "💾", desc: "文档二进制与版本文件的分布式对象存储。" },
      { label: "Redis", icon: "⚡", desc: "Celery broker 与缓存层。" },
      { label: "翻译引擎", icon: "📝", desc: "pdf2zh_next，版式保留 PDF 翻译。" },
      { label: "RAGFlow", icon: "🔍", desc: "文档解析与向量检索后端。" },
      { label: "语音服务", icon: "🎤", desc: "FunASR 转写 + CAM++ 说话人分离。" },
    ],
  },
  {
    id: "skill", name: "能力层", color: COLORS.skill,
    radius: 165, yOffset: 65,
    description: "可插拔的智能工具与技能包",
    nodes: [
      { label: "知识问答", icon: "💬", desc: "RAGFlow 检索增强生成 + iframe 嵌入。" },
      { label: "文档智能", icon: "🤖", desc: "PDF 翻译与文档对比的异步任务模型。" },
      { label: "Skill 框架", icon: "🧩", desc: "SKILL.md 驱动的技能注册与执行引擎。" },
      { label: "搜索检索", icon: "🔎", desc: "SearXNG 元搜索 + 平台内文档检索。" },
      { label: "文档对比", icon: "📊", desc: "异步 diff 引擎，语义检索与色系分离。" },
      { label: "内容订阅", icon: "📡", desc: "网站收藏与公众号 feed，DeepSeek 摘要。" },
    ],
  },
  {
    id: "semantic", name: "语义层", color: COLORS.semantic,
    radius: 115, yOffset: -55,
    description: "本体论 + 知识图谱",
    nodes: [
      { label: "本体论", icon: "🧬", desc: "实体类型、关系类型与公理规则的结构化建模。" },
      { label: "知识图谱", icon: "🕸️", desc: "Neo4j 图数据库，支撑推理与关联发现。" },
      { label: "语义推理", icon: "🔗", desc: "OWL 规则推理，增强知识问答语义深度。" },
    ],
  },
  {
    id: "agent", name: "智能体层", color: COLORS.agent,
    radius: 65, yOffset: -175,
    description: "感知、规划与执行，统筹全局",
    nodes: [
      { label: "调度智能体", icon: "🧠", desc: "AgentLoopSession 短会话，避免连接池占满。" },
      { label: "工具循环", icon: "🔄", desc: "AgentToolLoop 执行引擎。" },
      { label: "AI 对话", icon: "💭", desc: "流式对话，多轮上下文与 Skill 激活。" },
      { label: "多智能体", icon: "👥", desc: "AIP 互联协议，AgentKit 包拆分架构。" },
    ],
  },
]);

// ── 状态 ──
const wrapperRef = ref(null);
const particleCanvas = ref(null);
const rotationAngle = ref(-30);
const hoveredNode = ref(null);
const activeNode = ref(null);
const isDragging = ref(false);
const activeLayer = computed(() => activeNode.value ? layers.value.find(l => l.nodes.includes(activeNode.value)) : null);

// ── 拖拽 ──
let dragStartX = 0, dragStartAngle = 0;
const getX = e => e.touches ? e.touches[0].clientX : e.clientX;

function onPointerDown(e) { if (e.button !== 0) return; dragStartX = getX(e); dragStartAngle = rotationAngle.value; isDragging.value = true; }
function onTouchStart(e) { dragStartX = getX(e); dragStartAngle = rotationAngle.value; isDragging.value = true; }
function onPointerMove(e) { if (!isDragging.value) return; rotationAngle.value = dragStartAngle + (getX(e) - dragStartX) * 0.6; }
function onTouchMove(e) { if (!isDragging.value) return; rotationAngle.value = dragStartAngle + (getX(e) - dragStartX) * 0.6; }
function onPointerUp() { isDragging.value = false; }

// ── 自动缓慢旋转 ──
let autoAnim = null;
let lastTime = 0;
function autoRotate(time) {
  if (!isDragging.value) {
    rotationAngle.value += 0.08;
  }
  updateNodes();
  autoAnim = requestAnimationFrame(autoRotate);
}

// ── 粒子系统 ──
let particleCtx = null;
let particles = [];
let particleAnim = null;

function initParticles() {
  const canvas = particleCanvas.value;
  if (!canvas) return;
  particleCtx = canvas.getContext("2d");
  resizeParticles();
  window.addEventListener("resize", resizeParticles);
  particles = Array.from({ length: 80 }, () => createParticle());
}

function resizeParticles() {
  const canvas = particleCanvas.value;
  if (!canvas) return;
  canvas.width = canvas.parentElement.clientWidth || window.innerWidth;
  canvas.height = canvas.parentElement.clientHeight || window.innerHeight;
}

function createParticle() {
  const colors = Object.values(COLORS);
  return {
    x: Math.random() * (particleCanvas.value?.width || 800),
    y: Math.random() * (particleCanvas.value?.height || 600),
    r: Math.random() * 2 + 0.5,
    dx: (Math.random() - 0.5) * 0.3,
    dy: (Math.random() - 0.5) * 0.3,
    color: colors[Math.floor(Math.random() * colors.length)],
    alpha: Math.random() * 0.4 + 0.1,
    pulse: Math.random() * Math.PI * 2,
  };
}

function drawParticles(time) {
  if (!particleCtx || !particleCanvas.value) { particleAnim = requestAnimationFrame(drawParticles); return; }
  const ctx = particleCtx;
  const w = particleCanvas.value.width;
  const h = particleCanvas.value.height;
  ctx.clearRect(0, 0, w, h);

  for (const p of particles) {
    p.x += p.dx;
    p.y += p.dy;
    p.pulse += 0.02;
    if (p.x < 0 || p.x > w) p.dx *= -1;
    if (p.y < 0 || p.y > h) p.dy *= -1;

    const pulseAlpha = p.alpha * (0.6 + 0.4 * Math.sin(p.pulse));
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.globalAlpha = pulseAlpha;
    ctx.fill();

    // 发光
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.globalAlpha = pulseAlpha * 0.08;
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  particleAnim = requestAnimationFrame(drawParticles);
}

// ── 锥体计算 ──
const RIB_COUNT = 8;

const coneRibs = computed(() => {
  const raw = layers.value;
  if (raw.length < 2) return [];
  const r = [], bottom = raw[0], top = raw[raw.length - 1];
  for (let i = 0; i < RIB_COUNT; i++) {
    const a = (i / RIB_COUNT) * Math.PI * 2;
    const bx = bottom.radius * Math.sin(a), bz = bottom.radius * Math.cos(a);
    const tx = top.radius * Math.sin(a), tz = top.radius * Math.cos(a);
    const by = bottom.yOffset, ty = top.yOffset;
    const mx = (bx + tx) / 2, my = (by + ty) / 2, mz = (bz + tz) / 2;
    const dx = tx - bx, dy = ty - by, dz = tz - bz;
    const len = Math.sqrt(dx*dx + dy*dy + dz*dz);
    const aY = Math.atan2(dx, dz) * (180 / Math.PI);
    const aX = Math.atan2(dy, Math.sqrt(dx*dx + dz*dz)) * (180 / Math.PI);
    r.push({ id: `r-${i}`, style: {
      width: `${len}px`, height: "1px",
      transform: `translate3d(${mx}px,${my}px,${mz}px) rotateY(${aY}deg) rotateX(${-aX}deg)`,
      background: `linear-gradient(90deg,${bottom.color}35,${top.color}35)`,
    }});
  }
  return r;
});

const coneWalls = computed(() => {
  const raw = layers.value;
  if (raw.length < 2) return [];
  const r = [], step = 2;
  for (let i = 0; i < RIB_COUNT; i += step) {
    const a1 = (i / RIB_COUNT) * Math.PI * 2, a2 = ((i + step) / RIB_COUNT) * Math.PI * 2;
    const b = raw[0], t = raw[raw.length - 1];
    const b1x = b.radius * Math.sin(a1), b1z = b.radius * Math.cos(a1);
    const b2x = b.radius * Math.sin(a2), b2z = b.radius * Math.cos(a2);
    const t1x = t.radius * Math.sin(a1), t1z = t.radius * Math.cos(a1);
    const t2x = t.radius * Math.sin(a2), t2z = t.radius * Math.cos(a2);
    const cx = (b1x + b2x + t1x + t2x) / 4, cy = (b.yOffset + t.yOffset) / 2, cz = (b1z + b2z + t1z + t2z) / 4;
    const mbx = (b1x + b2x) / 2, mbz = (b1z + b2z) / 2, mtx = (t1x + t2x) / 2, mtz = (t1z + t2z) / 2;
    const wDx = mbx - mtx, wDz = mbz - mtz;
    const wLen = Math.sqrt(wDx*wDx + wDz*wDz), hLen = t.yOffset - b.yOffset;
    const wA = Math.atan2(wDx, wDz) * (180 / Math.PI);
    r.push({ id: `w-${i}`, style: {
      width: `${wLen}px`, height: `${hLen}px`,
      transform: `translate3d(${cx}px,${cy}px,${cz}px) rotateY(${wA}deg)`,
      background: `linear-gradient(180deg,${t.color}0a,${b.color}06)`,
    }});
  }
  return r;
});

const nodePositions = reactive(new Map());

function updateNodes() {
  const angle = rotationAngle.value * Math.PI / 180;
  for (const layer of layers.value) {
    const count = layer.nodes.length;
    for (let i = 0; i < count; i++) {
      const wa = (i / count) * Math.PI * 2 + angle;
      nodePositions.set(`${layers.value.indexOf(layer)}-${i}`, {
        x: layer.radius * Math.sin(wa), y: layer.yOffset, z: layer.radius * Math.cos(wa), angle: wa,
      });
    }
  }
}

function nodeStyle(layer, index, li) {
  const pos = nodePositions.get(`${li}-${index}`);
  if (!pos) return { display: "none" };
  const df = Math.max(0.3, Math.min(1, ((pos.z + layer.radius) / (layer.radius * 2)) * 1.3 + 0.15));
  return {
    transform: `translate3d(${pos.x}px,${pos.y}px,${pos.z}px) scale(${df}) rotateX(${-Math.sin(pos.angle) * 5}deg)`,
    opacity: df,
    zIndex: pos.z < -layer.radius * 0.1 ? 0 : Math.round(pos.z + layer.radius + 300 - li * 30),
  };
}

function ringStyle(layer) {
  return {
    width: `${layer.radius * 2 + 14}px`, height: `${layer.radius * 2 + 14}px`,
    transform: `translate3d(-50%,-50%,-2px) translateY(${layer.yOffset}px)`,
    borderColor: `${layer.color}50`,
    boxShadow: `0 0 28px ${layer.color}1a, inset 0 0 28px ${layer.color}0c`,
  };
}

function ringFaceStyle(layer) {
  return {
    width: `${layer.radius * 2}px`, height: `${layer.radius * 2}px`,
    transform: `translate3d(-50%,-50%,0) translateY(${layer.yOffset}px)`,
    background: `radial-gradient(circle, ${layer.color}16 0%, ${layer.color}08 25%, transparent 70%)`,
    borderColor: `${layer.color}24`,
  };
}

function ringGlowStyle(layer) {
  return {
    width: `${layer.radius * 2 + 60}px`, height: `${layer.radius * 2 + 60}px`,
    transform: `translate3d(-50%,-50%,-4px) translateY(${layer.yOffset}px)`,
    background: `radial-gradient(circle, ${layer.color}08 0%, transparent 70%)`,
  };
}

function onNodeEnter(n) { hoveredNode.value = n; }
function onNodeLeave() { hoveredNode.value = null; }
function onNodeClick(n) { activeNode.value = n; }

onMounted(() => {
  updateNodes();
  autoAnim = requestAnimationFrame(autoRotate);
  if (!props.loginMode) {
    initParticles();
    particleAnim = requestAnimationFrame(drawParticles);
  }
});

onUnmounted(() => {
  if (autoAnim) cancelAnimationFrame(autoAnim);
  if (particleAnim) cancelAnimationFrame(particleAnim);
  if (!props.loginMode) window.removeEventListener("resize", resizeParticles);
});
</script>

<style scoped>
.arch-wrapper {
  position: relative; width: 100%; height: 100%; min-height: 700px;
  overflow: hidden; user-select: none; cursor: grab;
  background: radial-gradient(ellipse 50% 35% at 50% 58%, color-mix(in srgb, var(--platform-accent) 5%, transparent), transparent 80%);
  border-radius: var(--platform-radius);
}
.arch-wrapper--dragging { cursor: grabbing; }
.arch-wrapper--login {
  position: fixed;
  inset: 0;
  min-height: 100dvh;
  border-radius: 0;
  background:
    radial-gradient(ellipse 60% 45% at 50% 55%, rgba(14, 165, 233, 0.04), transparent 70%),
    radial-gradient(ellipse 40% 30% at 30% 40%, rgba(139, 92, 246, 0.03), transparent 60%),
    radial-gradient(ellipse 40% 30% at 70% 40%, rgba(16, 185, 129, 0.03), transparent 60%),
    var(--platform-bg-base);
}

.arch-bg-glow {
  position: absolute; inset: 0; pointer-events: none;
  background:
    radial-gradient(ellipse 40% 50% at 50% 60%, var(--platform-accent)04, transparent 60%),
    radial-gradient(ellipse 20% 30% at 30% 50%, rgba(139,92,246,0.03), transparent 50%),
    radial-gradient(ellipse 20% 30% at 70% 50%, rgba(16,185,129,0.03), transparent 50%);
}

.arch-particles {
  position: absolute; inset: 0; pointer-events: none; z-index: 1;
}

.arch-scene {
  position: relative; z-index: 2;
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  perspective: 1100px; perspective-origin: 50% 45%;
}

.arch-cone {
  position: relative; width: 0; height: 0;
  transform-style: preserve-3d;
  transform: rotateX(18deg) translateY(-10px);
}

.arch-cone-rib {
  position: absolute; left: 0; top: 0;
  transform-origin: left center; transform-style: preserve-3d;
  pointer-events: none; opacity: 0.5;
}
.arch-cone-wall {
  position: absolute; left: 0; top: 0;
  transform-origin: center center; transform-style: preserve-3d;
  pointer-events: none; opacity: 0.2;
}

.arch-ring {
  position: absolute; top: 50%; left: 50%;
  border-radius: 50%; border: 2.5px solid;
  transform-style: preserve-3d; pointer-events: none;
  backface-visibility: hidden;
}
.arch-ring-face {
  position: absolute; top: 50%; left: 50%;
  border-radius: 50%; border: 1px solid;
  transform-style: preserve-3d; pointer-events: none;
  backface-visibility: hidden;
}
.arch-ring-glow {
  position: absolute; top: 50%; left: 50%;
  border-radius: 50%;
  transform-style: preserve-3d; pointer-events: none;
  backface-visibility: hidden;
  animation: arch-glow-pulse 4s ease-in-out infinite alternate;
}
@keyframes arch-glow-pulse {
  0% { opacity: 0.3; transform: translate3d(-50%,-50%,-4px) scale(0.95); }
  100% { opacity: 0.7; transform: translate3d(-50%,-50%,-4px) scale(1.05); }
}

.arch-node {
  position: absolute; left: 50%; top: 50%;
  transform-style: preserve-3d; cursor: pointer;
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  transition: filter 0.3s ease, opacity 0.15s ease;
  backface-visibility: hidden; will-change: transform, opacity;
}
.arch-node:hover { z-index: 999 !important; }
.arch-node__inner {
  width: 42px; height: 42px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; color: #fff;
  box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 20%, transparent), 0 4px 14px color-mix(in srgb, currentColor 22%, transparent);
  transition: transform 0.35s var(--platform-ease-spring), box-shadow 0.35s ease;
  position: relative;
}
.arch-node__inner::after {
  content: ""; position: absolute; inset: -4px; border-radius: 50%;
  border: 2px solid color-mix(in srgb, currentColor 18%, transparent);
  opacity: 0; transition: opacity 0.35s ease;
}
.arch-node--hovered .arch-node__inner {
  transform: scale(1.25);
  box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 32%, transparent), 0 8px 30px color-mix(in srgb, currentColor 35%, transparent);
}
.arch-node--hovered .arch-node__inner::after { opacity: 1; border-color: color-mix(in srgb, currentColor 45%, transparent); }
.arch-node__icon { line-height: 1; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.15)); }

.arch-hint {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  padding: 5px 14px;
  background: color-mix(in srgb, var(--platform-bg-elevated) 70%, transparent);
  backdrop-filter: blur(10px); border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-pill); font-size: 11px;
  color: var(--platform-text-tertiary); opacity: 0.6; pointer-events: none; z-index: 3;
}
.arch-hint-icon {
  position: absolute; bottom: 46px; left: 50%; transform: translateX(-50%);
  font-size: 18px; color: var(--platform-text-quaternary); opacity: 0.35;
  pointer-events: none; z-index: 3;
  animation: arch-bounce 1.8s ease-in-out infinite;
}
@keyframes arch-bounce {
  0%,100% { transform: translateX(-50%) translateX(0); }
  50% { transform: translateX(-50%) translateX(6px); }
}

.arch-info-panel {
  position: absolute; right: 20px; top: 20px; width: 280px; padding: 18px 20px;
  background: color-mix(in srgb, var(--platform-bg-elevated) 90%, transparent);
  backdrop-filter: blur(18px); border: 1px solid var(--platform-border-strong);
  border-radius: var(--platform-radius); box-shadow: var(--platform-modal-shadow); z-index: 10;
}
.arch-info-panel__close {
  position: absolute; top: 10px; right: 10px; width: 24px; height: 24px;
  border: none; background: transparent; color: var(--platform-text-tertiary);
  cursor: pointer; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s ease;
}
.arch-info-panel__close:hover { background: var(--platform-bg-tertiary); color: var(--platform-text); }
.arch-info-panel__header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 10px; }
.arch-info-panel__icon { font-size: 30px; line-height: 1; flex-shrink: 0; }
.arch-info-panel__title { font-size: 15px; font-weight: 600; color: var(--platform-text); letter-spacing: -0.01em; line-height: 1.3; }
.arch-info-panel__layer { font-size: 11px; font-weight: 500; letter-spacing: 0.04em; margin-top: 2px; opacity: 0.8; }
.arch-info-panel__desc { margin: 0; font-size: 12px; line-height: 1.65; color: var(--platform-text-secondary); }

.arch-panel-slide-enter-active { transition: opacity 0.3s var(--platform-ease-smooth), transform 0.3s var(--platform-ease-spring); }
.arch-panel-slide-leave-active { transition: opacity 0.2s var(--platform-ease-smooth), transform 0.2s var(--platform-ease-smooth); }
.arch-panel-slide-enter-from { opacity: 0; transform: translateX(20px) scale(0.96); }
.arch-panel-slide-leave-to { opacity: 0; transform: translateX(20px) scale(0.96); }

.arch-legend {
  position: absolute; left: 16px; top: 16px; z-index: 3;
  display: flex; flex-direction: column; gap: 8px; padding: 12px 14px;
  background: color-mix(in srgb, var(--platform-bg-elevated) 65%, transparent);
  backdrop-filter: blur(10px); border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-sm); max-width: 210px;
}
.arch-legend__item { display: flex; align-items: flex-start; gap: 8px; }
.arch-legend__bar { width: 3px; height: 26px; border-radius: 2px; flex-shrink: 0; margin-top: 1px; }
.arch-legend__label { font-size: 11px; font-weight: 600; color: var(--platform-text); line-height: 1.4; }
.arch-legend__desc { font-size: 10px; color: var(--platform-text-tertiary); line-height: 1.4; font-weight: 400; margin-top: 1px; }

html[data-theme="dark"] .arch-node__label { text-shadow: 0 1px 8px rgba(0,0,0,0.8); }
</style>
