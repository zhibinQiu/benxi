import { computed, nextTick } from "vue";
import { escapeHtml } from "../utils/markdown.js";
import {
  DIFF_TYPE_CLASS as diffTypeClass,
  buildPdfDiffHighlights,
  diffCaptionForSide,
  buildParagraphsFromContent,
  hitPage,
  paraMatchesHit,
  diffAnchorBlocks,
  diffMatchesPara,
} from "../utils/compareDocument.js";
import { PREVIEW_KIND } from "../utils/documentPreview.js";

/**
 * 文档对比页：差异高亮、段落匹配与搜索命中渲染。
 */
export function useCompareDiffHighlight({
  t,
  compareMode,
  job,
  versionCompareRelation,
  columns,
  activeTargetIndex,
  activePairIndex,
  activeDiffId,
  searchQuery,
  searchHits,
  activeHitIndex,
  targetColumn,
  columnScrollRefs,
  colPreviewKind,
  colUsesOriginalPreview,
}) {
  const diffItems = computed(() => {
    if (compareMode.value === "version") {
      if (versionCompareRelation.value?.status !== "done") return [];
      return versionCompareRelation.value.diff_items || [];
    }
    if (!job.value?.diff_items) return [];
    const leftId = job.value.left_document_id;
    const rightId = job.value.right_document_id;
    return job.value.diff_items.filter(
      (d) => d.doc_a_id === leftId && d.doc_b_id === rightId
    );
  });

  const searchTerms = computed(() => {
    const q = searchQuery.value.trim().toLowerCase();
    if (!q) return [];
    return q.split(/\s+/).filter((term) => term.length >= 2 && !term.includes(":") && !term.includes("："));
  });

  const activeHit = computed(() =>
    activeHitIndex.value >= 0 ? searchHits.value[activeHitIndex.value] : null
  );

  const hitNavLabel = computed(() => {
    if (!searchHits.value.length || activeHitIndex.value < 0) return "";
    return `${activeHitIndex.value + 1} / ${searchHits.value.length}`;
  });

  const canHitPrev = computed(
    () => searchHits.value.length > 0 && activeHitIndex.value > 0
  );

  const canHitNext = computed(
    () =>
      searchHits.value.length > 0 &&
      activeHitIndex.value >= 0 &&
      activeHitIndex.value < searchHits.value.length - 1
  );

  const rightParagraphs = computed(() => colParagraphs(targetColumn.value));

  function diffTypeText(type) {
    return t(`compare.diffType.${type}`) || type || t("compare.diffType.unknown");
  }

  function columnDiffSide(index) {
    if (compareMode.value === "version") {
      const pairIdx = activePairIndex.value;
      if (index === pairIdx) return "baseline";
      if (index === pairIdx + 1) return "target";
      return "none";
    }
    if (index === 0) return "baseline";
    if (index === activeTargetIndex.value) return "target";
    return "none";
  }

  function colParagraphs(col) {
    return buildParagraphsFromContent(col.content);
  }

  function colPlainPreview(col) {
    if (!col.content || colUsesOriginalPreview(col)) return "";
    if (colParagraphs(col).length) return "";
    return col.content.full_text?.trim() || "";
  }

  function colPdfHighlights(col, index) {
    return buildPdfDiffHighlights(
      diffItems.value,
      columnDiffSide(index),
      col.pdfPage || 1,
      activeDiffId.value
    );
  }

  function colPdfCaption(col, index) {
    if (!activeDiffId.value) return "";
    const side = columnDiffSide(index);
    if (side === "none") return "";
    const d = diffItems.value.find((x) => x.id === activeDiffId.value);
    if (!d) return "";
    const text = diffCaptionForSide(d, side);
    if (!text) return "";
    const label = diffTypeText(d.diff_type);
    return `${label}：${text.length > 200 ? `${text.slice(0, 200)}…` : text}`;
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function snippetHighlightParts(snippet) {
    const sn = (snippet || "").trim();
    if (!sn) return [];
    if (sn.length <= 120) return [sn];
    return [sn.slice(0, 120), sn.slice(0, 60)];
  }

  function highlightHtml(text, { diffClass, searchActive, hitSnippet, inlineDiff } = {}) {
    let html = escapeHtml(text || "");
    if (!html) return "<span class='para-empty'>（空段落）</span>";

    if (inlineDiff?.spans?.length && inlineDiff.text) {
      const raw = inlineDiff.text;
      const sideKey = inlineDiff.side === "baseline" ? "left" : "right";
      let cursor = 0;
      const parts = [];
      const ordered = [...inlineDiff.spans].sort(
        (a, b) => (a[`${sideKey}_start`] || 0) - (b[`${sideKey}_start`] || 0)
      );
      for (const span of ordered) {
        const start = span[`${sideKey}_start`] ?? 0;
        const end = span[`${sideKey}_end`] ?? start;
        if (start > cursor) {
          parts.push(escapeHtml(raw.slice(cursor, start)));
        }
        const chunk = raw.slice(start, end);
        const cls =
          span.tag === "delete"
            ? diffTypeClass.delete
            : span.tag === "insert"
              ? diffTypeClass.add
              : diffTypeClass.modify;
        parts.push(chunk ? `<span class="${cls}">${escapeHtml(chunk)}</span>` : "");
        cursor = end;
      }
      if (cursor < raw.length) parts.push(escapeHtml(raw.slice(cursor)));
      html = parts.join("") || html;
    } else if (diffClass) {
      html = `<span class="${diffClass}">${html}</span>`;
    }
    if (searchActive) {
      let marked = false;
      if (hitSnippet) {
        for (const part of snippetHighlightParts(hitSnippet)) {
          if (!part || part.length < 4) continue;
          const idx = (text || "").indexOf(part);
          if (idx >= 0) {
            const re = new RegExp(escapeRegExp(part));
            html = html.replace(re, '<mark class="hl-search hl-search--active">$&</mark>');
            marked = true;
            break;
          }
        }
      }
      if (!marked && searchTerms.value.length) {
        for (const term of searchTerms.value) {
          const re = new RegExp(`(${escapeRegExp(term)})`, "gi");
          html = html.replace(re, '<mark class="hl-search">$1</mark>');
        }
      }
    }
    return html;
  }

  function paraHitState(paraText) {
    let isHit = false;
    let isActive = false;
    searchHits.value.forEach((hit, i) => {
      if (paraMatchesHit(paraText, hit)) {
        isHit = true;
        if (i === activeHitIndex.value) isActive = true;
      }
    });
    return { isHit, isActive };
  }

  function highlightSnippet(text) {
    return highlightHtml(text || "", { searchActive: true });
  }

  function diffClassForSide(side, para) {
    if (!diffItems.value.length) return null;
    for (const d of diffItems.value) {
      if (!diffMatchesPara(d, side, para)) continue;
      if (d.diff_type === "delete" && side === "baseline") return diffTypeClass.delete;
      if (d.diff_type === "add" && side === "target") return diffTypeClass.add;
      if (d.diff_type === "modify") return diffTypeClass.modify;
    }
    return null;
  }

  function diffActiveForPara(side, para) {
    if (!activeDiffId.value) return false;
    const d = diffItems.value.find((x) => x.id === activeDiffId.value);
    return d ? diffMatchesPara(d, side, para) : false;
  }

  function inlineDiffForPara(side, para) {
    if (!activeDiffId.value) return null;
    const d = diffItems.value.find((x) => x.id === activeDiffId.value);
    if (!d || d.diff_type !== "modify" || !diffMatchesPara(d, side, para)) return null;
    const spans = d.anchor_json?.inline_spans;
    if (!spans?.length) return null;
    return { side, spans, text: side === "baseline" ? d.text_left : d.text_right };
  }

  function findParaIndexByHit(hit) {
    const paras = rightParagraphs.value;
    for (let i = 0; i < paras.length; i++) {
      if (paraMatchesHit(paras[i].text, hit)) return i;
    }
    const page = hitPage(hit);
    const byPage = paras.findIndex((p) => p.page === page);
    return byPage >= 0 ? byPage : 0;
  }

  function onDiffClick(d) {
    activeDiffId.value = d.id;
    scrollToDiffItem(d);
  }

  async function scrollToDiffItem(d) {
    await nextTick();
    for (let i = 0; i < columns.value.length; i += 1) {
      const side = columnDiffSide(i);
      if (side === "none") continue;
      const col = columns.value[i];
      const blocks = diffAnchorBlocks(d, side);
      const page = blocks[0]?.page;
      if (
        page &&
        colUsesOriginalPreview(col) &&
        colPreviewKind(col) === PREVIEW_KIND.PDF
      ) {
        col.pdfPage = Number(page) || 1;
        continue;
      }
      const blockIndex = blocks[0]?.block_index;
      if (blockIndex == null) continue;
      const root = columnScrollRefs.value[i];
      const el = root?.querySelector?.(`[data-block-index="${blockIndex}"]`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("para-flash");
        window.setTimeout(() => el.classList.remove("para-flash"), 2000);
      }
    }
  }

  return {
    diffItems,
    searchTerms,
    activeHit,
    hitNavLabel,
    canHitPrev,
    canHitNext,
    rightParagraphs,
    diffTypeText,
    columnDiffSide,
    colParagraphs,
    colPlainPreview,
    colPdfHighlights,
    colPdfCaption,
    highlightHtml,
    paraHitState,
    highlightSnippet,
    diffClassForSide,
    diffActiveForPara,
    inlineDiffForPara,
    findParaIndexByHit,
    onDiffClick,
    scrollToDiffItem,
  };
}
