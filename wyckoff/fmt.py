"""Định dạng số/ngày kiểu Việt Nam cho mọi chuỗi do code sinh (hiển thị và payload LLM)."""
from __future__ import annotations

import pandas as pd


def vn_num(x: float | None, d: int = 2) -> str:
    """22.745 -> '22,75'; 1699.62 -> '1.699,62'."""
    if x is None:
        return "n/a"
    s = f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def vn_int(x: float) -> str:
    """27360105 -> '27.360.105'."""
    return vn_num(x, 0)


def vn_ts(ts: pd.Timestamp) -> str:
    return f"{ts:%d/%m/%Y}"


def vn_g(x: float) -> str:
    """Tham số cấu hình: 0.2 -> '0,2'; 1.5 -> '1,5'; 3.0 -> '3'."""
    s = vn_num(x, 2)
    return s.rstrip("0").rstrip(",") if "," in s else s
