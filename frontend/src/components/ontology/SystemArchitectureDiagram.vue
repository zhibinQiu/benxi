<template>
  <div
    class="arch-wrapper"
    ref="wrapperRef"
    @mousedown="onDragStart"
    @mousemove="onDragMove"
    @mouseup="onDragEnd"
    @mouseleave="onDragEnd"
    @touchstart.prevent="onTouchStart"
    @touchmove.prevent="onTouchMove"
    @touchend="onDragEnd"
    :class="{ 'arch-wrapper--dragging': isDragging }"
  >
    <!-- 3D 场景容器 -->
    <div class="arch-scene">
      <div class="arch-pyramid">
        <!-- 金字塔骨架：连接相邻层的斜面支柱 -->
        <div
          v-for="strut in pyramidStruts"
          :key="strut.id"
          class="arch-strut"
          :style="strut.style"
        />

        <!-- 渲染每一层的轨道、节点和底座 -->
        <template v-for="(layer, li) in layers" :key="li">
          <!-- 轨道环 -->
          <div
            class="arch-ring-track"
            :style="ringTrackStyle(layer)"
          />
          <!-- 底座盘 -->
          <div
            class="arch-ring-disk"
            :style="ringDiskStyle(layer)"
          />
          <!-- 层标签 -->
          <div
            class="arch-layer-label"
            :style="layerLabelStyle(layer)"
          >
            <span class="arch-layer-label__dot" :style="{ background: layer.color }" />
            {{ layer.name }}
            <span class="arch-layer-label__count">{{ layer.nodes.length }}</span>
          </div>
          <!-- 节点 -->
          <div
            v-for="(node, ni) in layer.nodes"
            :key="`${li}-${ni}`"
            class="arch-node"
            :class="{ 'arch-node--hovered': hoveredNode === node, 'arch-node--active': activeNode === node }"
            :style="nodeStyle(layer, ni, li)"
            @mouseenter="onNodeEnter(node)"
            @mouseleave="onNodeLeave"
            @click.stop="onNodeClick(node, layer)"
          >
            <div class="arch-node__inner" :style="{ background: layer.color }">
              <span class="arch-node__icon">{{ node.icon }}</span>
            </div>
            <div class="arch-node__label" :style="{ color: layer.color }">
              {{ node.label }}
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 操作提示 -->
    <div class="arch-hint">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 8v8M8 12h8"/>
      </svg>
      拖拽旋转 · 点击节点查看详情
    </div>

    <!-- 信息面板（点击节点后展开） -->
    <Transition name="arch-panel-slide">
      <div v-if="activeNode" class="arch-info-panel" @click.stop>
        <button class="arch-info-panel__close" @click="activeNode = null">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l10 10M12 2L2 12"/></svg>
        </button>
        <div class="arch-info-panel__header">
          <span class="arch-info-panel__icon">{{ activeNode.icon }}</span>
          <div>
            <div class="arch-info-panel__title">{{ activeNode.label }}</div>
            <div class="arch-info-panel__layer" :style="{ color: activeLayer?.color }">
              {{ activeLayer?.name }}
            </div>
          </div>
        </div>
        <p class="arch-info-panel__desc">{{ activeNode.description }}</p>
      </div>
    </Transition>

    <!-- 图例 -->
    <div class="arch-legend">
      <div v-for="(layer, li) in layers" :key="li" class="arch-legend__item">
        <span class="arch-legend__bar" :style="{ background: layer.color }" />
        <span class="arch-legend__label">{{ layer.name }}</span>
        <span class="arch-legend__desc">{{ layer.description }}</span>
      </div>
    </div>

    <!-- 设计说明 -->
    <div class="arch-essay">
      <h4 class="arch-essay__title">金字塔分层架构</h4>
      <div class="arch-essay__body">
        <p>本析平台采用<strong>金字塔式</strong>分层架构：底部<strong>设施层</strong>（文档库、IAM、存储）是数据与权限的基石；中下层<strong>能力层</strong>封装可插拔的智能工具与技能包，由底层设施承载支撑；中上层<strong>语义层</strong>（本体 + 知识图谱）为数据赋予结构化含义；顶层<strong>智能体层</strong>俯瞰全局，感知、推理与编排调度下层全部能力。</p>
        <p>层与层之间通过骨架支柱相连，隐喻每层依赖并构建于下层之上。<strong>智能体不直接操作数据，而是通过工具调用下层能力</strong>——这正是分层解耦的设计哲学。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from "vue";

// ── 颜色 ──

const LAYER_COLORS = {
  infra: "#0ea5e9",
  skill: "#8b5cf6",
  semantic: "#f59e0b",
  agent: "#10b981",
};

