"""Mục tiêu giá theo Nhân–Quả (Cause & Effect): đếm ngang trên biểu đồ Point & Figure.

Dựng P&F từ giá đóng cửa (ô `box`, đảo chiều `reversal` ô). Số cột trong vùng tích lũy
(từ đầu range đến LPS, chưa có LPS thì đến trước SOS, chưa có SOS thì đến phiên cuối – tạm tính)
nhân với `box x reversal` là bề rộng "nguyên nhân"; cộng vào:
  - đáy thấp nhất của cấu trúc (min support / đáy SC / đáy Spring) -> mục tiêu thận trọng
  - đường đếm (đáy LPS, chưa có LPS thì support)                    -> mục tiêu tích cực
Chỉ là ước lượng, không phải dự báo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from wyckoff.config import PnfConfig
from wyckoff.indicators.ticks import tick_size
from wyckoff.phases import Structure


@dataclass(frozen=True)
class PnfColumn:
    direction: int          # +1 cột X (tăng), -1 cột O (giảm)
    low_box: int            # chỉ số ô thấp nhất (giá = ô x box)
    high_box: int
    start_idx: int          # vị trí trong chuỗi đầu vào
    end_idx: int


def pnf_columns(closes: Sequence[float], box: float, reversal: int = 3) -> list[PnfColumn]:
    """Các cột P&F dựng từ chuỗi close. Cột đầu tiên mở khi giá đi được >= 1 ô."""
    if box <= 0:
        raise ValueError("box phải > 0")
    if reversal < 1:
        raise ValueError("reversal phải >= 1")
    cols: list[PnfColumn] = []
    if len(closes) == 0:
        return cols
    k = lambda p: math.floor(p / box + 1e-9)  # noqa: E731
    ref = k(closes[0])
    direction, lo, hi, start, end = 0, ref, ref, 0, 0
    for i, c in enumerate(closes[1:], start=1):
        b = k(c)
        if direction == 0:
            if b > ref:
                direction, lo, hi, end = 1, ref, b, i
            elif b < ref:
                direction, lo, hi, end = -1, b, ref, i
        elif direction == 1:
            if b > hi:
                hi, end = b, i
            elif b <= hi - reversal:
                cols.append(PnfColumn(1, lo, hi, start, end))
                direction, hi, lo, start, end = -1, hi - 1, b, i, i
        else:
            if b < lo:
                lo, end = b, i
            elif b >= lo + reversal:
                cols.append(PnfColumn(-1, lo, hi, start, end))
                direction, lo, hi, start, end = 1, lo + 1, b, i, i
    if direction != 0:
        cols.append(PnfColumn(direction, lo, hi, start, end))
    return cols


def box_size(atr: float, ref_price: float, cfg: PnfConfig, exchange: str = "HOSE") -> float:
    """Ô = `box_atr` x ATR lúc range xác nhận, làm tròn lên theo bước giá (tối thiểu 1 tick)."""
    tick = tick_size(ref_price, exchange)
    return round(max(tick, math.ceil(cfg.box_atr * atr / tick - 1e-9) * tick), 4)


def cause_effect_target(df: pd.DataFrame, s: Structure, cfg: PnfConfig | None = None,
                        exchange: str = "HOSE") -> dict[str, Any] | None:
    """Mục tiêu theo đếm ngang cho cấu trúc `s` (cần range, pha thuộc `cfg.phases`)."""
    cfg = cfg or PnfConfig()
    rng = s.rng
    if rng is None or s.phase not in cfg.phases:
        return None
    last = len(df) - 1
    if s.lps is not None:
        end, provisional = s.lps.idx, False
    elif s.sos is not None:
        end, provisional = s.sos.idx - 1, False
    else:
        end, provisional = last, True
    start = rng.start_idx
    if end <= start:
        return None
    box = box_size(rng.atr_at_confirm, rng.support, cfg, exchange)
    cols = pnf_columns(df["close"].iloc[start:end + 1].tolist(), box, cfg.reversal)
    if not cols:
        return None
    width = len(cols) * box * cfg.reversal
    lows = [rng.support] + [e.low for e in (s.sc,) if e is not None]
    if s.spring is not None:
        lows.append(float(s.spring.details.get("lowest_low", s.spring.low)))
    if s.sos is not None and s.sos.details.get("reclaim"):     # đáy của nhịp thoát xuống thuộc cấu trúc
        lows.append(float(df["low"].iloc[start:s.sos.idx + 1].min()))
    base_low = min(lows)
    count_line = s.lps.low if s.lps is not None else rng.support
    return {
        "columns": len(cols), "box": box, "reversal": cfg.reversal,
        "count_from": f"{df.index[start]:%Y-%m-%d}", "count_to": f"{df.index[end]:%Y-%m-%d}",
        "count_to_event": "LPS" if s.lps is not None else "SOS" if s.sos is not None else None,
        "base_low": round(base_low, 2), "count_line": round(count_line, 2),
        "conservative": round(base_low + width, 2), "aggressive": round(count_line + width, 2),
        "provisional": provisional,
    }
