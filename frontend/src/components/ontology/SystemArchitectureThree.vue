<template>
  <div class="three-arch" ref="containerRef">
    <div ref="canvasWrapperRef" class="three-arch__canvas" />

    <!-- 指示线 SVG -->
    <svg class="three-arch__lines" aria-hidden="true">
      <line
        v-for="layer in lineEndpoints"
        :key="layer.id"
        :x1="layer.x1"
        :y1="layer.y1"
        :x2="layer.x2"
        :y2="layer.y2"
        :stroke="layer.color"
        stroke-width="1"
        stroke-dasharray="3 3"
        :opacity="activeLayer?.id === layer.id ? 0.6 : 0.2"
        class="three-arch__connector"
        :class="{ 'three-arch__connector--active': activeLayer?.id === layer.id }"
      />
    </svg>

    <!-- 层标题（右侧可点击） -->
    <div class="three-arch__labels">
      <button
        v-for="layer in layerLabels"
        :key="layer.id"
        class="three-arch__label"
        :class="{ 'three-arch__label--active': activeLayer?.id === layer.id }"
        :style="{ position: 'absolute', top: `${layer.y}%`, color: layer.color }"
        @click.stop="toggleLayerInfo(layer.id)"
      >
        <span class="three-arch__label-text">{{ layer.name }}</span>
      </button>
    </div>

    <!-- 信息卡片 -->
    <Transition name="arch-card">
      <div
        v-if="activeLayer"
        class="three-arch__card"
        :style="{ '--card-accent': activeLayer.color, top: `${activeLayer.cardTop}%` }"
        @click.stop
      >
        <div class="three-arch__card-header">
          <span class="three-arch__card-title">{{ activeLayer.name }}</span>
          <button class="three-arch__card-close" @click="activeLayer = null">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2l8 8M10 2l-8 8"/></svg>
          </button>
        </div>
        <p class="three-arch__card-desc">{{ activeLayer.philosophy }}</p>
        <div class="three-arch__card-tools">
          <span
            v-for="tool in activeLayer.tools"
            :key="tool"
            class="three-arch__card-tool"
            :style="{ background: `${activeLayer.color}12`, color: activeLayer.color }"
          >{{ tool }}</span>
        </div>
      </div>
    </Transition>

    <!-- hover 提示 -->
    <div
      v-if="hoverLabel"
      class="three-arch__hover-tip"
      :style="{ left: `${hoverLabel.x}px`, top: `${hoverLabel.y}px`, color: hoverLabel.color }"
    >{{ hoverLabel.text }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const COLORS = {
  infra: "#4d94ff",
  skill: "#a78bfa",
  semantic: "#f59e0b",
  agent: "#34d399",
};

// 每层渐变终点色（主色→偏移色）
const GRADIENT_TO = {
  infra: "#4dd4ff",
  skill: "#d48cfa",
  semantic: "#f5d00b",
  agent: "#34d3d3",
};

const NODE_LABELS = {
  infra: ["文档库", "数据库", "对象存储", "缓存", "翻译引擎", "切片库"],
  skill: ["知识问答", "文档智能", "技能框架", "搜索检索", "工具"],
  semantic: ["本体论", "知识图谱", "语义推理"],
  agent: ["调度智能体", "工具循环", "AI 对话", "多智能体"],
};

const LAYER_CONFIG = [
  {
    id: "infra", name: "平台设施层", color: COLORS.infra,
    gradientColor: GRADIENT_TO.infra,
    radius: 1.8, y: -1.0, nodeCount: 6,
    philosophy: "以文档库、数据库、对象存储、切片库等基础服务为底座，构建安全、可靠、可扩展的数据与权限基石。一切上层智能都建立在稳固的基础设施之上——这既是工程原则，也是设计哲学：没有坚实的地基，就没有高耸的塔尖。",
    tools: ["文档库", "数据库", "对象存储", "缓存", "翻译引擎", "切片库", "语音服务"],
    nodeLabels: NODE_LABELS.infra,
  },
  {
    id: "skill", name: "能力层", color: COLORS.skill,
    gradientColor: GRADIENT_TO.skill,
    radius: 1.38, y: 0.05, nodeCount: 5,
    philosophy: "知识问答、文档智能、搜索检索——这些可插拔的技能与工具构成了平台的「能力之环」。每个能力都是独立的智能单元，通过统一的注册与执行引擎被灵活调度。这种插件式架构体现了「高内聚、低耦合」的设计理念：每个技能专注做好一件事，组合起来却能应对无限场景。",
    tools: ["知识问答", "文档智能", "技能框架", "搜索检索", "文档对比", "工具"],
    nodeLabels: NODE_LABELS.skill,
  },
  {
    id: "semantic", name: "语义层", color: COLORS.semantic,
    gradientColor: GRADIENT_TO.semantic,
    radius: 0.95, y: 1.1, nodeCount: 3,
    philosophy: "本体论定义了「世界如何被描述」——实体类型、关系类型、公理规则；知识图谱则将描述付诸实践，用图结构承载关联与推理。这一层的核心哲学是：让机器理解语义，而非仅仅匹配关键词。通过语义推理规则，平台从「搜索」进化到「认知」。",
    tools: ["本体论", "知识图谱", "语义推理"],
    nodeLabels: NODE_LABELS.semantic,
  },
  {
    id: "agent", name: "智能体层", color: COLORS.agent,
    gradientColor: GRADIENT_TO.agent,
    radius: 0.5, y: 2.1, nodeCount: 4,
    philosophy: "调度智能体、工具循环、AI 对话、多智能体协作——这是平台的「大脑与双手」。Agent 层统筹感知、规划与执行：它理解用户意图，分解任务，调度技能与工具，最终交付结果。核心设计哲学是「感知-思考-行动」循环，以及通过互联协议实现多智能体联邦协作。",
    tools: ["调度智能体", "工具循环", "AI 对话", "多智能体"],
    nodeLabels: NODE_LABELS.agent,
  },
];

// ── 位置映射 ──
const minY = -1.6, maxY = 3.1;
const layerLabels = LAYER_CONFIG.map((l) => {
  const pct = 100 - ((l.y - minY) / (maxY - minY)) * 100;
  return { ...l, y: Math.max(10, Math.min(88, pct)) };
});

const lineEndpoints = computed(() =>
  LAYER_CONFIG.map((l) => {
    const pct = 100 - ((l.y - minY) / (maxY - minY)) * 100;
    const y = Math.max(10, Math.min(88, pct));
    return { id: l.id, color: l.color, x1: 24, y1: y, x2: 50, y2: y };
  })
);

// ── 状态 ──
const activeLayer = ref(null);
const hoverLabel = ref(null);
const containerRef = ref(null);
const canvasWrapperRef = ref(null);

function toggleLayerInfo(id) {
  if (activeLayer.value?.id === id) {
    activeLayer.value = null;
  } else {
    const layer = layerLabels.find((l) => l.id === id);
    activeLayer.value = { ...layer, cardTop: Math.max(2, layer.y - 2) };
  }
}

// ── Three.js ──
let scene, camera, renderer, controls;
let animFrameId = null;
const nodeMeshes = [];
const nodeDataMap = new Map();
let raycaster, pointer;

// ── 方形辅助函数 ──

/** 沿方形周长均匀分布节点 */
function squarePerimeterPos(index, total, radius) {
  const perimeter = 8 * radius;
  const step = perimeter / total;
  const d = index * step;
  const sideLen = 2 * radius;
  const side = Math.floor(d / sideLen) % 4;
  const p = (d - side * sideLen) / radius - 1; // -1..1
  let x, z;
  switch (side) {
    case 0: x = p * radius; z = -radius; break; // 底边
    case 1: x = radius; z = p * radius; break;   // 右边
    case 2: x = -p * radius; z = radius; break;  // 顶边
    case 3: x = -radius; z = -p * radius; break; // 左边
  }
  return { x, z };
}

/** 沿方形周长向外偏移一点（标签位置） */
function squareLabelOffset(index, total, radius, offset) {
  const pos = squarePerimeterPos(index, total, radius);
  const sideLen = 2 * radius;
  const perimeter = 8 * radius;
  const step = perimeter / total;
  const d = index * step;
  const side = Math.floor(d / sideLen) % 4;
  let dx = 0, dz = 0;
  switch (side) {
    case 0: dz = -offset; break;
    case 1: dx = offset; break;
    case 2: dz = offset; break;
    case 3: dx = -offset; break;
  }
  return { x: pos.x + dx, z: pos.z + dz };
}

/** 获取方形 4 个角点 */
function squareCorners(radius, y) {
  const r = radius;
  return [
    new THREE.Vector3(-r, y, -r),
    new THREE.Vector3( r, y, -r),
    new THREE.Vector3( r, y,  r),
    new THREE.Vector3(-r, y,  r),
  ];
}

// ── 构建方形环（渐变 + 垂直厚度） ──
function buildSquareRing(cfg) {
  const r = cfg.radius;
  const thickness = 0.04;
  const ringHeight = 0.10;
  const inner = r - thickness;
  const c1 = new THREE.Color(cfg.color);
  const c2 = new THREE.Color(cfg.gradientColor);

  const shape = new THREE.Shape();
  shape.moveTo(-r, -r);
  shape.lineTo( r, -r);
  shape.lineTo( r,  r);
  shape.lineTo(-r,  r);
  shape.closePath();

  const hole = new THREE.Path();
  hole.moveTo(-inner, -inner);
  hole.lineTo( inner, -inner);
  hole.lineTo( inner,  inner);
  hole.lineTo(-inner,  inner);
  hole.closePath();
  shape.holes.push(hole);

  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: ringHeight,
    bevelEnabled: false,
  });
  geo.translate(0, 0, -ringHeight / 2);

  const pos = geo.getAttribute("position");
  const colsArr = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const px = pos.getX(i);
    const py = pos.getY(i);
    const angle = Math.atan2(py, px);
    const t = ((angle / (2 * Math.PI)) + 0.5) % 1.0;
    const mixed = c1.clone().lerp(c2, t);
    colsArr[i * 3] = mixed.r;
    colsArr[i * 3 + 1] = mixed.g;
    colsArr[i * 3 + 2] = mixed.b;
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colsArr, 3));

  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.65,
    side: THREE.DoubleSide,
    depthWrite: false,
  }));
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = cfg.y;
  return mesh;
}

