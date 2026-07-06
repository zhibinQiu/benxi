/** 文档对比页纯函数与常量（无 Vue 依赖） */

import { PREVIEW_KIND, resolveDocumentPreviewKind } from "./documentPreview.js";

export const MIN_COMPARE_COLS = 2;
export const MAX_CROSS_COLS = 4;
export const MAX_VERSION_COLS = 12;

export const DIFF_TYPE_LABEL = {
  add: "新增",
  delete: "删除",
  modify: "修改",
};

export const DIFF_TYPE_CLASS = {
  add: "hl-add",
  delete: "hl-delete",
  modify: "hl-modify",
};

export function docSideKey(doc) {
  if (!doc?.id) return "";
  return doc.version_id ? `${doc.id}:${doc.version_id}` : doc.id;
}

export function docDisplayTitle(doc) {
  if (!doc) return "";
  if (doc.version_no != null) return `${doc.title} · v${doc.version_no}`;
  return doc.title;
}

export function buildCompareDoc(base, version = null) {
  return {
    id: base.id,
    title: base.title,
    file_name: version?.file_name || base.file_name,
    file_size: version?.file_size || base.file_size,
    version_id: version?.id || null,
    version_no: version?.version_no ?? null,
    change_description: version?.change_description || "",
    created_at: version?.created_at || base.created_at || null,
  };
}

export function formatTimelineDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function isPdfFileName(name) {
  return resolveDocumentPreviewKind(name) === PREVIEW_KIND.PDF;
}

export function comparePreviewKind(fileName, mimeType = "") {
  return resolveDocumentPreviewKind(fileName, mimeType);
}

export function usesOriginalFilePreview(kind) {
  return (
    kind === PREVIEW_KIND.PDF ||
    kind === PREVIEW_KIND.IMAGE ||
    kind === PREVIEW_KIND.HTML
  );
}

/** 从差异列表提取当前页 PDF 高亮框（需 block diff 含 bbox） */
export function buildPdfDiffHighlights(diffItems, side, page, activeDiffId = null) {
  if (!side || side === "none" || !Array.isArray(diffItems)) return [];
  const pageNo = Number(page) > 0 ? Number(page) : 1;
  const highlights = [];
  for (const d of diffItems) {
    let diffType = null;
    if (d.diff_type === "delete" && side === "baseline") diffType = "delete";
    else if (d.diff_type === "add" && side === "target") diffType = "add";
    else if (d.diff_type === "modify") diffType = "modify";
    else continue;

    for (const block of diffAnchorBlocks(d, side)) {
      if ((block.page || 1) !== pageNo) continue;
      if (!Array.isArray(block.bbox) || block.bbox.length < 4) continue;
      highlights.push({
        id: d.id,
        bbox: block.bbox.map(Number),
        diffType,
        active: d.id === activeDiffId,
      });
    }
  }
  return highlights;
}

export function diffCaptionForSide(d, side) {
  if (!d || !side || side === "none") return "";
  if (side === "baseline") return (d.text_left || d.text_right || "").trim();
  return (d.text_right || d.text_left || "").trim();
}

export function pdfSrcWithPage(base, page) {
  if (!base) return "";
  const root = String(base).split("#")[0];
  const p = Number(page);
  return p > 1 ? `${root}#page=${p}` : root;
}

export function buildParagraphsFromContent(content) {
  if (!content) return [];
  const paras = [];
  if (Array.isArray(content.blocks) && content.blocks.length) {
    for (const b of content.blocks) {
      if (!b?.text?.trim()) continue;
      paras.push({
        page: b.page || 1,
        index: b.block_index ?? paras.length,
        block_index: b.block_index ?? paras.length,
        text: b.text,
        bbox: b.bbox || null,
        block_type: b.block_type || "text",
      });
    }
    return paras;
  }
  const pages = content.pages || [];
  for (const page of pages) {
    const pageNo = page.page || 1;
    const pageBlocks = page.blocks || [];
    if (pageBlocks.length) {
      pageBlocks.forEach((blk, i) => {
        const text = (blk.text || "").trim();
        if (!text) return;
        paras.push({
          page: pageNo,
          index: blk.block_index ?? paras.length,
          block_index: blk.block_index ?? i,
          text,
          bbox: blk.bbox || null,
          block_type: blk.block_type || "text",
        });
      });
      continue;
    }
    const text = page.text || "";
    let chunks = text.split(/\n\s*\n+/).map((p) => p.trim()).filter(Boolean);
    if (!chunks.length && text.trim()) chunks = [text.trim()];
    for (const chunk of chunks) {
      paras.push({
        page: pageNo,
        index: paras.length,
        block_index: paras.length,
        text: chunk,
        bbox: null,
        block_type: "paragraph",
      });
    }
  }
  if (!paras.length && content.full_text?.trim()) {
    const chunks = content.full_text
      .split(/\n\s*\n+/)
      .map((p) => p.trim())
      .filter(Boolean);
    for (const chunk of chunks) {
      paras.push({
        page: 1,
        index: paras.length,
        block_index: paras.length,
        text: chunk,
        bbox: null,
        block_type: "paragraph",
      });
    }
  }
  return paras;
}

export function hitPage(hit) {
  const a = hit?.anchor_json || {};
  const p = a.page ?? a.page_num;
  const n = parseInt(p, 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

export function paraMatchesHit(paraText, hit) {
  const sn = (hit?.snippet || "").trim();
  const t = (paraText || "").trim();
  if (!sn || !t) return false;
  return t === sn || t.includes(sn) || sn.includes(t);
}

export function diffAnchorBlocks(d, side) {
  const anchor = d?.anchor_json || {};
  if (anchor.kind !== "block") return [];
  if (side === "baseline") {
    return anchor.left_blocks?.length
      ? anchor.left_blocks
      : anchor.left
        ? [anchor.left]
        : [];
  }
  if (side === "target") {
    return anchor.right_blocks?.length
      ? anchor.right_blocks
      : anchor.right
        ? [anchor.right]
        : [];
  }
  return [];
}

export function diffMatchesPara(d, side, para) {
  const blocks = diffAnchorBlocks(d, side);
  if (blocks.length) {
    const idx = para.block_index ?? para.index;
    return blocks.some((b) => b.block_index === idx);
  }
  const t = (para.text || "").trim();
  if (!t) return false;
  const left = (d.text_left || "").trim();
  const right = (d.text_right || "").trim();
  if (side === "baseline") {
    if (d.diff_type === "delete" && left && (left === t || left.includes(t) || t.includes(left))) {
      return true;
    }
    if (d.diff_type === "modify" && left && (left === t || left.includes(t) || t.includes(left))) {
      return true;
    }
  }
  if (side === "target") {
    if (d.diff_type === "add" && right && (right === t || right.includes(t) || t.includes(right))) {
      return true;
    }
    if (d.diff_type === "modify" && right && (right === t || right.includes(t) || t.includes(right))) {
      return true;
    }
  }
  return false;
}
