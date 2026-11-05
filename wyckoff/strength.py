"""Sức mạnh cung cầu trong Markup / Markdown tại phiên cuối của `df`. Chỉ mô tả, chưa kiểm định bằng backtest.

Bên chủ đạo: Markup = cầu, Markdown = cung. Ba tín hiệu, mỗi tín hiệu -1 / 0 / +1:
    volume      tỷ trọng khối lượng ở phiên cùng chiều xu hướng trong `window` phiên
    swing       hai đỉnh và hai đáy đã xác nhận gần nhất có đi đúng chiều xu hướng không
    correction  nhịp điều chỉnh (Markup) / nhịp hồi (Markdown) tính từ cực trị của nhịp xu hướng:
                nông và volume thấp +1; sâu, volume cao hoặc close sai phía SMA -1; chưa có nhịp 0
Tổng >= strong_score: mạnh; <= weak_score: yếu đi; còn lại: trung bình.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from wyckoff.config import StrengthConfig
from wyckoff.detectors.models import Swing
from wyckoff.fmt import vn_num, vn_ts

MODERATE, STRONG, WEAK = "trung bình", "mạnh", "yếu đi"


@dataclass(frozen=True)
class Signal:
    key: str
    title: str
    text: str
    points: int


@dataclass(frozen=True)
class Correction:
    active: bool
    quality: str | None             # "light" | "normal" | "heavy"; None khi chưa có nhịp
    verdict: str
    bars: int
    extreme_price: float
    extreme_date: str               # YYYY-MM-DD
    depth_atr: float
    retrace_pct: float | None
    vol_ratio: float | None


@dataclass(frozen=True)
class TrendStrength:
    side: Literal["demand", "supply"]
    level: str
    score: int
    headline: str
    up_volume_pct: float | None     # tỷ trọng khối lượng phiên tăng; phần còn lại là phiên giảm
    window: int
    signals: tuple[Signal, ...]
    correction: Correction

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _volume_signal(close: np.ndarray, volume: np.ndarray, s: int, cfg: StrengthConfig) -> tuple[Signal, float | None]:
    w = cfg.window
    chg = np.diff(close[-(w + 1):])
    vol = volume[-len(chg):] if len(chg) else volume[:0]
    up, down = float(vol[chg > 0].sum()), float(vol[chg < 0].sum())
    title = "Khối lượng"
    if up + down <= 0:
        return Signal("volume", title, f"Chưa đủ dữ liệu khối lượng {w} phiên.", 0), None
    up_pct = up / (up + down) * 100
    with_trend = up_pct if s > 0 else 100 - up_pct
    pts = 1 if with_trend >= cfg.volume_strong_pct else -1 if with_trend <= cfg.volume_weak_pct else 0
    side, word = ("cầu", "tăng") if s > 0 else ("cung", "giảm")
    tail = {1: f"{side} chiếm ưu thế", 0: "hai bên khá cân bằng", -1: f"{side} không chiếm ưu thế"}[pts]
    return Signal("volume", title, f"Phiên {word} chiếm {vn_num(with_trend, 0)}% khối lượng {w} phiên: {tail}.", pts), up_pct


def _swing_signal(swings: list[Swing], t: int, s: int, cfg: StrengthConfig) -> Signal:
    title = "Đỉnh đáy"
    known = [x for x in swings if x.confirmed_idx <= t and x.idx >= t - cfg.swing_lookback]
    highs = [x.price for x in known if x.kind == "high"][-2:]
    lows = [x.price for x in known if x.kind == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return Signal("swing", title, f"Chưa đủ đỉnh đáy xác nhận trong {cfg.swing_lookback} phiên.", 0)
    hi_ok = s * (highs[1] - highs[0]) > 0
    lo_ok = s * (lows[1] - lows[0]) > 0
    pair = f"đỉnh {vn_num(highs[0])} -> {vn_num(highs[1])}, đáy {vn_num(lows[0])} -> {vn_num(lows[1])}"
    word = "cao dần" if s > 0 else "thấp dần"
    if hi_ok and lo_ok:
        return Signal("swing", title, f"Đỉnh và đáy cùng {word} ({pair}).", 1)
    if not hi_ok and not lo_ok:
        return Signal("swing", title, f"Đỉnh và đáy đều đi ngược xu hướng ({pair}).", -1)
    return Signal("swing", title, f"Đỉnh và đáy chưa đồng thuận ({pair}).", 0)


def _correction(df: pd.DataFrame, start: int, s: int, sma_period: int, cfg: StrengthConfig) -> tuple[Signal, Correction]:
    close = df["close"].to_numpy(dtype=float)
    t = len(close) - 1
    leg = close[start:t + 1]
    ext = start + int(np.argmax(s * leg))
    base = close[start + int(np.argmin(s * close[start:ext + 1]))]
    atr = float(df["atr"].iloc[t])
    depth = float(s * (close[ext] - close[t]))
    depth_atr = depth / atr if atr > 0 else 0.0
    move = abs(close[ext] - base)
    retrace = depth / move * 100 if move > 0 else None
    bars = t - ext
    vr = df["vol_ratio"].to_numpy(dtype=float)[ext + 1:t + 1]
    vol = float(np.nanmean(vr)) if bars > 0 and not np.isnan(vr).all() else None
    sma = float(df["sma"].iloc[t])
    wrong_side = not np.isnan(sma) and s * (close[t] - sma) < 0

    title, ext_word = ("Điều chỉnh", "đỉnh") if s > 0 else ("Nhịp hồi", "đáy")
    ext_date = df.index[ext]
    active = bars >= cfg.min_correction_bars and depth_atr >= cfg.min_correction_atr
    if not active:
        verdict = f"Chưa có nhịp {title.lower()} đáng kể; {ext_word} gần nhất {vn_num(close[ext])} ({vn_ts(ext_date)})."
        corr = Correction(False, None, verdict, bars, float(close[ext]), f"{ext_date:%Y-%m-%d}", round(depth_atr, 2),
                          None if retrace is None else round(retrace, 1), None if vol is None else round(vol, 2))
        return Signal("correction", title, verdict, 0), corr

    heavy = wrong_side or (retrace is not None and retrace >= cfg.deep_retrace_pct) or (vol is not None and vol >= cfg.high_vol_ratio)
    light = not heavy and retrace is not None and retrace < cfg.shallow_retrace_pct and vol is not None and vol < cfg.low_vol_ratio
    quality = "heavy" if heavy else "light" if light else "normal"
    pts = {"heavy": -1, "light": 1, "normal": 0}[quality]
    if s > 0:
        tail = {"light": "nhịp nông, volume thấp, cung chưa mạnh lên", "normal": "nhịp điều chỉnh bình thường",
                "heavy": "nhịp sâu hoặc volume cao, cung đang mạnh lên"}[quality]
    else:
        tail = {"light": "nhịp hồi yếu, volume thấp, cầu chưa quay lại", "normal": "nhịp hồi bình thường",
                "heavy": "nhịp hồi mạnh hoặc volume cao, cầu đang quay lại"}[quality]
    parts = [f"{bars} phiên từ {ext_word} {vn_num(close[ext])} ({vn_ts(ext_date)})", f"{vn_num(depth_atr, 1)} ATR"]
    if retrace is not None:
        parts.append(f"bằng {vn_num(retrace, 0)}% nhịp {'tăng' if s > 0 else 'giảm'} trước đó")
    if vol is not None:
        parts.append(f"volume {vn_num(vol)}x TB20")
    side_note = f", close {'dưới' if s > 0 else 'trên'} SMA{sma_period}" if wrong_side else ""
    verdict = f"{title} {', '.join(parts)}{side_note}: {tail}."
    corr = Correction(True, quality, verdict, bars, float(close[ext]), f"{ext_date:%Y-%m-%d}", round(depth_atr, 2),
                      None if retrace is None else round(retrace, 1), None if vol is None else round(vol, 2))
    return Signal("correction", title, verdict, pts), corr


def trend_strength(df: pd.DataFrame, swings: list[Swing], start_idx: int, direction: Literal["up", "down"],
                   cfg: StrengthConfig | None = None, sma_period: int = 50) -> TrendStrength:
    """`start_idx`: phiên bắt đầu nhịp xu hướng trong `df`. `df` cần close, volume, atr, vol_ratio, sma."""
    cfg = cfg or StrengthConfig()
    s = 1 if direction == "up" else -1
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    vol_sig, up_pct = _volume_signal(close, volume, s, cfg)
    swing_sig = _swing_signal(swings, len(df) - 1, s, cfg)
    corr_sig, corr = _correction(df, max(start_idx, 0), s, sma_period, cfg)
    score = vol_sig.points + swing_sig.points + corr_sig.points
    level = STRONG if score >= cfg.strong_score else WEAK if score <= cfg.weak_score else MODERATE
    side_vn = "Cầu" if s > 0 else "Cung"
    headline = {STRONG: f"{side_vn} đang mạnh", WEAK: f"{side_vn} đang yếu đi", MODERATE: f"{side_vn} ở mức trung bình"}[level]
    return TrendStrength("demand" if s > 0 else "supply", level, score, headline,
                         None if up_pct is None else round(up_pct, 1), cfg.window, (vol_sig, swing_sig, corr_sig), corr)
