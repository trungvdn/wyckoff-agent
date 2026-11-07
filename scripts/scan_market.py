"""Quét thị trường cho trang Lọc cổ phiếu: cập nhật giá, phân tích mọi mã trong cache, lưu vào data/scanner.db.

Chạy sau 15:00 khi đã có nến ngày. Trang web cũng có nút "Quét lại" làm cùng việc này.

    python scripts/scan_market.py                    # mọi cổ phiếu trong cache/
    python scripts/scan_market.py --no-update        # không tải giá, quét trên dữ liệu đang có
    python scripts/scan_market.py --symbols HPG,FPT  # chỉ vài mã (lưu thành lượt quét của phiên đó)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.scanner import ScanProgress, ScanStore, run_scan  # noqa: E402
from wyckoff.web.store import Settings, load_app_config, scan_runner  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Quét thị trường cho trang Lọc cổ phiếu")
    p.add_argument("--symbols", help="danh sách mã, cách nhau dấu phẩy; mặc định mọi cổ phiếu trong cache")
    p.add_argument("--no-update", action="store_true", help="không tải giá")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = Settings(no_llm=True)
    cfg = load_app_config(settings)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
    progress = ScanProgress(running=True, started=datetime.now().isoformat(timespec="seconds"))
    universe, analyze, update = scan_runner(settings, cfg, update_prices=not args.no_update, symbols=symbols)(progress)

    def report(symbol: str) -> dict:
        row = analyze(symbol)
        print(f"[{progress.done + 1}/{progress.total}] {symbol}: {row['stage']} · {row['phase_title']}")
        return row

    rows, failed = run_scan(universe, report, update=update, progress=progress)
    as_of = ScanStore(settings.scanner_db).save_scan(rows, failed, started=progress.started or "", universe=len(universe),
                                                     finished=datetime.now().isoformat(timespec="seconds"))
    for f in failed:
        print(f"{f['symbol']}: {f['reason']}", file=sys.stderr)
    if as_of is None:
        print("Không quét được mã nào.", file=sys.stderr)
        return 1
    print(f"Đã lưu {len(rows)}/{len(universe)} mã, phiên {as_of}, vào {settings.scanner_db} ({progress.elapsed_s:.0f} giây).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
