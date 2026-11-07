// Định dạng số / ngày kiểu Việt Nam (22,75; 1.699,62; 03/11/2026). Giá tính bằng nghìn đồng.
const nf = (d: number) => new Intl.NumberFormat("vi-VN", { minimumFractionDigits: d, maximumFractionDigits: d });
const P2 = nf(2);
const P1 = nf(1);
const P0 = nf(0);

type Num = number | null | undefined;

export const fmtPrice = (x: Num) => (x == null ? "—" : P2.format(x));
export const fmtRatio = (x: Num) => (x == null ? "—" : P2.format(x));
export const fmtPct = (x: Num) => (x == null ? "—" : `${x > 0 ? "+" : ""}${P1.format(x)}%`);
export const fmtPct2 = (x: Num) => (x == null ? "—" : `${x > 0 ? "+" : ""}${P2.format(x)}%`);
export const fmtInt = (x: Num) => (x == null ? "—" : P0.format(x));

export function fmtVolume(v: Num): string {
  if (v == null) return "—";
  if (v >= 1e6) return `${P1.format(v / 1e6)} tr`;
  if (v >= 1e3) return `${P1.format(v / 1e3)} N`;
  return P0.format(v);
}

/** "2026-10-02" -> "02/10/2026" */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

/** Nhãn trục: khung ngày "02/10", khung tuần "02/10/26", "full" -> dd/mm/yyyy */
export function fmtDateShort(iso: string | null | undefined, mode: "1D" | "1W" | "full" = "1D"): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (mode === "full") return `${d}/${m}/${y}`;
  return mode === "1W" ? `${d}/${m}/${y.slice(2)}` : `${d}/${m}`;
}

/** Nội dung pill trạng thái khi đã có dữ liệu. */
export const readyText = (symbol: string, asOf: string) => `${symbol} · dữ liệu đến ${fmtDate(asOf)}`;
