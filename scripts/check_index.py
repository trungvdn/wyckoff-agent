"""Dò mã chỉ số mà vnstock chấp nhận (vd. VNSmallCap có thể là VNSML, VNSMALLCAP...).

    python scripts/check_index.py                 # thử các mã VNSmallCap / VNMidCap thường gặp
    python scripts/check_index.py VNSML VNSI      # thử mã tự chọn

In số phiên, ngày đầu / cuối cho từng mã × nguồn. Dùng mã có lịch sử dài nhất cho `market.context_benchmark`.
"""
from __future__ import annotations

import sys

CANDIDATES = ["VNSML", "VNSMALLCAP", "VNSMALL", "VNSC", "VNSI", "VNSMCAP", "VNMID", "VNMIDCAP", "VNALL", "VN100"]


def try_market(sym: str) -> str:
    from vnstock import Market

    df = Market().index(sym).ohlcv(start="2017-01-01", end="2026-11-03", source="kbs")
    return f"{len(df)} phiên, {df.iloc[0, 0]} → {df.iloc[-1, 0]}" if df is not None and len(df) else "rỗng"


def try_quote(sym: str, source: str) -> str:
    from vnstock import Quote

    df = Quote(symbol=sym, source=source).history(start="2017-01-01", end="2026-11-03", interval="1D")
    return f"{len(df)} phiên, {df.iloc[0, 0]} → {df.iloc[-1, 0]}" if df is not None and len(df) else "rỗng"


def main() -> None:
    syms = [s.upper() for s in sys.argv[1:]] or CANDIDATES
    try:
        from vnstock import Listing

        lst = Listing()
        for fn in ("all_indices", "indices", "all_index"):
            if hasattr(lst, fn):
                print(f"Listing().{fn}():")
                print(getattr(lst, fn)())
                break
    except Exception as exc:  # noqa: BLE001
        print("Không liệt kê được chỉ số:", str(exc)[:200])
    for s in syms:
        for name, fn in (("Market.index[kbs]", lambda: try_market(s)), ("Quote[VCI]", lambda: try_quote(s, "VCI")),
                         ("Quote[KBS]", lambda: try_quote(s, "KBS"))):
            try:
                res = fn()
            except Exception as exc:  # noqa: BLE001
                res = "lỗi: " + str(exc).splitlines()[0][:100]
            print(f"{s:12s} {name:18s} {res}")


if __name__ == "__main__":
    main()