// ── 构建方形发光环（薄片，置于环顶） ──
function buildGlowSquareRing(cfg) {
  const r = cfg.radius + 0.06;
  const inner = r - 0.012;
  const c = new THREE.Color(cfg.color);

  const shape = new THREE.Shape();
  shape.moveTo(-r, -r);
  shape.lineTo( r, -r);
  shape.lineTo( r,  r);
  shape.lineTo(-r,  r);
  shape.closePath();

  const hole = new THREE.Path();
  hole.moveTo(-inner, -inner);
  hole.lineTo( inner, -inner);
  hole.lineTo( inner,  inner);
  hole.lineTo(-inner,  inner);
  hole.closePath();
  shape.holes.push(hole);

  const geo = new THREE.ShapeGeometry(shape);
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: c,
    transparent: true,
    opacity: 0.10,
    side: THREE.DoubleSide,
    depthWrite: false,
  }));
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = cfg.y - 0.05;
  return mesh;
}

function buildSquareDisk(cfg) {
  const r = cfg.radius - 0.1;
  const c = new THREE.Color(cfg.color);

  const shape = new THREE.Shape();
  const s = r * 0.85;
  shape.moveTo(-s, -s);
  shape.lineTo( s, -s);
  shape.lineTo( s,  s);
  shape.lineTo(-s,  s);
  shape.closePath();

  const geo = new THREE.ShapeGeometry(shape);
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: c,
    transparent: true,
    opacity: 0.018,
    side: THREE.DoubleSide,
    depthWrite: false,
  }));
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = cfg.y;
  return mesh;
}

