export const ROSE_THREE_PRESET = {
  rotate: true,
  particleCount: 76,
  trailSpan: 0.31,
  durationMs: 5300,
  rotationDurationMs: 28000,
  pulseDurationMs: 4400,
  strokeWidth: 4.6,
  roseA: 9.2,
  roseABoost: 0.6,
  roseBreathBase: 0.72,
  roseBreathBoost: 0.28,
  roseScale: 3.25,
  point(progress, detailScale, config) {
    const t = progress * Math.PI * 2;
    const a = config.roseA + detailScale * config.roseABoost;
    const r =
      a * (config.roseBreathBase + detailScale * config.roseBreathBoost) * Math.cos(3 * t);
    return {
      x: 50 + Math.cos(t) * r * config.roseScale,
      y: 50 + Math.sin(t) * r * config.roseScale,
    };
  },
};

export const ROSE_FOUR_PRESET = {
  rotate: true,
  particleCount: 140,
  trailSpan: 0.12,
  durationMs: 9500,
  rotationDurationMs: 60000,
  pulseDurationMs: 4500,
  strokeWidth: 4.6,
  roseA: 14,
  roseABoost: 0.6,
  roseBreathBase: 0.72,
  roseBreathBoost: 0.8,
  roseScale: 5,
  point(progress, detailScale, config) {
    const t = progress * Math.PI * 2;
    const a = config.roseA + detailScale * config.roseABoost;
    const r =
      a * (config.roseBreathBase + detailScale * config.roseBreathBoost) * Math.cos(4 * t);
    return {
      x: 50 + Math.cos(t) * r * config.roseScale,
      y: 50 + Math.sin(t) * r * config.roseScale,
    };
  },
};

export const THINKING_TRAIL_PRESET = {
  rotate: true,
  particleCount: 64,
  trailSpan: 0.38,
  durationMs: 4600,
  rotationDurationMs: 28000,
  pulseDurationMs: 4200,
  strokeWidth: 5.5,
  baseRadius: 7,
  detailAmplitude: 3,
  petalCount: 7,
  curveScale: 3.9,
  point(progress, detailScale, config) {
    const t = progress * Math.PI * 2;
    const petals = Math.round(config.petalCount);
    const x =
      config.baseRadius * Math.cos(t) -
      config.detailAmplitude * detailScale * Math.cos(petals * t);
    const y =
      config.baseRadius * Math.sin(t) -
      config.detailAmplitude * detailScale * Math.sin(petals * t);
    return {
      x: 50 + x * config.curveScale,
      y: 50 + y * config.curveScale,
    };
  },
};

export const CURVE_PRESETS = {
  "rose-three": ROSE_THREE_PRESET,
  "rose-four": ROSE_FOUR_PRESET,
  "thinking-trail": THINKING_TRAIL_PRESET,
};

export function getCurvePreset(name = "rose-three") {
  return CURVE_PRESETS[name] ?? ROSE_THREE_PRESET;
}

export function normalizeCurveProgress(progress) {
  return ((progress % 1) + 1) % 1;
}

export function getCurveDetailScale(time, config) {
  const pulseProgress = (time % config.pulseDurationMs) / config.pulseDurationMs;
  const pulseAngle = pulseProgress * Math.PI * 2;
  return 0.52 + ((Math.sin(pulseAngle + 0.55) + 1) / 2) * 0.48;
}

export function getCurveRotation(time, config) {
  if (!config.rotate) return 0;
  return -((time % config.rotationDurationMs) / config.rotationDurationMs) * 360;
}

export function curveConfigForSize(presetName, pixelSize) {
  const base = getCurvePreset(presetName);
  const scale = pixelSize / 88;
  return {
    ...base,
    particleCount: Math.max(20, Math.round(base.particleCount * Math.sqrt(scale))),
    strokeWidth: Math.max(1.4, base.strokeWidth * scale),
  };
}

export function curveConfigForBackground(presetName, pixelSize) {
  const base = curveConfigForSize(presetName, pixelSize);
  /** >1 表示更慢：粒子轨迹、整体旋转、呼吸缩放 */
  const speedFactor = 1.38;
  return {
    ...base,
    particleCount: Math.max(20, Math.round(base.particleCount * 0.4)),
    strokeWidth: Math.max(1.2, base.strokeWidth * 0.78),
    durationMs: Math.round(base.durationMs * speedFactor),
    rotationDurationMs: Math.round(base.rotationDurationMs * speedFactor),
    pulseDurationMs: Math.round(base.pulseDurationMs * speedFactor),
  };
}

/** 按钮 / 行内小尺寸：减少粒子，避免拥挤 */
export function curveConfigForInline(presetName, pixelSize) {
  const base = curveConfigForSize(presetName, pixelSize);
  return {
    ...base,
    particleCount: Math.max(10, Math.round(base.particleCount * 0.32)),
    strokeWidth: Math.max(1, base.strokeWidth * 0.72),
    trailSpan: Math.min(base.trailSpan, 0.22),
  };
}

export function buildCurvePath(detailScale, config, steps = 480) {
  return Array.from({ length: steps + 1 }, (_, index) => {
    const point = config.point(index / steps, detailScale, config);
    return `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
  }).join(" ");
}

export function getCurveParticle(index, progress, detailScale, config) {
  const tailOffset = index / (config.particleCount - 1);
  const point = config.point(
    normalizeCurveProgress(progress - tailOffset * config.trailSpan),
    detailScale,
    config
  );
  const fade = Math.pow(1 - tailOffset, 0.56);
  return {
    x: point.x,
    y: point.y,
    radius: 0.9 + fade * 2.7,
    opacity: 0.04 + fade * 0.96,
  };
}
