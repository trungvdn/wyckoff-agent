"""Phát hiện vùng đi ngang (trading range) theo cách online, không nhìn trước.

Duyệt từng phiên t:
- Chưa có range: xét các swing đã xác nhận đến t (confirmed_idx <= t). Tìm điểm bắt đầu
  sớm nhất s (là một swing) sao cho trên [s, t]:
    * >= min_swing_highs swing high và >= min_swing_lows swing low
    * resistance = max(swing high), support = min(swing low), height <= max_height_atr * ATR_t
    * t - s >= min_bars
    * mọi close nằm trong [support - tol*ATR, resistance + tol*ATR]
    * |độ dốc hồi quy close| / ATR_t <= max_slope_atr
  -> range được xác nhận tại t, biên cố định từ đây. Bối cảnh (sau nhịp giảm / sau nhịp tăng /
  trung tính / chưa rõ) tính từ lợi suất `context_lookback` phiên trước s.
- Đang có range: nếu close vượt resistance + exit_atr*ATR (hoặc dưới support - exit_atr*ATR)
  exit_bars phiên liên tiếp thì range kết thúc tại phiên trước chuỗi đó, xác nhận tại t.
- Neo SC–AR (`anchors`): tại phiên AR xác nhận, nếu chưa có range và chiều cao <= max_height_atr * ATR_t thì mở range
  theo đáy SC và đỉnh AR, ưu tiên trước cách dựng từ swing.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from wyckoff.config import RangeConfig
from wyckoff.detectors.models import CTX_AFTER_DECLINE, CTX_AFTER_RISE, CTX_NEUTRAL, CTX_UNKNOWN, Swing, TradingRange


@dataclass(frozen=True)
class RangeAnchor:
    """Biên range lấy từ SC và AR; chỉ được biết tại `confirmed_idx` (phiên AR xác nhận)."""
    start_idx: int
    confirmed_idx: int
    support: float
    resistance: float


def _slope(values: np.ndarray) -> float:
    x = np.arange(len(values), dtype=float)
    return float(np.polyfit(x, values, 1)[0])


def _try_form_range(
    t: int, swings: list[Swing], close: np.ndarray, atr_t: float, cfg: RangeConfig
) -> tuple[int, float, float] | None:
    for j in range(len(swings)):
        window = swings[j:]
        s_idx = window[0].idx
        if t - s_idx < cfg.min_bars:
            return None  # các điểm bắt đầu sau còn ngắn hơn
        highs = [s.price for s in window if s.kind == "high"]
        lows = [s.price for s in window if s.kind == "low"]
        if len(highs) < cfg.min_swing_highs or len(lows) < cfg.min_swing_lows:
            continue
        resistance, support = max(highs), min(lows)
        if resistance - support > cfg.max_height_atr * atr_t:
            continue
        seg = close[s_idx:t + 1]
        tol = cfg.close_tolerance_atr * atr_t
        if seg.max() > resistance + tol or seg.min() < support - tol:
            continue
        if abs(_slope(seg)) / atr_t > cfg.max_slope_atr:
            continue
        return s_idx, support, resistance
    return None


def classify_context(close: np.ndarray, start_idx: int, cfg: RangeConfig) -> tuple[str, float | None]:
    """Bối cảnh range theo lợi suất `context_lookback` phiên trước phiên bắt đầu (chỉ dùng dữ liệu quá khứ)."""
    if start_idx < cfg.context_lookback:
        return CTX_UNKNOWN, None
    ret = float(close[start_idx] / close[start_idx - cfg.context_lookback] - 1)
    if ret <= cfg.after_decline_max_return:
        return CTX_AFTER_DECLINE, ret
    if ret >= cfg.after_rise_min_return:
        return CTX_AFTER_RISE, ret
    return CTX_NEUTRAL, ret


def detect_trading_ranges(
    df: pd.DataFrame, swings: list[Swing], cfg: RangeConfig | None = None, anchors: list[RangeAnchor] | None = None
) -> list[TradingRange]:
    """`df` phải có cột `atr` (từ add_indicators)."""
    cfg = cfg or RangeConfig()
    close = df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    dates = df.index
    n = len(df)
    swings = sorted(swings, key=lambda s: s.idx)
    anchor_at = {a.confirmed_idx: a for a in anchors or []}

    ranges: list[TradingRange] = []
    active: TradingRange | None = None
    outside_dir: str | None = None
    outside_count = 0
    last_end_idx = -1

    for t in range(n):
        if np.isnan(atr[t]):
            continue
        if active is None:
            anchor = anchor_at.get(t)
            if anchor is not None and 0 < anchor.resistance - anchor.support <= cfg.max_height_atr * atr[t]:
                context, prior_return = classify_context(close, anchor.start_idx, cfg)
                active = TradingRange(
                    range_id=len(ranges), start_idx=anchor.start_idx, start_date=dates[anchor.start_idx],
                    end_idx=t, end_date=dates[t], confirmed_idx=t, confirmed_date=dates[t],
                    support=anchor.support, resistance=anchor.resistance, atr_at_confirm=float(atr[t]),
                    context=context, prior_return=prior_return, anchored=True,  # type: ignore[arg-type]
                )
                outside_dir, outside_count = None, 0
                continue
            avail = [
                s for s in swings
                if s.confirmed_idx <= t and s.idx > last_end_idx and s.idx >= t - cfg.max_lookback
            ]
            found = _try_form_range(t, avail, close, atr[t], cfg)
            if found:
                s_idx, support, resistance = found
                context, prior_return = classify_context(close, s_idx, cfg)
                active = TradingRange(
                    range_id=len(ranges), start_idx=s_idx, start_date=dates[s_idx],
                    end_idx=t, end_date=dates[t], confirmed_idx=t, confirmed_date=dates[t],
                    support=support, resistance=resistance, atr_at_confirm=float(atr[t]),
                    context=context, prior_return=prior_return,  # type: ignore[arg-type]
                )
                outside_dir, outside_count = None, 0
            continue

        thr = cfg.exit_atr * atr[t]
        direction = "up" if close[t] > active.resistance + thr else "down" if close[t] < active.support - thr else None
        if direction is None:
            outside_dir, outside_count = None, 0
            active = replace(active, end_idx=t, end_date=dates[t])
            continue
        outside_count = outside_count + 1 if direction == outside_dir else 1
        outside_dir = direction
        if outside_count >= cfg.exit_bars:
            ended = replace(
                active, end_confirmed_idx=t, end_confirmed_date=dates[t], exit_direction=direction  # type: ignore[arg-type]
            )
            ranges.append(ended)
            last_end_idx = ended.end_idx
            active, outside_dir, outside_count = None, None, 0

    if active is not None:
        ranges.append(replace(active, end_idx=n - 1, end_date=dates[n - 1]))
    return ranges
