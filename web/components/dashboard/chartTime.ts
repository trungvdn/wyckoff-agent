// Trục thời gian dùng chung cho các biểu đồ Lightweight Charts.
import { TickMarkType, type BusinessDay, type Time } from "lightweight-charts";
import { fmtDateShort } from "@/lib/format";

/** Thời gian của thư viện (chuỗi hoặc BusinessDay) -> "YYYY-MM-DD". */
export function timeToIso(t: Time): string {
  if (typeof t === "string") return t;
  if (typeof t === "number") return new Date(t * 1000).toISOString().slice(0, 10);
  const { year, month, day } = t as BusinessDay;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function tickLabel(t: Time, type: TickMarkType): string {
  const iso = timeToIso(t);
  if (type === TickMarkType.Year) return iso.slice(0, 4);
  if (type === TickMarkType.Month) return `T${Number(iso.slice(5, 7))}/${iso.slice(2, 4)}`;
  return fmtDateShort(iso);
}
