"""Đo lợi suất sau tín hiệu. Quy ước chống look-ahead: tín hiệu biết tại close phiên t,
vào lệnh ở OPEN phiên t+1, đo đến CLOSE phiên t+H (H phiên nắm giữ, gồm phiên vào).
Lợi suất đã trừ chi phí khứ hồi; lợi suất vượt = lợi suất cổ phiếu - lợi suất chỉ số cùng kỳ.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _arr(s: pd.Series) -> np.ndarray:
    return s.to_numpy(dtype=float)


def rolling_beta(stock: pd.DataFrame, index_aligned: pd.DataFrame, window: int = 250, min_periods: int = 120) -> pd.Series:
    """Beta của cổ phiếu với chỉ số tại mỗi phiên t, từ lợi suất ngày trong `window` phiên đến t (không nhìn trước)."""
    rs = stock["close"].pct_change()
    ri = index_aligned["close"].pct_change()
    cov = rs.rolling(window, min_periods=min_periods).cov(ri)
    var = ri.rolling(window, min_periods=min_periods).var()
    return (cov / var).rename("beta")


def forward_metrics(
    df: pd.DataFrame, index_aligned: pd.DataFrame | None, signal_idx: int, horizons: tuple[int, ...],
    cost_pct: float = 0.3, price_limit: float = 0.07, limit_tolerance: float = 0.005, beta: float | None = None,
) -> dict[str, Any]:
    """Chỉ số đo cho một tín hiệu tại phiên `signal_idx` (vào lệnh ở open phiên sau).
    `beta` (point-in-time) -> thêm bexcess_H = lợi suất − beta × lợi suất chỉ số cùng kỳ."""
    o, h, l, c = (_arr(df[k]) for k in ("open", "high", "low", "close"))
    last = len(df) - 1
    entry = signal_idx + 1
    out: dict[str, Any] = {"entry_idx": entry if entry <= last else None}
    if entry > last:
        out["entry_date"] = None
        out["entry_price"] = None
        out["untradable"] = None
        for H in horizons:
            out.update({f"ret_{H}": np.nan, f"excess_{H}": np.nan, f"bexcess_{H}": np.nan, f"mfe_{H}": np.nan, f"mae_{H}": np.nan})
        return out
    out["entry_date"] = df.index[entry]
    out["entry_price"] = o[entry]
    out["untradable"] = bool(o[entry] >= c[entry - 1] * (1 + price_limit - limit_tolerance))   # mở cửa giá trần
    io = ic = None
    if index_aligned is not None:
        io, ic = _arr(index_aligned["open"]), _arr(index_aligned["close"])
    for H in horizons:
        end = entry + H - 1
        if end > last:
            out.update({f"ret_{H}": np.nan, f"excess_{H}": np.nan, f"bexcess_{H}": np.nan, f"mfe_{H}": np.nan, f"mae_{H}": np.nan})
            continue
        ret = (c[end] / o[entry] - 1) * 100 - cost_pct
        out[f"ret_{H}"] = ret
        if io is not None:
            base = io[entry] if not np.isnan(io[entry]) else ic[entry - 1]
            idx_ret = (ic[end] / base - 1) * 100
            out[f"excess_{H}"] = ret - idx_ret
            out[f"bexcess_{H}"] = ret - beta * idx_ret if beta is not None and not np.isnan(beta) else np.nan
        else:
            out[f"excess_{H}"] = np.nan
            out[f"bexcess_{H}"] = np.nan
        out[f"mfe_{H}"] = (h[entry:end + 1].max() / o[entry] - 1) * 100
        out[f"mae_{H}"] = (l[entry:end + 1].min() / o[entry] - 1) * 100
    return out


def baseline_returns(
    df: pd.DataFrame, index_aligned: pd.DataFrame | None, horizons: tuple[int, ...], cost_pct: float = 0.3,
    first_signal_idx: int = 0, beta: pd.Series | None = None,
) -> pd.DataFrame:
    """Lợi suất nếu 'tín hiệu' ở MỌI phiên t >= first_signal_idx (nền để so sánh). Vector hoá."""
    o, c = _arr(df["open"]), _arr(df["close"])
    n = len(df)
    out = pd.DataFrame(index=df.index)
    entry_open = np.r_[o[1:], np.nan]                        # open phiên t+1
    if index_aligned is not None:
        io, ic = _arr(index_aligned["open"]), _arr(index_aligned["close"])
        i_base = np.where(np.isnan(np.r_[io[1:], np.nan]), ic, np.r_[io[1:], np.nan])
    for H in horizons:
        end_close = np.r_[c[H:], np.full(H, np.nan)]          # close phiên t+H
        ret = (end_close / entry_open - 1) * 100 - cost_pct
        out[f"ret_{H}"] = ret
        if index_aligned is not None:
            i_end = np.r_[ic[H:], np.full(H, np.nan)]
            idx_ret = (i_end / i_base - 1) * 100
            out[f"excess_{H}"] = ret - idx_ret
            out[f"bexcess_{H}"] = ret - beta.to_numpy(dtype=float) * idx_ret if beta is not None else np.nan
        else:
            out[f"excess_{H}"] = np.nan
            out[f"bexcess_{H}"] = np.nan
    mask = np.arange(n) >= first_signal_idx
    return out[mask]


def bootstrap_mean_ci(values: np.ndarray, n: int = 2000, ci: float = 0.90, seed: int = 7) -> tuple[float, float]:
    """Khoảng tin cậy bootstrap của giá trị trung bình (bỏ NaN). < 2 mẫu -> (nan, nan)."""
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    a = (1 - ci) / 2
    return (float(np.quantile(means, a)), float(np.quantile(means, 1 - a)))


def scenario_race(close: np.ndarray, start_idx: int, up: float | None, down: float | None, max_bars: int) -> tuple[str, int | None]:
    """Từ phiên start_idx+1: close vượt `up` trước -> 'xác nhận'; close dưới `down` trước -> 'vô hiệu';
    hết `max_bars` phiên hoặc hết dữ liệu -> 'chưa rõ'. Thiếu mức -> 'không áp dụng'."""
    if up is None and down is None:
        return "không áp dụng", None
    last = len(close) - 1
    for k in range(start_idx + 1, min(start_idx + max_bars, last) + 1):
        if up is not None and close[k] > up:
            return "xác nhận", k - start_idx
        if down is not None and close[k] < down:
            return "vô hiệu", k - start_idx
    return "chưa rõ", None
