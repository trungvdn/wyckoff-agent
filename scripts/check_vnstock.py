"""Chẩn đoán vnstock: cấp tài khoản và độ phủ lịch sử của từng cách gọi.

    python scripts/check_vnstock.py HPG --start 2020-01-01

Gửi toàn bộ output này khi báo lỗi dữ liệu thiếu lịch sử.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.data.fetcher import (  # noqa: E402
    _market_ohlcv,
    _quote_history,
    chunked,
    normalize_ohlcv,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("symbol", nargs="?", default="HPG")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--sources", default="VCI,KBS")
    args = p.parse_args()

    import vnstock

    print(f"vnstock {getattr(vnstock, '__version__', '?')}  | Python {sys.version.split()[0]}")
    for fn in ("status", "usage", "policy"):
        try:
            print(f"vnstock.{fn}():", getattr(vnstock, fn)())
        except Exception as exc:  # noqa: BLE001
            print(f"vnstock.{fn}(): lỗi {type(exc).__name__}: {exc}")

    print(f"\nYêu cầu {args.symbol} {args.start} -> {args.end}")
    for src in args.sources.split(","):
        for name, fetch in (
            ("Quote.history", _quote_history(src)),
            ("Market.ohlcv(limit)", _market_ohlcv(src)),
            ("Quote.history chia đoạn 365 ngày", chunked(_quote_history(src), 365)),
        ):
            try:
                df = normalize_ohlcv(fetch(args.symbol, args.start, args.end))
                info = f"{len(df):5d} phiên  {df.index[0].date()} -> {df.index[-1].date()}" if len(df) else "rỗng"
            except Exception as exc:  # noqa: BLE001
                info = f"lỗi {type(exc).__name__}: {str(exc)[:200]}"
            print(f"  [{src}] {name:34s} {info}")


if __name__ == "__main__":
    main()
