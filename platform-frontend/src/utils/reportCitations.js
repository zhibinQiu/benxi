/** 从报告正文中提取实际引用的 citation 条目 */

const CITATION_REF_RE = /[\[【](\d{1,2})[\]】]/g;
const CITATION_REF_REPLACE_RE = /(\[|【)(\d{1,2})(\]|】)/g;

export function extractCitationIndexes(content) {
  const indexes = new Set();
  const text = String(content || "");
  for (const match of text.matchAll(CITATION_REF_RE)) {
    const num = Number(match[1]);
    if (num > 0) indexes.add(num);
  }
  return indexes;
}

export function filterCitedCitations(content, citations = []) {
  const indexes = extractCitationIndexes(content);
  if (!indexes.size) return [];
  return (citations || [])
    .filter((c) => indexes.has(Number(c.index)))
    .sort((a, b) => Number(a.index) - Number(b.index));
}

/** 将正文与引用编号重排为连续的 1,2,3… */
export function alignCitationsWithContent(content, citations = []) {
  const pool = filterCitedCitations(content, citations);
  if (!pool.length) {
    return { content: String(content || ""), citations: [] };
  }
  const oldIndexes = pool.map((c) => Number(c.index)).filter(Boolean);
  const remap = new Map(oldIndexes.map((old, i) => [old, i + 1]));
  let alignedContent = String(content || "");
  const needsRenumber = oldIndexes.some((old) => remap.get(old) !== old);
  if (needsRenumber) {
    alignedContent = alignedContent.replace(
      CITATION_REF_REPLACE_RE,
      (match, open, num, close) => {
        const mapped = remap.get(Number(num));
        return mapped != null ? `${open}${mapped}${close}` : match;
      }
    );
  }
  const alignedCitations = pool.map((c, i) => ({ ...c, index: i + 1 }));
  return { content: alignedContent, citations: alignedCitations };
}

export function splitCitedCitations(content, citations = []) {
  const { content: alignedContent, citations: cited } = alignCitationsWithContent(
    content,
    citations
  );
  const local = cited.filter((c) => c.document_id && c.source !== "web");
  const web = cited.filter((c) => c.source === "web" || c.url);
  return { cited, local, web, content: alignedContent };
}
