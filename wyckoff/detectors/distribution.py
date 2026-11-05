"""Sự kiện phía phân phối: BC, BC failed, AR(d), ST(d), SOW, LPSY. Chỉ ghi nhận trong `result.distribution`:
không vào `result.events`, nên không đổi pha / tin cậy / backtest / payload.

Đối xứng với SC, SC failed, AR, ST, SOS, LPS (đổi vai high <-> low; tests/test_distribution.py kiểm tra bằng cách lật giá).
Mọi điều kiện tại phiên t chỉ dùng dữ liệu <= t; sự kiện cần phiên sau mang `confirmed_idx` = phiên xác nhận.

BC không đối xứng hoàn toàn với SC, do đặc thù giá VN:
- `bc_min_rise`: tăng theo % dễ đạt hơn giảm, và cổ phiếu tăng giá thường xuyên có phiên volume lớn sát đỉnh 60 phiên.
- `bc_exclude_ceiling_locked`: phiên khóa trần (close = trần) chưa cho thấy cung hấp thụ cầu nên không phải climax;
  dạng chuỗi tăng trần xác nhận ở phiên đảo chiều đầu tiên có close_pos thấp.
UT / UTAD đã có ở `detect_utad`, không lặp lại ở đây.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import DistributionConfig
from wyckoff.detectors.events import _make_event, _rounded
from wyckoff.detectors.models import Event, EventType, TradingRange

_EPS = 1e-9


def _ymd(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- BC

def detect_buying_climax(df: pd.DataFrame, cfg: DistributionConfig | None = None, decimals: int = 2,
                         price_limit: float = 0.07, limit_tolerance: float = 0.005) -> list[Event]:
    """BC và BC failed.

    Điều kiện nền: tăng >= bc_min_rise từ close thấp nhất `bc_trend_lookback` phiên, close > SMA, high cao nhất
    `bc_highest_high_lookback` phiên, volume > bc_min_vol_ratio x TB20.
    Dạng climax (không khóa trần): True Range > bc_min_spread_atr x ATR. Xác nhận ngay nếu close_pos <= bc_max_close_pos;
      hoặc trong `bc_zone_bars` phiên sau có close < điểm giữa nến mà không vượt đỉnh nến (xác nhận tại phiên đó).
    Dạng chuỗi tăng trần: >= ceiling_chain_min_days phiên tăng trần trong `ceiling_chain_window` phiên trước,
      phiên hiện tại close_pos <= bc_max_close_pos. Không xét biên độ.
    BC mới trong `bc_cooldown_bars` phiên chỉ giữ nếu đỉnh cao hơn (theo thứ tự xác nhận).
    BC failed: trong `bc_fail_window` phiên và trước khi có AR(d) (close thấp nhất <= đỉnh BC - ar_min_atr x ATR),
      có close > đỉnh BC + bc_fail_atr x ATR."""
    cfg = cfg or DistributionConfig()
    r = _rounded(df, decimals)
    width = (df["tr"] / df["atr_ref"]).round(decimals)
    min_close = df["close"].rolling(cfg.bc_trend_lookback, min_periods=cfg.bc_trend_lookback).min()
    rise = df["close"] / min_close - 1
    highest = df["high"].rolling(cfg.bc_highest_high_lookback, min_periods=cfg.bc_highest_high_lookback).max()
    ceilings = (df["close"].pct_change() >= price_limit - limit_tolerance).astype(int)
    ceiling_count = ceilings.shift(1).rolling(cfg.ceiling_chain_window, min_periods=1).sum()

    base = ((r["vol_ratio"] > cfg.bc_min_vol_ratio) & (rise >= cfg.bc_min_rise) & (df["high"] >= highest)
            & (df["close"] > df["sma"])).fillna(False)
    locked = df["ceiling_locked"] if "ceiling_locked" in df.columns else pd.Series(False, index=df.index)
    climax_mask = base & (width > cfg.bc_min_spread_atr)
    if cfg.bc_exclude_ceiling_locked:
        climax_mask &= ~locked.astype(bool)
    climax = climax_mask.to_numpy()
    chain = (base & (ceiling_count >= cfg.ceiling_chain_min_days) & (r["close_pos"] <= cfg.bc_max_close_pos)).to_numpy()

    close = df["close"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    last = len(df) - 1
    found: list[Event] = []
    for c in range(len(df)):
        if not (climax[c] or chain[c]):
            continue
        details: dict[str, Any] = {
            "rise_from_low": round(float(rise.iloc[c]), 4),
            "width_atr": float(width.iloc[c]),
            "ceiling_days_before": int(ceiling_count.iloc[c]),
        }
        if climax[c] and r["close_pos"].iloc[c] <= cfg.bc_max_close_pos:
            details["confirmation"] = "same_bar"
            found.append(_make_event(df, EventType.BC, c, c, None, details))
            continue
        if chain[c]:
            details["confirmation"] = "ceiling_chain"
            found.append(_make_event(df, EventType.BC, c, c, None, details))
            continue
        mid = (high[c] + low[c]) / 2
        for k in range(c + 1, min(c + cfg.bc_zone_bars, last) + 1):
            if high[k] > high[c]:
                break     # đỉnh mới cao hơn -> nến này không còn là đỉnh
            if close[k] < mid:
                details.update({"confirmation": "zone", "climax_mid": round(mid, 4), "reversal_close": close[k]})
                found.append(_make_event(df, EventType.BC, c, k, None, details))
                break

    bcs: list[Event] = []
    for e in sorted(found, key=lambda e: (e.confirmed_idx, e.idx)):
        if bcs and e.idx - bcs[-1].idx < cfg.bc_cooldown_bars and e.high <= bcs[-1].high:
            continue
        bcs.append(e)
    return sorted(bcs + _bc_failures(df, bcs, cfg), key=lambda e: (e.idx, e.kind.value))


def _bc_failures(df: pd.DataFrame, bcs: list[Event], cfg: DistributionConfig) -> list[Event]:
    close = df["close"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    out: list[Event] = []
    for bc in bcs:
        ar_level = bc.high - cfg.ar_min_atr * atr_ref[bc.idx]
        min_close = np.inf
        for j in range(bc.confirmed_idx + 1, min(bc.confirmed_idx + cfg.bc_fail_window, last) + 1):
            if min_close <= ar_level:
                break     # đã có AR(d) -> vượt đỉnh BC lúc này thuộc về range (ST(d) / UT), không phải BC thất bại
            if close[j] > bc.high + cfg.bc_fail_atr * atr_ref[j]:
                details = {"bc_date": _ymd(bc.date), "bc_high": bc.high,
                           "above_bc_high_atr": round(float((close[j] - bc.high) / atr_ref[j]), 3)}
                out.append(_make_event(df, EventType.BC_FAILED, j, j, None, details))
                break
            min_close = min(min_close, close[j])
    return out


def _bcs(events: list[Event]) -> tuple[list[Event], dict[str, int]]:
    bcs = [e for e in events if e.kind == EventType.BC]
    failed = {e.details["bc_date"]: e.idx for e in events if e.kind == EventType.BC_FAILED}
    return bcs, failed


# ------------------------------------------------------------------------ AR(d)

def detect_ar_d(df: pd.DataFrame, bc_events: list[Event], cfg: DistributionConfig | None = None) -> list[Event]:
    """AR(d): đáy pivot đầu tiên (ar_pivot_bars mỗi bên) sau BC, trong `ar_window` phiên, với
    low <= đỉnh BC - ar_min_atr x ATR. Xác nhận ở pivot + ar_pivot_bars. BC đã thất bại thì không có AR(d)."""
    cfg = cfg or DistributionConfig()
    bcs, failed = _bcs(bc_events)
    low = df["low"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    k = cfg.ar_pivot_bars
    out: list[Event] = []
    for bc in bcs:
        level = bc.high - cfg.ar_min_atr * atr_ref[bc.idx]
        fail_idx = failed.get(_ymd(bc.date), np.inf)
        for p in range(bc.idx + 1, min(bc.idx + cfg.ar_window, last - k) + 1):
            if p + k >= fail_idx:
                break
            if low[p] > level:
                continue
            if low[p] < low[max(p - k, 0):p].min() and low[p] <= low[p + 1:p + k + 1].min():
                details = {"bc_date": _ymd(bc.date), "reaction_atr": round(float((bc.high - low[p]) / atr_ref[bc.idx]), 3)}
                out.append(_make_event(df, EventType.AR_D, p, p + k, None, details))
                break
    return out


# ------------------------------------------------------------------------ ST(d)

def detect_st_d(df: pd.DataFrame, bc_events: list[Event], ar_events: list[Event],
                cfg: DistributionConfig | None = None) -> list[Event]:
    """ST(d): sau AR(d), trong `st_window` phiên: high trong [đỉnh BC - st_band_below_atr x ATR, đỉnh BC + st_band_above_atr x ATR],
    volume < st_max_vol_vs_bc x volume BC, biên độ < st_max_spread_vs_bc x biên độ BC, close <= đỉnh BC.
    Các ST(d) cách nhau >= st_min_gap_bars. Xác nhận tại max(phiên ST(d), phiên xác nhận AR(d)). Dừng khi BC thất bại."""
    cfg = cfg or DistributionConfig()
    bcs, failed = _bcs(bc_events)
    by_date = {_ymd(bc.date): bc for bc in bcs}
    high = df["high"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    spread = (df["high"] - df["low"]).to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    out: list[Event] = []
    for ar in ar_events:
        bc = by_date.get(ar.details["bc_date"])
        if bc is None:
            continue
        fail_idx = failed.get(ar.details["bc_date"], np.inf)
        bc_spread = bc.high - bc.low
        prev = -np.inf
        for k in range(ar.idx + 1, min(ar.idx + cfg.st_window, last) + 1):
            if k >= fail_idx:
                break
            a = atr_ref[k]
            if (
                bc.high - cfg.st_band_below_atr * a - _EPS <= high[k] <= bc.high + cfg.st_band_above_atr * a + _EPS
                and volume[k] < cfg.st_max_vol_vs_bc * bc.volume
                and spread[k] < cfg.st_max_spread_vs_bc * bc_spread
                and close[k] <= bc.high + _EPS
                and k - prev >= cfg.st_min_gap_bars
            ):
                details = {"bc_date": ar.details["bc_date"], "volume_vs_bc": round(float(volume[k] / bc.volume), 3),
                           "high_vs_bc_atr": round(float((high[k] - bc.high) / a), 3)}
                out.append(_make_event(df, EventType.ST_D, k, max(k, ar.confirmed_idx), None, details))
                prev = k
    return out


# -------------------------------------------------------------------------- SOW

def detect_sow(df: pd.DataFrame, ranges: list[TradingRange], cfg: DistributionConfig | None = None,
               decimals: int = 2) -> list[Event]:
    """SOW: trong range đã xác nhận (hoặc trong chuỗi phiên đang phá range), nến giảm close < open,
    close < support - sow_min_breakdown_atr x ATR, biên độ > sow_min_spread_atr x ATR,
    volume > sow_min_vol_ratio x TB20, close_pos <= sow_max_close_pos. Xác nhận ngay tại phiên đó.

    Dạng chuỗi khóa sàn (đặc thù VN, volume và biên độ bị khóa sàn chặn): phiên khóa sàn đầu tiên đạt đủ
    sow_floor_chain_min_days phiên khóa sàn trong `sow_floor_chain_window` phiên, close < support - sow_min_breakdown_atr x ATR.
    Một phiên khóa sàn đơn lẻ không tự động là SOW."""
    cfg = cfg or DistributionConfig()
    r = _rounded(df, decimals)
    last = len(df) - 1
    events: list[Event] = []
    if "floor_locked" in df.columns:
        locked = df["floor_locked"].astype(bool)
        reached = locked & (locked.astype(int).rolling(cfg.sow_floor_chain_window, min_periods=1).sum() >= cfg.sow_floor_chain_min_days)
        chain = reached & ~reached.shift(1, fill_value=False)
    else:
        chain = pd.Series(False, index=df.index)
    for rng in ranges:
        lo = rng.confirmed_idx + 1
        hi = rng.end_confirmed_idx if rng.end_confirmed_idx is not None else last
        if lo > hi:
            continue
        seg, rs = df.iloc[lo:hi + 1], r.iloc[lo:hi + 1]
        below = (seg["close"] < rng.support - cfg.sow_min_breakdown_atr * seg["atr_ref"]).fillna(False)
        wide = (
            below
            & (seg["close"] < seg["open"])
            & (rs["spread_atr"] > cfg.sow_min_spread_atr)
            & (rs["vol_ratio"] > cfg.sow_min_vol_ratio)
            & (rs["close_pos"] <= cfg.sow_max_close_pos)
        ).fillna(False)
        floor_form = below & chain.iloc[lo:hi + 1]
        for k in np.flatnonzero((wide | floor_form).to_numpy()):
            i = lo + int(k)
            details = {"support": round(rng.support, 4),
                       "breakdown_atr": round(float((rng.support - df["close"].iloc[i]) / df["atr_ref"].iloc[i]), 3),
                       "form": "wide_spread" if wide.iloc[int(k)] else "floor_chain"}
            events.append(_make_event(df, EventType.SOW, i, i, rng.range_id, details))
    return sorted(events, key=lambda e: e.idx)


# ------------------------------------------------------------------------- LPSY

def detect_lpsy(df: pd.DataFrame, ranges: list[TradingRange], sow_events: list[Event],
                cfg: DistributionConfig | None = None, decimals: int = 2) -> list[Event]:
    """LPSY sau SOW: trong `lpsy_window` phiên, phiên k có high <= support + lpsy_hold_below_sup_atr x ATR,
    high >= close thấp nhất từ SOW + lpsy_min_rally_atr x ATR, vol_ratio < lpsy_max_vol_ratio,
    spread_atr < lpsy_max_spread_atr. Xác nhận khi trong `lpsy_confirm_bars` phiên sau có close < low[k]. Mỗi SOW tối đa một LPSY."""
    cfg = cfg or DistributionConfig()
    r = _rounded(df, decimals)
    sup_by_id = {rg.range_id: rg.support for rg in ranges}
    low = df["low"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    vr = r["vol_ratio"].to_numpy(dtype=float)
    sa = r["spread_atr"].to_numpy(dtype=float)
    last = len(df) - 1
    out: dict[int, Event] = {}
    for sow in sow_events:
        sup = sup_by_id.get(sow.range_id)
        if sup is None:
            continue
        min_close = close[sow.idx]
        for k in range(sow.idx + 1, min(sow.idx + cfg.lpsy_window, last) + 1):
            a = atr_ref[k]
            if (
                high[k] <= sup + cfg.lpsy_hold_below_sup_atr * a + _EPS
                and high[k] >= min_close + cfg.lpsy_min_rally_atr * a - _EPS
                and vr[k] < cfg.lpsy_max_vol_ratio
                and sa[k] < cfg.lpsy_max_spread_atr
            ):
                conf = next((j for j in range(k + 1, min(k + cfg.lpsy_confirm_bars, last) + 1) if close[j] < low[k]), None)
                if conf is None and k + cfg.lpsy_confirm_bars > last:
                    break     # chưa đủ phiên để biết k có được xác nhận không -> không xét phiên sau (tránh look-ahead)
                if conf is not None:
                    if k not in out:
                        details = {"sow_date": _ymd(sow.date), "support": round(sup, 4),
                                   "high_vs_support_atr": round(float((high[k] - sup) / a), 3),
                                   "rally_atr": round(float((high[k] - min_close) / a), 3)}
                        out[k] = _make_event(df, EventType.LPSY, k, conf, sow.range_id, details)
                    break
            min_close = min(min_close, close[k])
    return sorted(out.values(), key=lambda e: e.idx)


def detect_distribution(df: pd.DataFrame, ranges: list[TradingRange], cfg: DistributionConfig | None = None,
                        decimals: int = 2, price_limit: float = 0.07, limit_tolerance: float = 0.005) -> list[Event]:
    """Mọi sự kiện phía phân phối, chưa gán vòng đời (xem `lifecycle.annotate_distribution`)."""
    cfg = cfg or DistributionConfig()
    bc = detect_buying_climax(df, cfg, decimals, price_limit, limit_tolerance)
    ar = detect_ar_d(df, bc, cfg)
    sow = detect_sow(df, ranges, cfg, decimals)
    events = bc + ar + detect_st_d(df, bc, ar, cfg) + sow + detect_lpsy(df, ranges, sow, cfg, decimals)
    return sorted(events, key=lambda e: (e.idx, e.kind.value))
