/** PDF 对比页高亮：bbox 坐标换算与文本层回退匹配 */

import { diffAnchorBlocks } from "./compareDocument.js";

/** 单框或同一 diff 累计高亮面积超过页面比例时视为误匹配 */
const MAX_BOX_AREA_RATIO = 0.55;
const MAX_DIFF_TOTAL_AREA_RATIO = 0.38;
const MIN_TEXT_MATCH_LEN = 6;

function diffTypeForSide(diffType, side) {
  if (diffType === "delete" && side === "baseline") return "delete";
  if (diffType === "add" && side === "target") return "add";
  if (diffType === "modify") return "modify";
  return null;
}

/** 将 OCR / 归一化 bbox 转为 PDF 用户空间（左下角原点） */
function bboxToPdfRect(bbox, pageViewport) {
  const nums = bbox.map(Number);
  if (nums.length < 4 || nums.some((n) => !Number.isFinite(n))) return null;

  let [x0, y0, x1, y1] = nums;
  const pw = pageViewport.width;
  const ph = pageViewport.height;
  const max = Math.max(Math.abs(x0), Math.abs(y0), Math.abs(x1), Math.abs(y1));
  const min = Math.min(x0, y0, x1, y1);

  const normalizePair = (a, b, size) => {
    const lo = Math.min(a, b) * size;
    const hi = Math.max(a, b) * size;
    return [lo, hi];
  };

  if (max <= 1.05 && min >= 0) {
    [x0, x1] = normalizePair(x0, x1, pw);
    const [ty0, ty1] = normalizePair(y0, y1, ph);
    return [x0, ph - ty1, x1, ph - ty0];
  }

  // PDF 用户空间（点），优先于 0–1000 归一化，避免 A4 坐标被误缩放
  const looksLikePdfPoints =
    min >= 0 &&
    max > 1.05 &&
    x1 <= pw * 1.2 &&
    y1 <= ph * 1.2 &&
    Math.max(x1, y1) > 100;
  if (looksLikePdfPoints) {
    if (y0 > y1) {
      return [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
    }
    const top = Math.min(y0, y1);
    const bottom = Math.max(y0, y1);
    return [Math.min(x0, x1), ph - bottom, Math.max(x0, x1), ph - top];
  }

  if (max <= 1000 && min >= 0) {
    const sx = pw / 1000;
    const sy = ph / 1000;
    [x0, x1] = normalizePair(x0, x1, sx);
    const [ty0, ty1] = normalizePair(y0, y1, sy);
    return [x0, ph - ty1, x1, ph - ty0];
  }

  if (y0 > y1) {
    return [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
  }
  const top = Math.min(y0, y1);
  const bottom = Math.max(y0, y1);
  return [Math.min(x0, x1), ph - bottom, Math.max(x0, x1), ph - top];
}

function isOversizedViewportBox(box, viewport) {
  if (!box || !viewport) return true;
  const vw = viewport.width || 1;
  const vh = viewport.height || 1;
  const pageArea = vw * vh;
  const area = (box.width || 0) * (box.height || 0);
  if (area < 1) return true;
  if (box.width > vw * MAX_BOX_AREA_RATIO || box.height > vh * MAX_BOX_AREA_RATIO) {
    return true;
  }
  return area > pageArea * MAX_BOX_AREA_RATIO;
}

export function bboxToViewportBox(bbox, viewport, page) {
  const base = page.getViewport({ scale: 1 });
  const pdfRect = bboxToPdfRect(bbox, base);
  if (!pdfRect) return null;
  const rect = viewport.convertToViewportRectangle(pdfRect);
  const left = Math.min(rect[0], rect[2]);
  const top = Math.min(rect[1], rect[3]);
  const width = Math.abs(rect[2] - rect[0]);
  const height = Math.abs(rect[3] - rect[1]);
  if (width < 1 || height < 1) return null;
  const box = { left, top, width, height };
  if (isOversizedViewportBox(box, viewport)) return null;
  return box;
}

function itemViewportBox(item, viewport, pdfjsLib) {
  const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
  const fontHeight = Math.hypot(tx[2], tx[3]) || 12;
  const width = Math.max((item.width || 0) * viewport.scale, fontHeight * 0.5);
  return {
    left: tx[4],
    top: tx[5] - fontHeight,
    width,
    height: fontHeight + 2,
  };
}

function diffAppliesToPage(d, side, pageNo) {
  const blocks = diffAnchorBlocks(d, side);
  if (!blocks.length) return true;
  return blocks.some((b) => (b.page || 1) === pageNo);
}

function searchLines(text) {
  return String(text || "")
    .split(/\n+/)
    .map((s) => s.trim())
    .filter((s) => s.length >= MIN_TEXT_MATCH_LEN);
}

function textMatchesItem(line, str) {
  if (!line || !str) return false;
  const a = line.trim();
  const b = str.trim();
  if (b.length < MIN_TEXT_MATCH_LEN || a.length < MIN_TEXT_MATCH_LEN) return false;
  if (a === b) return true;
  if (a.length >= b.length && a.includes(b) && b.length / a.length >= 0.35) return true;
  if (b.length >= a.length && b.includes(a) && a.length / b.length >= 0.35) return true;
  const prefixLen = Math.min(24, a.length, b.length);
  return prefixLen >= MIN_TEXT_MATCH_LEN && a.slice(0, prefixLen) === b.slice(0, prefixLen);
}

function diffTextBoxesWithinLimit(boxes, viewport) {
  const vw = viewport.width || 1;
  const vh = viewport.height || 1;
  const pageArea = vw * vh;
  const maxArea = pageArea * MAX_DIFF_TOTAL_AREA_RATIO;
  const total = boxes.reduce((sum, b) => sum + b.width * b.height, 0);
  if (total <= maxArea) return boxes;
  return [];
}

/** 无 bbox 时根据 PDF 文本层匹配差异段落 */
export async function buildTextLayerHighlightBoxes(
  page,
  viewport,
  pdfjsLib,
  { diffItems, side, pageNo, activeDiffId, onlyDiffIds = null }
) {
  if (!side || side === "none" || !Array.isArray(diffItems) || !diffItems.length) {
    return [];
  }
  const textContent = await page.getTextContent();
  const items = textContent.items || [];
  const boxes = [];
  const seen = new Set();
  const allowIds =
    onlyDiffIds instanceof Set ? onlyDiffIds : onlyDiffIds ? new Set(onlyDiffIds) : null;

  for (const d of diffItems) {
    if (allowIds && !allowIds.has(String(d.id))) continue;
    const diffType = diffTypeForSide(d.diff_type, side);
    if (!diffType) continue;
    if (!diffAppliesToPage(d, side, pageNo)) continue;

    const rawText = side === "baseline" ? d.text_left : d.text_right;
    const lines = searchLines(rawText);
    if (!lines.length) continue;

    const diffBoxes = [];
    for (const item of items) {
      const str = String(item.str || "").trim();
      if (!str) continue;
      let hit = false;
      for (const line of lines) {
        if (textMatchesItem(line, str)) {
          hit = true;
          break;
        }
      }
      if (!hit) continue;

      const box = itemViewportBox(item, viewport, pdfjsLib);
      if (isOversizedViewportBox(box, viewport)) continue;
      const key = `${d.id}-${Math.round(box.left)}-${Math.round(box.top)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      diffBoxes.push({
        key,
        ...box,
        diffType,
        active: d.id === activeDiffId,
        id: d.id,
      });
    }
    boxes.push(...diffTextBoxesWithinLimit(diffBoxes, viewport));
  }
  return boxes;
}
