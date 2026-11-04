"""Danh sách mã cho backtest."""
from __future__ import annotations

import pandas as pd


def symbols_by_group(group: str = "VN30") -> list[str]:
    """Danh sách mã hiện tại của nhóm (vnstock 5.x: Listing().symbols_by_group)."""
    from vnstock import Listing

    raw = Listing().symbols_by_group(group=group)
    if isinstance(raw, pd.DataFrame):
        col = next((c for c in raw.columns if str(c).lower() in ("symbol", "ticker", "code")), raw.columns[0])
        raw = raw[col]
    syms = sorted({str(s).strip().upper() for s in list(raw) if str(s).strip()})
    if not syms:
        raise RuntimeError(f"vnstock trả về danh sách rỗng cho nhóm {group}")
    return syms