// ── 分层数据（从下到上 = 金字塔从宽到窄）──

const layers = ref([
  {
    id: "infra",
    name: "平台设施层",
    color: LAYER_COLORS.infra,
    radius: 240,
    yOffset: -160,
    description: "数据存储、身份权限与外部智能引擎",
    nodes: [
      { label: "文档库", icon: "📄", description: "分级 scope 文档管理，支持版本控制、单文档 ACL、回收站。MinIO 存储二进制，PostgreSQL 管理元数据。" },
      { label: "IAM", icon: "🔐", description: "用户/部门/角色管理，JWT 无状态鉴权，RBAC 功能权限细粒度控制。平台 ACL 为唯一权限真相。" },
      { label: "PostgreSQL", icon: "🗄️", description: "主数据存储，事务保障 schema migrate。承载用户、文档、任务、知识链接等全部结构化数据。" },
      { label: "MinIO", icon: "💾", description: "文档二进制与版本文件的分布式对象存储。前端通过 presigned URL 直传，避免 API 超时。" },
      { label: "Redis", icon: "⚡", description: "Celery broker 与缓存层。任务状态与重要数据仍以 DB 为准，Redis 可丢。" },
      { label: "翻译引擎", icon: "📝", description: "pdf2zh_next / BabelDOC 提供版式保留 PDF 翻译。Celery 监控异步任务进度。" },
      { label: "RAGFlow", icon: "🔍", description: "文档解析与向量检索后端。可选栈，通过 KnowledgeGateway 统一对接，支持 iframe 问答嵌入。" },
      { label: "语音服务", icon: "🎤", description: "FunASR Docker 转写 + CAM++ 说话人分离。录音文件自动转文字与智能总结。" },
    ],
  },
  {
    id: "skill",
    name: "能力层",
    color: LAYER_COLORS.skill,
    radius: 180,
    yOffset: -40,
    description: "可插拔的智能工具与技能包",
    nodes: [
      { label: "知识问答", icon: "💬", description: "RAGFlow 检索增强生成 + iframe 嵌入。支持个人/部门/公司三级知识库隔离。" },
      { label: "文档智能", icon: "🤖", description: "PDF 翻译与文档对比。异步任务模型，权限贯穿全文检索与差异对比。" },
      { label: "Skill 框架", icon: "🧩", description: "SKILL.md 驱动的技能注册与执行引擎。支持 catalog 发现、playbook 指令、上传技能包。" },
      { label: "搜索检索", icon: "🔎", description: "SearXNG 元搜索引擎 + 平台内文档检索。允许 LLM 通过 research tool 按需调用。" },
      { label: "文档对比", icon: "📊", description: "异步 diff 引擎，语义检索与色系分离。平台侧 allowed_document_ids 白名单过滤。" },
      { label: "内容订阅", icon: "📡", description: "网站收藏与公众号 feed。web_article_fetcher + DeepSeek 摘要，可选导入文档库。" },
    ],
  },
  {
    id: "semantic",
    name: "语义层",
    color: LAYER_COLORS.semantic,
    radius: 130,
    yOffset: 60,
    description: "为知识赋予结构化含义",
    nodes: [
      { label: "本体论", icon: "🧬", description: "实体类型、关系类型与公理规则的结构化建模。支持从组织、智能体、文档抽取并同步。" },
      { label: "知识图谱", icon: "🕸️", description: "Neo4j 图数据库存储实体-关系网络。通过 graph 包统一管理，支撑推理与关联发现。" },
      { label: "语义推理", icon: "🔗", description: "本体公理驱动的推理引擎。基于 OWL 规则推导隐含关系，增强知识问答的语义深度。" },
    ],
  },
  {
    id: "agent",
    name: "智能体层",
    color: LAYER_COLORS.agent,
    radius: 90,
    yOffset: 160,
    description: "感知、规划与执行，统筹全局",
    nodes: [
      { label: "调度智能体", icon: "🧠", description: "任务感知与路由核心。基于 AgentLoopSession 短会话，I/O 前释放 PG 连接，避免连接池占满。" },
      { label: "工具循环", icon: "🔄", description: "AgentToolLoop 执行引擎。LLM 通过 research / load / memory 等工具按需调用能力层。" },
      { label: "AI 对话", icon: "💭", description: "流式对话服务。支持多轮上下文、附件上传、Skill 激活，以 streaming 方式推送回复。" },
      { label: "多智能体", icon: "👥", description: "AIP 智能体互联协议。支持智能体发现、调用、外部登记，AgentKit 包拆分架构。" },
    ],
  },
]);

