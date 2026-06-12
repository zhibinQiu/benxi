/** PDF 对比页高亮：bbox 坐标换算与文本层回退匹配 */

import { diffAnchorBlocks } from "./compareDocument.js";

function diffTypeForSide(diffType, side) {
  if (diffType === "delete" && side === "baseline") return "delete";
  if (diffType === "add" && side === "target") return "add";
  if (diffType === "modify") return "modify";
  return null;
}

/** 将 OCR / 归一化 bbox 转为 PDF 用户空间（左下角原点） */
export function bboxToPdfRect(bbox, pageViewport) {
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
  return { left, top, width, height };
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
    .filter((s) => s.length >= 2);
}

function textMatchesItem(line, str) {
  if (!line || !str) return false;
  const a = line.slice(0, 48);
  const b = str.trim();
  if (b.length < 2) return false;
  return a.includes(b) || b.includes(a) || a.slice(0, 24) === b.slice(0, 24);
}

/** 无 bbox 时根据 PDF 文本层匹配差异段落 */
export async function buildTextLayerHighlightBoxes(
  page,
  viewport,
  pdfjsLib,
  { diffItems, side, pageNo, activeDiffId }
) {
  if (!side || side === "none" || !Array.isArray(diffItems) || !diffItems.length) {
    return [];
  }
  const textContent = await page.getTextContent();
  const items = textContent.items || [];
  const boxes = [];
  const seen = new Set();

  for (const d of diffItems) {
    const diffType = diffTypeForSide(d.diff_type, side);
    if (!diffType) continue;
    if (!diffAppliesToPage(d, side, pageNo)) continue;

    const rawText = side === "baseline" ? d.text_left : d.text_right;
    const lines = searchLines(rawText);
    if (!lines.length) continue;

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
      const key = `${d.id}-${Math.round(box.left)}-${Math.round(box.top)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      boxes.push({
        key,
        ...box,
        diffType,
        active: d.id === activeDiffId,
        id: d.id,
      });
    }
  }
  return boxes;
}