function makeTextSprite(text, color, opacity = 0.7) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const fontSize = 28;
  ctx.font = `500 ${fontSize}px "Inter","PingFang SC","Microsoft YaHei",sans-serif`;
  const tw = ctx.measureText(text).width;
  const pad = 10;
  const r = 5;
  canvas.width = tw + pad * 2;
  canvas.height = fontSize * 1.5;
  const w = canvas.width, h = canvas.height;

  ctx.fillStyle = "rgba(8,8,14,0.45)";
  ctx.beginPath();
  ctx.moveTo(r, 0); ctx.lineTo(w - r, 0);
  ctx.quadraticCurveTo(w, 0, w, r); ctx.lineTo(w, h - r);
  ctx.quadraticCurveTo(w, h, w - r, h); ctx.lineTo(r, h);
  ctx.quadraticCurveTo(0, h, 0, h - r); ctx.lineTo(0, r);
  ctx.quadraticCurveTo(0, 0, r, 0); ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.15;
  ctx.stroke();
  ctx.globalAlpha = 1;

  ctx.font = `500 ${fontSize}px "Inter","PingFang SC","Microsoft YaHei",sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.globalAlpha = opacity;
  ctx.fillText(text, w / 2, h / 2);

  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: true, depthWrite: false, opacity });
  const sprite = new THREE.Sprite(mat);
  const aspect = canvas.width / canvas.height;
  sprite.scale.set(aspect * 0.22, 0.22, 1);
  return sprite;
}

function init() {
  const wrapper = canvasWrapperRef.value;
  if (!wrapper) return;
  const w = wrapper.clientWidth;
  const h = wrapper.clientHeight;

  scene = new THREE.Scene();
  const aspect = w / h;
  camera = new THREE.PerspectiveCamera(32, aspect, 0.1, 100);
  camera.position.set(5.5, 3.0, 7.0);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.85;
  wrapper.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enableZoom = false;
  controls.minDistance = 4;
  controls.maxDistance = 20;
  controls.maxPolarAngle = Math.PI / 2.1;
  controls.minPolarAngle = Math.PI / 7;
  controls.target.set(0, 0.55, 0);
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.25;

  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const dl = new THREE.DirectionalLight(0xffffff, 1.2);
  dl.position.set(6, 10, 5);
  scene.add(dl);
  const fl = new THREE.DirectionalLight(0x8888ff, 0.35);
  fl.position.set(-5, 3, -6);
  scene.add(fl);
  const rl = new THREE.DirectionalLight(0xffffff, 0.2);
  rl.position.set(0, -5, 8);
  scene.add(rl);

  buildLayers();
  buildNodes();
  buildNodeLabels();
  buildConeWalls();

  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();
  renderer.domElement.addEventListener("click", onCanvasClick);
  renderer.domElement.addEventListener("pointermove", onCanvasMove);

  animate();
}

function buildLayers() {
  for (const cfg of LAYER_CONFIG) {
    scene.add(buildSquareDisk(cfg));
    scene.add(buildSquareRing(cfg));
    scene.add(buildGlowSquareRing(cfg));
  }
}

function buildNodes() {
  for (const cfg of LAYER_CONFIG) {
    const count = cfg.nodeCount;
    const color = new THREE.Color(cfg.color);
    const labels = cfg.nodeLabels || [];

    for (let i = 0; i < count; i++) {
      const { x, z } = squarePerimeterPos(i, count, cfg.radius);
      let mesh, extraMesh;

      if (cfg.id === "infra") {
        const geo = new THREE.BoxGeometry(0.18, 0.18, 0.18);
        const mat = new THREE.MeshPhysicalMaterial({
          color, emissive: color, emissiveIntensity: 0.05,
          metalness: 0.1, roughness: 0.4,
        });
        mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(x, cfg.y, z);
        const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.4 }));
        edge.position.copy(mesh.position);
        scene.add(edge);
      } else if (cfg.id === "skill") {
        const geo = new THREE.OctahedronGeometry(0.16);
        const mat = new THREE.MeshPhysicalMaterial({
          color, emissive: color, emissiveIntensity: 0.06,
          metalness: 0.15, roughness: 0.35, flatShading: true,
        });
        mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(x, cfg.y, z);
        const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.35 }));
        edge.position.copy(mesh.position);
        scene.add(edge);
      } else if (cfg.id === "semantic") {
        const geo = new THREE.IcosahedronGeometry(0.14);
        const mat = new THREE.MeshPhysicalMaterial({
          color, emissive: color, emissiveIntensity: 0.08,
          metalness: 0.05, roughness: 0.35, flatShading: true,
        });
        mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(x, cfg.y, z);
        const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.35 }));
        edge.position.copy(mesh.position);
        scene.add(edge);
      } else {
        const geo = new THREE.SphereGeometry(0.12, 10, 10);
        const mat = new THREE.MeshPhysicalMaterial({
          color, emissive: color, emissiveIntensity: 0.1,
          metalness: 0.05, roughness: 0.2,
        });
        mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(x, cfg.y, z);
        extraMesh = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.01, 6, 14), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.25 }));
        extraMesh.position.set(x, cfg.y, z);
        extraMesh.rotation.x = Math.PI / 2;
        scene.add(extraMesh);
      }

      scene.add(mesh);
      nodeMeshes.push(mesh);
      nodeDataMap.set(mesh, {
        layerId: cfg.id,
        label: labels[i % labels.length] || cfg.name,
      });
    }
  }
}

function buildNodeLabels() {
  for (const cfg of LAYER_CONFIG) {
    const count = cfg.nodeCount;
    const labels = cfg.nodeLabels || [];
    for (let i = 0; i < count; i++) {
      const label = labels[i % labels.length];
      if (!label) continue;
      const { x, z } = squareLabelOffset(i, count, cfg.radius, 0.5);
      const sprite = makeTextSprite(label, cfg.color, 0.7);
      sprite.position.set(x, cfg.y, z);
      scene.add(sprite);
    }
  }
}

function buildConeWalls() {
  const bottom = LAYER_CONFIG[0];
  const top = LAYER_CONFIG[LAYER_CONFIG.length - 1];
  const bCorners = squareCorners(bottom.radius, bottom.y);
  const tCorners = squareCorners(top.radius, top.y);

  const bc = new THREE.Color(bottom.color);
  const tc = new THREE.Color(top.color);

  for (let i = 0; i < 4; i++) {
    const b0 = bCorners[i];
    const b1 = bCorners[(i + 1) % 4];
    const t0 = tCorners[i];
    const t1 = tCorners[(i + 1) % 4];

    const verts = new Float32Array([
      b0.x, b0.y, b0.z, b1.x, b1.y, b1.z, t0.x, t0.y, t0.z,
      t1.x, t1.y, t1.z, t0.x, t0.y, t0.z, b1.x, b1.y, b1.z,
    ]);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(verts, 3));
    geo.computeVertexNormals();

    const colsArr = new Float32Array(18);
    for (let j = 0; j < 6; j++) {
      const c = j < 3 ? bc : tc;
      colsArr[j * 3] = c.r;
      colsArr[j * 3 + 1] = c.g;
      colsArr[j * 3 + 2] = c.b;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colsArr, 3));

    scene.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.02, side: THREE.DoubleSide, depthWrite: false,
    })));
  }

  // 各层角点连接线
  const allLayers = LAYER_CONFIG;
  for (let li = 0; li < allLayers.length - 1; li++) {
    const la = allLayers[li];
    const lb = allLayers[li + 1];
    const aCorners = squareCorners(la.radius, la.y);
    const bCorners2 = squareCorners(lb.radius, lb.y);
    for (let ci = 0; ci < 4; ci++) {
      scene.add(new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([aCorners[ci], bCorners2[ci]]),
        new THREE.LineBasicMaterial({
          color: new THREE.Color(la.color).lerp(new THREE.Color(lb.color), 0.5),
          transparent: true, opacity: 0.04,
        })
      ));
    }
  }
}

// ── 点击粒子 → 显示对应层卡片 ──
function onCanvasClick(e) {
  if (!renderer) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const intersects = raycaster.intersectObjects(nodeMeshes);
  if (intersects.length > 0) {
    const hit = intersects[0].object;
    const data = nodeDataMap.get(hit);
    if (data) toggleLayerInfo(data.layerId);
  }
}

// ── hover 节点时显示文字提示 ──
function onCanvasMove(e) {
  if (!renderer) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const intersects = raycaster.intersectObjects(nodeMeshes);

  if (intersects.length > 0) {
    const hit = intersects[0].object;
    const data = nodeDataMap.get(hit);
    if (data) {
      const cfg = LAYER_CONFIG.find((l) => l.id === data.layerId);
      hoverLabel.value = {
        text: data.label,
        color: cfg ? cfg.color : "#fff",
        x: e.clientX - containerRef.value.getBoundingClientRect().left + 12,
        y: e.clientY - containerRef.value.getBoundingClientRect().top - 6,
      };
      renderer.domElement.style.cursor = "pointer";
      return;
    }
  }
  hoverLabel.value = null;
  renderer.domElement.style.cursor = "grab";
}

function animate() {
  time += 0.01;
  for (let i = 0; i < nodeMeshes.length; i++) {
    nodeMeshes[i].position.y += Math.sin(time * 1.2 + i * 0.8) * 0.005;
  }
  controls.update();
  renderer.render(scene, camera);
  animFrameId = requestAnimationFrame(animate);
}

function onResize() {
  const wrapper = canvasWrapperRef.value;
  if (!wrapper || !renderer) return;
  const w = wrapper.clientWidth, h = wrapper.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}

onMounted(() => { init(); window.addEventListener("resize", onResize); });
onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId);
  if (renderer) {
    renderer.domElement.removeEventListener("click", onCanvasClick);
    renderer.domElement.removeEventListener("pointermove", onCanvasMove);
    renderer.dispose();
    renderer.domElement.remove();
  }
  window.removeEventListener("resize", onResize);
});
</script>

<style scoped>
.three-arch {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.three-arch__canvas {
  width: 100%;
  height: 100%;
}

.three-arch__canvas :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
  cursor: grab;
}

.three-arch__lines {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: none;
}

.three-arch__connector {
  transition: opacity 0.3s ease;
}

.three-arch__connector--active {
  stroke-dasharray: none !important;
  stroke-width: 1.5;
}

.three-arch__labels {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
}

.three-arch__label {
  display: flex;
  align-items: center;
  gap: 6px;
  transform: translateY(-50%) translateX(-50%);
  background: none;
  border: none;
  padding: 3px 8px;
  cursor: pointer;
  outline: none;
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
  pointer-events: auto;
  left: 50%;
  transition: filter 0.25s ease;
}

.three-arch__label:hover,
.three-arch__label--active {
  filter: brightness(1.5);
}

.three-arch__label-text {
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.03em;
  color: currentColor;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.5), 0 0 12px rgba(0, 0, 0, 0.25);
  opacity: 0.9;
  transition: opacity 0.25s ease, text-shadow 0.25s ease;
  white-space: nowrap;
}

.three-arch__label--active .three-arch__label-text,
.three-arch__label:hover .three-arch__label-text {
  opacity: 1;
  text-shadow: 0 0 12px currentColor, 0 1px 6px rgba(0, 0, 0, 0.5);
}

.three-arch__hover-tip {
  position: absolute;
  z-index: 4;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
  color: currentColor;
  background: rgba(8, 8, 14, 0.6);
  backdrop-filter: blur(8px);
  padding: 3px 8px;
  border-radius: 5px;
  transform: translateY(-50%);
  pointer-events: none;
  white-space: nowrap;
}

.three-arch__card {
  position: absolute;
  right: 8px;
  width: 200px;
  max-height: 250px;
  padding: 10px 12px 12px;
  background: rgba(8, 8, 14, 0.7);
  backdrop-filter: blur(20px) saturate(1.3);
  -webkit-backdrop-filter: blur(20px) saturate(1.3);
  border: 1px solid color-mix(in srgb, var(--card-accent) 20%, rgba(255, 255, 255, 0.05));
  border-radius: 10px;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 color-mix(in srgb, var(--card-accent) 8%, rgba(255, 255, 255, 0.04));
  z-index: 3;
  transform: translateY(-50%);
  overflow-y: auto;
}

.three-arch__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.three-arch__card-title {
  font-size: 13px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--card-accent);
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
}

.three-arch__card-close {
  width: 20px;
  height: 20px;
  border: none;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, color 0.15s ease;
}

.three-arch__card-close:hover {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
}

.three-arch__card-desc {
  margin: 0 0 8px;
  font-size: 10.5px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.6);
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
}

.three-arch__card-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.three-arch__card-tool {
  font-size: 9px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1.5;
  white-space: nowrap;
  font-family: var(--platform-font, "Inter", "PingFang SC", system-ui, sans-serif);
}

.arch-card-enter-active {
  transition: opacity 0.2s var(--platform-ease-smooth, ease), transform 0.2s var(--platform-ease-spring, ease);
}
.arch-card-leave-active {
  transition: opacity 0.12s var(--platform-ease-smooth, ease), transform 0.12s var(--platform-ease-smooth, ease);
}
.arch-card-enter-from {
  opacity: 0;
  transform: translateY(-50%) translateX(8px) scale(0.95);
}
.arch-card-leave-to {
  opacity: 0;
  transform: translateY(-50%) translateX(8px) scale(0.95);
}
</style>