// ── 状态 ──

const wrapperRef = ref(null);
const rotationAngle = ref(0);
const hoveredNode = ref(null);
const activeNode = ref(null);
const isDragging = ref(false);

const activeLayer = computed(() => {
  if (!activeNode.value) return null;
  return layers.value.find((l) => l.nodes.includes(activeNode.value));
});

// ── 拖拽 ──

let dragStartX = 0;
let dragStartAngle = 0;

function getClientX(e) {
  return e.touches ? e.touches[0].clientX : e.clientX;
}

function onDragStart(e) {
  if (e.button !== 0) return;
  dragStartX = getClientX(e);
  dragStartAngle = rotationAngle.value;
  isDragging.value = true;
}

function onTouchStart(e) {
  dragStartX = getClientX(e);
  dragStartAngle = rotationAngle.value;
  isDragging.value = true;
}

function onDragMove(e) {
  if (!isDragging.value) return;
  const clientX = getClientX(e);
  const delta = clientX - dragStartX;
  rotationAngle.value = dragStartAngle + delta * 0.6;
  updateNodes();
}

function onTouchMove(e) {
  if (!isDragging.value) return;
  const clientX = getClientX(e);
  const delta = clientX - dragStartX;
  rotationAngle.value = dragStartAngle + delta * 0.6;
  updateNodes();
}

function onDragEnd() {
  isDragging.value = false;
}

// ── 金字塔支柱 ──

const STRUT_COUNT = 6;

const pyramidStruts = computed(() => {
  const result = [];
  const raw = layers.value;
  if (raw.length < 2) return result;

  for (let si = 0; si < STRUT_COUNT; si++) {
    const angle = (si / STRUT_COUNT) * Math.PI * 2;
    for (let li = 0; li < raw.length - 1; li++) {
      const bottom = raw[li];
      const top = raw[li + 1];
      const bx = bottom.radius * Math.sin(angle);
      const bz = bottom.radius * Math.cos(angle);
      const tx = top.radius * Math.sin(angle);
      const tz = top.radius * Math.cos(angle);
      const by = bottom.yOffset;
      const ty = top.yOffset;

      const midX = (bx + tx) / 2;
      const midZ = (bz + tz) / 2;
      const midY = (by + ty) / 2;
      const dx = tx - bx;
      const dz = tz - bz;
      const dy = ty - by;
      const length = Math.sqrt(dx * dx + dy * dy + dz * dz);
      const angleY = Math.atan2(dx, dz) * (180 / Math.PI);
      const angleX = Math.atan2(dy, Math.sqrt(dx * dx + dz * dz)) * (180 / Math.PI);

      result.push({
        id: `strut-${si}-${li}`,
        style: {
          width: `${length}px`,
          height: "2px",
          transform: `translate3d(${midX}px, ${midY}px, ${midZ}px) rotateY(${angleY}deg) rotateX(${-angleX}deg)`,
          background: `linear-gradient(90deg, ${bottom.color}44, ${top.color}44)`,
        },
      });
    }
  }
  return result;
});

// ── 节点位置计算 ──

const nodePositions = reactive(new Map());

function updateNodes() {
  const angle = rotationAngle.value;
  for (const layer of layers.value) {
    const count = layer.nodes.length;
    for (let i = 0; i < count; i++) {
      const itemAngle = (i / count) * Math.PI * 2;
      const worldAngle = itemAngle + angle * Math.PI / 180 * 0.002;
      const x = layer.radius * Math.sin(worldAngle);
      const z = layer.radius * Math.cos(worldAngle);
      const y = layer.yOffset;
      nodePositions.set(`${layers.value.indexOf(layer)}-${i}`, { x, y, z, angle: worldAngle });
    }
  }
}

// ── 节点样式 ──

function nodeStyle(layer, index, layerIndex) {
  const key = `${layerIndex}-${index}`;
  const pos = nodePositions.get(key);
  if (!pos) return { display: "none" };

  const depthFactor = (pos.z + layer.radius) / (layer.radius * 2);
  const depthClamp = Math.max(0.4, Math.min(1, depthFactor * 1.2 + 0.3));
  const scale = depthClamp;
  const opacity = depthClamp;
  const tiltAngle = -Math.sin(pos.angle) * 6;
  const behind = pos.z < -layer.radius * 0.15;

  return {
    transform: `translate3d(${pos.x}px, ${pos.y}px, ${pos.z}px) scale(${scale}) rotateX(${tiltAngle}deg)`,
    opacity,
    zIndex: behind ? 0 : Math.round(pos.z + layer.radius + 300 - layerIndex * 20),
  };
}

