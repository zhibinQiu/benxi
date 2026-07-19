/** A 股代码展示：000682.sz / 600519.sh */

export function formatStockCode(code, { lower = true } = {}) {
  const raw = String(code || "").trim();
  if (!raw) return "—";
  if (raw.includes(".")) {
    const [num, suf] = raw.split(".");
    const suffix = lower ? String(suf || "").toLowerCase() : String(suf || "").toUpperCase();
    return `${num}.${suffix}`;
  }
  const c = raw.toUpperCase();
  let suf = "SZ";
  if (/^(5|6|9)/.test(c)) suf = "SH";
  else if (/^(4|8)/.test(c)) suf = "BJ";
  return `${c}.${lower ? suf.toLowerCase() : suf}`;
}

export function pureStockCode(code) {
  return String(code || "").trim().split(".")[0] || "";
}
