<template>
  <div class="arch-dna" ref="containerRef">
    <svg class="arch-dna__svg" viewBox="0 0 500 500" preserveAspectRatio="xMidYMid meet">
      <defs>
        <filter id="dna-glow-bright">
          <feGaussianBlur stdDeviation="3" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="dna-glow-soft">
          <feGaussianBlur stdDeviation="6" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      <!-- █ 1. 玫瑰曲线（源头动画） -->
      <!-- 亮线条 -->
      <path
        :d="rosePath(curveScale, 240)"
        :stroke="curveColor"
        stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"
        fill="none"
        opacity="0.35"
        :stroke-dasharray="dashArray"
        :stroke-dashoffset="dashOffset"
        class="dna-rose"
      />
      <!-- 光晕线条 -->
      <path
        :d="rosePath(curveScale, 240)"
        :stroke="curveColor"
        stroke-width="5"
        stroke-linecap="round"
        fill="none"
        opacity="0.06"
        filter="url(#dna-glow-soft)"
        class="dna-rose-glow"
      />
      <!-- 游走粒子（沿曲线） -->
      <circle
        v-for="(p, pi) in curveParticles" :key="'cp-'+pi"
        :cx="p.x" :cy="p.y" :r="p.r"
        :fill="curveColor"
        :opacity="p.opacity"
        filter="url(#dna-glow-bright)"
      />

      <!-- █ 2. 发散粒子（从曲线逃逸→架构节点） -->
      <circle
        v-for="(p, pi) in escapedParticles" :key="'ep-'+pi"
        :cx="p.x" :cy="p.y" :r="p.r"
        :fill="p.color"
        :opacity="p.opacity"
        :filter="p.glow ? 'url(#dna-glow-bright)' : undefined"
      />

      <!-- █ 3. 架构节点（目标位置） -->
      <g v-for="(zone, zi) in ZONES" :key="'z-'+zi">
        <!-- 区域光晕 -->
        <ellipse :cx="zone.cx" :cy="zone.cy" :rx="zone.rx" :ry="zone.ry"
          :fill="zone.color" opacity="0.03" class="dna-zone-bg"
        />

        <!-- 节点 -->
        <g v-for="(node, ni) in zone.nodes" :key="'n-'+zi+'-'+ni">
          <circle :cx="node.x" :cy="node.y" r="10"
            :fill="zone.color" opacity="0.04" class="dna-node-glow"
          />
          <circle :cx="node.x" :cy="node.y" r="3"
            :fill="zone.color"
            :opacity="activeZone?.id === zone.id ? 1 : 0.4"
            class="dna-node"
            @click.stop="toggleInfo(zone.id)"
          />
          <text :x="node.x" :y="node.y + 14"
            :fill="zone.color"
            font-size="4.5" font-weight="600" text-anchor="middle"
            :opacity="activeZone?.id === zone.id ? 0.9 : 0.35"
            class="dna-label"
          >{{ node.label }}</text>
        </g>

        <!-- 层名 -->
        <text :x="zone.tx" :y="zone.ty"
          :fill="zone.color"
          font-size="7.5" font-weight="650" text-anchor="middle" letter-spacing="0.06em"
          :opacity="activeZone?.id === zone.id ? 0.85 : 0.35"
          class="dna-zonename"
          @click.stop="toggleInfo(zone.id)"
        >{{ zone.name }}</text>
      </g>
    </svg>

    <!-- 信息卡片 -->
    <Transition name="dna-card">
      <div v-if="activeZone" class="dna-card"
        :style="{ '--card-accent': activeZone.color }" @click.stop
      >
        <div class="dna-card__header">
          <span class="dna-card__title">{{ activeZone.name }}</span>
          <button class="dna-card__close" @click="activeZone = null">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l8 8M10 2l-8 8"/></svg>
          </button>
        </div>
        <p class="dna-card__desc">{{ activeZone.desc }}</p>
        <div class="dna-card__tags">
          <span v-for="tag in activeZone.tags" :key="tag"
            class="dna-card__tag"
            :style="{ background: `${activeZone.color}12`, color: activeZone.color }"
          >{{ tag }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from "vue";

// ── 配色 ──
const COLORS = ["#4d94ff", "#a78bfa", "#f59e0b", "#34d399"];
const ZONES = [
  {
    id: "infra", name: "平台设施层", color: COLORS[0],
    cx: 250, cy: 430, rx: 110, ry: 44, tx: 250, ty: 460,
    count: 6,
    desc: "以文档库、数据库、对象存储、切片库等基础服务为底座，构建安全、可靠、可扩展的数据与权限基石。",
    tags: ["文档库","数据库","对象存储","缓存","翻译引擎","切片库","语音服务"],
  },
  {
    id: "skill", name: "能力层", color: COLORS[1],
    cx: 105, cy: 270, rx: 90, ry: 38, tx: 105, ty: 225,
    count: 5,
    desc: "知识问答、文档智能、搜索检索——这些可插拔的技能与工具构成了平台的「能力之环」。",
    tags: ["知识问答","文档智能","技能框架","搜索检索","文档对比","工具"],
  },
  {
    id: "semantic", name: "语义层", color: COLORS[2],
    cx: 395, cy: 270, rx: 90, ry: 38, tx: 395, ty: 225,
    count: 3,
    desc: "本体论定义了「世界如何被描述」，知识图谱用图结构承载关联与推理。核心哲学：让机器理解语义。",
    tags: ["本体论","知识图谱","语义推理"],
  },
  {
    id: "agent", name: "智能体层", color: COLORS[3],
    cx: 250, cy: 100, rx: 100, ry: 42, tx: 250, ty: 68,
    count: 4,
    desc: "调度智能体、工具循环、AI 对话、多智能体协作——统筹感知、规划与执行。",
    tags: ["调度智能体","工具循环","AI 对话","多智能体"],
  },
];

// 生成节点位置
const LABEL_MAP = {
  infra: ["文档库","数据库","对象存储","缓存","翻译引擎","切片库"],
  skill: ["知识问答","文档智能","技能框架","搜索检索","工具"],
  semantic: ["本体论","知识图谱","语义推理"],
  agent: ["调度智能体","工具循环","AI 对话","多智能体"],
};

for (const z of ZONES) {
  const nodes = [];
  for (let i = 0; i < z.count; i++) {
    const span = Math.PI * 0.7;
    const start = -Math.PI * 0.35;
    const a = start + (i / Math.max(1, z.count - 1)) * span;
    nodes.push({
      x: z.cx + Math.cos(a) * z.rx * 0.65,
      y: z.cy + Math.sin(a) * z.ry * 0.55,
      label: LABEL_MAP[z.id]?.[i] || "",
    });
  }
  z.nodes = nodes;
}

// ── 玫瑰曲线 ──
function rosePt(t, scale) {
  const a = 44 + 4 * scale;
  const r = a * (0.7 + scale * 0.3) * Math.cos(3 * t);
  return { x: 250 + Math.cos(t) * r, y: 250 + Math.sin(t) * r };
}
function rosePath(scale, steps = 240) {
  return Array.from({ length: steps + 1 }, (_, i) => {
    const p = rosePt((i / steps) * Math.PI * 2, scale);
    return `${i === 0 ? "M" : "L"}${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
  }).join(" ");
}

// ── 曲线动画（路径绘制 + 粒子沿曲线滑动） ──
const curveScale = ref(0.7);
const curveColor = "var(--platform-accent, #4d94ff)";
const dashOffset = ref(0);
const dashArray = "1400";

const CURVE_PARTICLE_COUNT = 40;
const curveParticles = reactive([]);

for (let i = 0; i < CURVE_PARTICLE_COUNT; i++) {
  curveParticles.push({
    progress: i / CURVE_PARTICLE_COUNT,
    speed: 0.08 + Math.random() * 0.06,
    r: 2.0 + Math.random() * 2.5,
    opacity: 0.3 + Math.random() * 0.6,
    x: 250, y: 250,
  });
}

// ── 逃逸粒子（从曲线飞向节点） ──
const ESCAPED_COUNT = 60;
const escapedParticles = reactive([]);

for (let i = 0; i < ESCAPED_COUNT; i++) {
  const zi = Math.floor(Math.random() * ZONES.length);
  const zone = ZONES[zi];
  const ni = Math.floor(Math.random() * zone.nodes.length);
  const node = zone.nodes[ni];
  escapedParticles.push({
    targetX: node.x, targetY: node.y,
    color: zone.color,
    progress: Math.random(),
    speed: 0.12 + Math.random() * 0.2,
    phase: Math.random() * Math.PI * 2,
    r: 1.2 + Math.random() * 2.0,
    opacity: 0.1,
    glow: Math.random() > 0.5,
    zoneId: zone.id,
    x: 250, y: 250,
  });
}

// ── 状态 ──
const activeZone = ref(null);

// ── 动画循环 ──
let animFrame = null;
let startTime = 0;

function animate(time) {
  if (!startTime) startTime = time;
  const t = time - startTime;
  const sec = t / 1000;

  // 曲线呼吸缩放
  curveScale.value = 0.65 + Math.sin(sec * 0.3) * 0.08;

  // 曲线绘制动画（虚线偏移）
  dashOffset.value = -(t * 0.04) % 1400;

  // 更新曲线粒子（沿曲线滑动）
  for (const p of curveParticles) {
    p.progress += p.speed * 0.005;
    if (p.progress > 1) p.progress -= 1;
    const pos = rosePt(p.progress * Math.PI * 2, curveScale.value);
    p.x = pos.x;
    p.y = pos.y;
    p.opacity = 0.2 + 0.5 * (0.5 + 0.5 * Math.sin(sec * 0.5 + p.progress * Math.PI * 2));
  }

  // 更新逃逸粒子
  for (const p of escapedParticles) {
    p.progress += p.speed * 0.003;
    if (p.progress > 1.3) {
      p.progress = -0.2;
      // 重置时换一个目标
      const zi = Math.floor(Math.random() * ZONES.length);
      const zone = ZONES[zi];
      const ni = Math.floor(Math.random() * zone.nodes.length);
      const node = zone.nodes[ni];
      p.targetX = node.x;
      p.targetY = node.y;
      p.color = zone.color;
      p.zoneId = zone.id;
      p.glow = Math.random() > 0.5;
    }

    const clamped = Math.max(0, Math.min(1, p.progress));
    // 从中心点飞向目标
    const ease = clamped < 0.5
      ? 2 * clamped * clamped
      : 1 - (1 - clamped) * (1 - clamped) * 2;

    // 带随机扰动
    const wobble = Math.sin(sec * 0.4 + p.phase) * 5 * (1 - ease);
    p.x = 250 + (p.targetX - 250) * ease + wobble;
    p.y = 250 + (p.targetY - 250) * ease + wobble;
    p.r = 1.2 + (1 - ease) * 1.8;
    p.opacity = 0.05 + 0.5 * (1 - ease);
  }

  animFrame = requestAnimationFrame(animate);
}

function toggleInfo(id) {
  if (activeZone.value?.id === id) activeZone.value = null;
  else activeZone.value = ZONES.find((z) => z.id === id);
}

onMounted(() => { animFrame = requestAnimationFrame(animate); });
onUnmounted(() => { if (animFrame) cancelAnimationFrame(animFrame); });
</script>

<style scoped>
.arch-dna {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 450px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse 50% 40% at 50% 50%, color-mix(in srgb, var(--platform-accent) 3%, transparent), transparent 80%);
  border-radius: var(--platform-radius);
}

.arch-dna__svg {
  width: 100%;
  height: 100%;
  max-width: 520px;
  max-height: 520px;
  overflow: visible;
}

/* ── 玫瑰曲线 ── */
.dna-rose {
  transition: d 0.3s ease;
}
.dna-rose-glow {
  transition: d 0.3s ease;
}

/* ── 区域背景 ── */
.dna-zone-bg {
  transition: opacity 0.3s ease;
}

/* ── 节点 ── */
.dna-node-glow {
  animation: dna-pulse 3.5s ease-in-out infinite alternate;
}
@keyframes dna-pulse {
  0% { opacity: 0.02; }
  100% { opacity: 0.08; }
}
.dna-node {
  cursor: pointer;
  transition: opacity 0.3s ease;
  filter: drop-shadow(0 0 3px currentColor);
}
.dna-node:hover {
  filter: drop-shadow(0 0 8px currentColor);
}
.dna-label {
  pointer-events: none;
  transition: opacity 0.3s ease;
}
.dna-zonename {
  cursor: pointer;
  transition: opacity 0.3s ease;
}
.dna-zonename:hover {
  opacity: 0.85 !important;
}

/* ── 信息卡片 ── */
.dna-card {
  position: absolute;
  right: 8px;
  bottom: 8px;
  width: 200px;
  max-height: 220px;
  padding: 10px 12px 12px;
  background: rgba(8, 8, 14, 0.7);
  backdrop-filter: blur(20px) saturate(1.3);
  -webkit-backdrop-filter: blur(20px) saturate(1.3);
  border: 1px solid color-mix(in srgb, var(--card-accent) 20%, rgba(255, 255, 255, 0.05));
  border-radius: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3), inset 0 1px 0 color-mix(in srgb, var(--card-accent) 8%, rgba(255, 255, 255, 0.04));
  z-index: 10;
  overflow-y: auto;
}
.dna-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.dna-card__title {
  font-size: 13px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--card-accent);
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
}
.dna-card__close {
  width: 20px; height: 20px;
  border: none;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease;
}
.dna-card__close:hover {
  background: rgba(255, 255, 255, 0.1); color: rgba(255, 255, 255, 0.7);
}
.dna-card__desc {
  margin: 0 0 8px; font-size: 10.5px; line-height: 1.6;
  color: rgba(255, 255, 255, 0.6);
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
}
.dna-card__tags { display: flex; flex-wrap: wrap; gap: 3px; }
.dna-card__tag {
  font-size: 9px; font-weight: 500; padding: 2px 6px; border-radius: 4px;
  line-height: 1.5; white-space: nowrap;
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
}

.dna-card-enter-active { transition: opacity 0.2s var(--platform-ease-smooth, ease), transform 0.2s var(--platform-ease-spring, ease); }
.dna-card-leave-active { transition: opacity 0.12s var(--platform-ease-smooth, ease), transform 0.12s var(--platform-ease-smooth, ease); }
.dna-card-enter-from { opacity: 0; transform: translateY(8px) scale(0.95); }
.dna-card-leave-to { opacity: 0; transform: translateY(8px) scale(0.95); }
</style>