function ringTrackStyle(layer) {
  return {
    width: `${layer.radius * 2 + 16}px`,
    height: `${layer.radius * 2 + 16}px`,
    transform: `translate3d(-50%, -50%, -2px) translateY(${layer.yOffset}px)`,
    borderColor: `${layer.color}30`,
    boxShadow: `inset 0 0 30px ${layer.color}06, 0 0 20px ${layer.color}04`,
  };
}

function ringDiskStyle(layer) {
  return {
    width: `${layer.radius * 2}px`,
    height: `${layer.radius * 2}px`,
    transform: `translate3d(-50%, -50%, 0) translateY(${layer.yOffset}px)`,
    background: `radial-gradient(circle, ${layer.color}10 0%, ${layer.color}04 40%, transparent 70%)`,
    borderColor: `${layer.color}15`,
  };
}

function layerLabelStyle(layer) {
  return {
    transform: `translate3d(-50%, ${layer.yOffset}px, ${layer.radius + 8}px)`,
    color: layer.color,
  };
}

// ── 鼠标交互 ──

function onNodeEnter(node) {
  hoveredNode.value = node;
}

function onNodeLeave() {
  hoveredNode.value = null;
}

function onNodeClick(node) {
  activeNode.value = node;
}

// ── 生命周期 ──

onMounted(() => {
  updateNodes();
});
</script>

<style scoped>
/* ── 容器 ── */
.arch-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 640px;
  overflow: hidden;
  background:
    radial-gradient(ellipse 60% 45% at 50% 55%, color-mix(in srgb, var(--platform-accent) 5%, transparent), transparent 75%);
  border-radius: var(--platform-radius);
  user-select: none;
  cursor: grab;
}

.arch-wrapper--dragging {
  cursor: grabbing;
}

/* ── 3D 场景 ── */
.arch-scene {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 30px;
  perspective: 900px;
  perspective-origin: 50% 20%;
}

.arch-pyramid {
  position: relative;
  width: 0;
  height: 0;
  transform-style: preserve-3d;
  transform: rotateX(22deg) rotateY(-15deg);
}

/* ── 骨架支柱 ── */
.arch-strut {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: left center;
  transform-style: preserve-3d;
  pointer-events: none;
  opacity: 0.5;
}

/* ── 轨道环 ── */
.arch-ring-track {
  position: absolute;
  top: 50%;
  left: 50%;
  border-radius: 50%;
  border: 1.5px solid;
  transform-style: preserve-3d;
  pointer-events: none;
  backface-visibility: hidden;
}

/* ── 底座盘 ── */
.arch-ring-disk {
  position: absolute;
  top: 50%;
  left: 50%;
  border-radius: 50%;
  border: 1px solid;
  transform-style: preserve-3d;
  pointer-events: none;
  backface-visibility: hidden;
}

/* ── 层标签 ── */
.arch-layer-label {
  position: absolute;
  left: 50%;
  top: 50%;
  transform-style: preserve-3d;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  white-space: nowrap;
  pointer-events: none;
  display: flex;
  align-items: center;
  gap: 6px;
  text-shadow: 0 0 16px color-mix(in srgb, var(--platform-bg-base) 85%, transparent);
}

.arch-layer-label__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.arch-layer-label__count {
  font-size: 9px;
  opacity: 0.5;
  font-weight: 400;
  letter-spacing: 0.02em;
  background: color-mix(in srgb, currentColor 12%, transparent);
  padding: 0 5px;
  border-radius: 6px;
  line-height: 1.5;
}

/* ── 节点 ── */
.arch-node {
  position: absolute;
  left: 50%;
  top: 50%;
  transform-style: preserve-3d;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  transition: filter 0.3s ease, opacity 0.15s ease;
  backface-visibility: hidden;
  will-change: transform, opacity;
}

.arch-node:hover {
  z-index: 200 !important;
}

.arch-node__inner {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  box-shadow:
    0 0 0 2px color-mix(in srgb, currentColor 18%, transparent),
    0 4px 14px color-mix(in srgb, currentColor 22%, transparent);
  transition:
    transform 0.3s var(--platform-ease-spring),
    box-shadow 0.3s ease;
  position: relative;
  color: #fff;
}

