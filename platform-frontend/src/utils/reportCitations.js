/** 从报告正文中提取实际引用的 citation 条目 */

const CITATION_REF_RE = /\[(\d{1,2})\]/g;

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

export function splitCitedCitations(content, citations = []) {
  const cited = filterCitedCitations(content, citations);
  const pool = cited.length ? cited : [...(citations || [])];
  const local = pool.filter((c) => c.document_id && c.source !== "web");
  const web = pool.filter((c) => c.source === "web" || c.url);
  return { cited: pool, local, web };
}
