/** Ghi chú (dữ liệu DEMO, khung tuần...) và cảnh báo tự động của engine. Ẩn khi không có gì. */
export function Banner({ notices, warnings }: { notices: string[]; warnings: string[] }) {
  if (!notices.length && !warnings.length) return null;
  return (
    <div className="flex flex-col gap-1 rounded-[10px] border border-line-strong bg-surface px-4 py-3 text-[13px] text-fg-2">
      {notices.map((t) => (
        <div key={t}>{t}</div>
      ))}
      {warnings.map((t) => (
        <div key={t} className="text-event">Cảnh báo: {t}</div>
      ))}
    </div>
  );
}
