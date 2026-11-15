export const isNum = (x) => typeof x === "number" && Number.isFinite(x);

export function fmtP(p) {
  if (!isNum(p)) return "n/a";
  return p < 0.001 ? "< 0.001" : p.toFixed(3);
}
export function pct(x, d = 1) {
  return isNum(x) ? `${(x * 100).toFixed(d)}%` : "n/a";
}
export function pts(x, d = 2) {
  return isNum(x) ? `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)} pts` : "n/a";
}
export function num(x, d) {
  if (!isNum(x)) return "n/a";
  const a = Math.abs(x);
  const dp = d ?? (a >= 1000 ? 0 : a >= 100 ? 1 : a >= 1 ? 2 : 3);
  return x.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
}
export function signed(x, d) {
  return isNum(x) ? `${x >= 0 ? "+" : "−"}${num(Math.abs(x), d)}` : "n/a";
}
export function compact(x) {
  return isNum(x) ? Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(x) : "n/a";
}