.arch-node__inner::after {
  content: "";
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 1.5px solid color-mix(in srgb, currentColor 20%, transparent);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.arch-node--hovered .arch-node__inner {
  transform: scale(1.2);
  box-shadow:
    0 0 0 4px color-mix(in srgb, currentColor 30%, transparent),
    0 8px 28px color-mix(in srgb, currentColor 35%, transparent);
}

.arch-node--hovered .arch-node__inner::after {
  opacity: 1;
  border-color: color-mix(in srgb, currentColor 40%, transparent);
}

.arch-node--active .arch-node__inner {
  transform: scale(1.14);
  box-shadow:
    0 0 0 5px color-mix(in srgb, currentColor 40%, transparent),
    0 0 36px color-mix(in srgb, currentColor 30%, transparent);
}

.arch-node--active .arch-node__inner::after {
  opacity: 1;
  border-color: color-mix(in srgb, currentColor 50%, transparent);
}

.arch-node__icon {
  line-height: 1;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.15));
}

.arch-node__label {
  font-size: 10px;
  font-weight: 500;
  white-space: nowrap;
  letter-spacing: 0.02em;
  opacity: 0.85;
  text-shadow: 0 1px 4px color-mix(in srgb, var(--platform-bg-base) 70%, transparent);
  max-width: 84px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.arch-node--hovered .arch-node__label {
  opacity: 1;
}

/* ── 操作提示 ── */
.arch-hint {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: color-mix(in srgb, var(--platform-bg-elevated) 75%, transparent);
  backdrop-filter: blur(10px);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-pill);
  font-size: 11px;
  color: var(--platform-text-tertiary);
  opacity: 0.7;
  pointer-events: none;
}

.arch-hint svg {
  opacity: 0.5;
  flex-shrink: 0;
}

/* ── 信息面板 ── */
.arch-info-panel {
  position: absolute;
  right: 20px;
  top: 20px;
  width: 280px;
  padding: 20px;
  background: color-mix(in srgb, var(--platform-bg-elevated) 92%, transparent);
  backdrop-filter: blur(16px);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius);
  box-shadow: var(--platform-modal-shadow);
}

.arch-info-panel__close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--platform-text-tertiary);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
}

.arch-info-panel__close:hover {
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
}

.arch-info-panel__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.arch-info-panel__icon {
  font-size: 28px;
  line-height: 1;
  flex-shrink: 0;
}

.arch-info-panel__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--platform-text);
  letter-spacing: -0.01em;
  line-height: 1.3;
}

.arch-info-panel__layer {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  margin-top: 2px;
  opacity: 0.8;
}

.arch-info-panel__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--platform-text-secondary);
}

/* ── 面板入场动画 ── */
.arch-panel-slide-enter-active {
  transition:
    opacity 0.3s var(--platform-ease-smooth),
    transform 0.3s var(--platform-ease-spring);
}
.arch-panel-slide-leave-active {
  transition:
    opacity 0.2s var(--platform-ease-smooth),
    transform 0.2s var(--platform-ease-smooth);
}
.arch-panel-slide-enter-from {
  opacity: 0;
  transform: translateX(20px) scale(0.96);
}
.arch-panel-slide-leave-to {
  opacity: 0;
  transform: translateX(20px) scale(0.96);
}

/* ── 图例 ── */
.arch-legend {
  position: absolute;
  left: 16px;
  top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--platform-bg-elevated) 70%, transparent);
  backdrop-filter: blur(8px);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-sm);
  max-width: 200px;
}

.arch-legend__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.arch-legend__bar {
  width: 3px;
  height: 24px;
  border-radius: 2px;
  flex-shrink: 0;
  margin-top: 1px;
}

.arch-legend__label {
  font-size: 11px;
  font-weight: 600;
  color: var(--platform-text);
  display: block;
  line-height: 1.4;
}

.arch-legend__desc {
  display: block;
  font-size: 10px;
  color: var(--platform-text-tertiary);
  line-height: 1.45;
  font-weight: 400;
  margin-top: 1px;
}

/* ── 设计说明 ── */
.arch-essay {
  position: absolute;
  left: 16px;
  bottom: 52px;
  max-width: 360px;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--platform-bg-elevated) 65%, transparent);
  backdrop-filter: blur(8px);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-sm);
}

.arch-essay__title {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--platform-text-tertiary);
}

.arch-essay__body {
  font-size: 11px;
  line-height: 1.65;
  color: var(--platform-text-tertiary);
}

.arch-essay__body p {
  margin: 0 0 6px;
}

.arch-essay__body p:last-child {
  margin-bottom: 0;
}

.arch-essay__body strong {
  color: var(--platform-text-secondary);
}

/* ── 暗色主题微调 ── */
html[data-theme="dark"] .arch-layer-label {
  text-shadow: 0 0 20px rgba(0, 0, 0, 0.85);
}

html[data-theme="dark"] .arch-node__label {
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.75);
}
</style>
