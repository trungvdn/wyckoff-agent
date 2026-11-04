"""Sự kiện cấu trúc tích lũy: PS, AR, ST (neo theo SC), LPS (sau SOS), UTAD (cảnh báo).

Mỗi sự kiện là một hàm thuần, chỉ dùng dữ liệu đến phiên xác nhận (`confirmed_idx`).
Yêu cầu `df` đã qua `add_indicators`.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import UTAD_MODES, ARConfig, LPSConfig, PSConfig, STConfig, UTADConfig
from wyckoff.detectors.events import _candidate, _change, _make_event, _rounded
from wyckoff.detectors.models import Event, EventStatus, EventType, StatusChange, TradingRange
from wyckoff.fmt import vn_num
from wyckoff.detectors.trading_range import RangeAnchor
from wyckoff.indicators.ticks import tick_size

_EPS = 1e-9


def _scs(events: list[Event]) -> tuple[list[Event], dict[str, int]]:
    """SC hợp lệ và phiên SC failed (theo ngày SC) để biết SC nào đã thất bại khi nào."""
    scs = [e for e in events if e.kind == EventType.SC]
    failed = {e.details["sc_date"]: e.idx for e in events if e.kind == EventType.SC_FAILED}
    return scs, failed


# --------------------------------------------------------------------------- PS

def detect_ps(df: pd.DataFrame, sc_events: list[Event], cfg: PSConfig | None = None, decimals: int = 2) -> list[Event]:
    """PS: trong `lookback` phiên trước SC (lấy phiên gần SC nhất): volume >= min_vol_ratio x TB20,
    close_pos >= min_close_pos, biên độ >= min_spread_atr x ATR, low > đáy SC, (close < SMA).
    Chỉ biết là PS khi SC đã xác nhận -> confirmed_idx = phiên xác nhận SC."""
    cfg = cfg or PSConfig()
    r = _rounded(df, decimals)
    scs, _ = _scs(sc_events)
    out: list[Event] = []
    for sc in scs:
        for j in range(sc.idx - 1, max(sc.idx - cfg.lookback, 0) - 1, -1):
            ok = (
                r["vol_ratio"].iloc[j] >= cfg.min_vol_ratio
                and r["close_pos"].iloc[j] >= cfg.min_close_pos
                and r["spread_atr"].iloc[j] >= cfg.min_spread_atr
                and df["low"].iloc[j] > sc.low
                and (not cfg.require_below_sma or df["close"].iloc[j] < df["sma"].iloc[j])
            )
            if ok:
                details = {"sc_date": sc.date.strftime("%Y-%m-%d"), "bars_before_sc": sc.idx - j}
                out.append(_make_event(df, EventType.PS, j, sc.confirmed_idx, None, details))
                break
    return out


# --------------------------------------------------------------------------- AR

def detect_ar(df: pd.DataFrame, sc_events: list[Event], cfg: ARConfig | None = None) -> list[Event]:
    """AR: đỉnh pivot đầu tiên (pivot_bars mỗi bên) sau SC, trong `window` phiên, với
    high >= đáy SC + min_rally_atr x ATR. Xác nhận ở phiên pivot + pivot_bars.
    SC đã thất bại trước khi AR được xác nhận thì không có AR."""
    cfg = cfg or ARConfig()
    scs, failed = _scs(sc_events)
    high = df["high"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    k = cfg.pivot_bars
    out: list[Event] = []
    for sc in scs:
        level = sc.low + cfg.min_rally_atr * atr_ref[sc.idx]
        fail_idx = failed.get(sc.date.strftime("%Y-%m-%d"), np.inf)
        for p in range(sc.idx + 1, min(sc.idx + cfg.window, last - k) + 1):
            if p + k >= fail_idx:
                break
            if high[p] < level:
                continue
            left = high[max(p - k, 0):p]
            if high[p] > left.max() and high[p] >= high[p + 1:p + k + 1].max():
                details = {
                    "sc_date": sc.date.strftime("%Y-%m-%d"),
                    "rally_atr": round(float((high[p] - sc.low) / atr_ref[sc.idx]), 3),
                }
                out.append(_make_event(df, EventType.AR, p, p + k, None, details))
                break
    return out


def sc_ar_anchors(sc_events: list[Event], ar_events: list[Event]) -> list[RangeAnchor]:
    """Mỗi AR cho một mốc neo range: support = đáy SC, resistance = đỉnh AR, biết tại phiên AR xác nhận."""
    scs, _ = _scs(sc_events)
    by_date = {sc.date.strftime("%Y-%m-%d"): sc for sc in scs}
    out: list[RangeAnchor] = []
    for ar in ar_events:
        sc = by_date.get(ar.details["sc_date"])
        if sc is not None:
            out.append(RangeAnchor(sc.idx, ar.confirmed_idx, sc.low, ar.high))
    return out


# --------------------------------------------------------------------------- ST

def detect_st(
    df: pd.DataFrame, sc_events: list[Event], ar_events: list[Event], cfg: STConfig | None = None
) -> list[Event]:
    """ST: sau AR, trong `window` phiên: low trong [đáy SC - band_below_atr x ATR, đáy SC + band_above_atr x ATR],
    volume < max_vol_vs_sc x volume SC, biên độ < max_spread_vs_sc x biên độ SC, close >= đáy SC.
    Các ST cách nhau >= min_gap_bars. Xác nhận tại max(phiên ST, phiên xác nhận AR).
    Dừng khi SC thất bại."""
    cfg = cfg or STConfig()
    scs, failed = _scs(sc_events)
    by_date = {sc.date.strftime("%Y-%m-%d"): sc for sc in scs}
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    spread = (df["high"] - df["low"]).to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    out: list[Event] = []
    for ar in ar_events:
        sc = by_date.get(ar.details["sc_date"])
        if sc is None:
            continue
        fail_idx = failed.get(ar.details["sc_date"], np.inf)
        sc_spread = sc.high - sc.low
        prev = -np.inf
        for k in range(ar.idx + 1, min(ar.idx + cfg.window, last) + 1):
            if k >= fail_idx:
                break
            a = atr_ref[k]
            if (
                sc.low - cfg.band_below_atr * a - _EPS <= low[k] <= sc.low + cfg.band_above_atr * a + _EPS
                and volume[k] < cfg.max_vol_vs_sc * sc.volume
                and spread[k] < cfg.max_spread_vs_sc * sc_spread
                and close[k] >= sc.low - _EPS
                and k - prev >= cfg.min_gap_bars
            ):
                details = {
                    "sc_date": ar.details["sc_date"],
                    "volume_vs_sc": round(float(volume[k] / sc.volume), 3),
                    "low_vs_sc_atr": round(float((low[k] - sc.low) / a), 3),
                }
                out.append(_make_event(df, EventType.ST, k, max(k, ar.confirmed_idx), None, details))
                prev = k
    return out


# -------------------------------------------------------------------------- LPS

def detect_lps(
    df: pd.DataFrame, ranges: list[TradingRange], sos_events: list[Event], cfg: LPSConfig | None = None,
    decimals: int = 2,
) -> list[Event]:
    """LPS sau SOS: trong `window` phiên, phiên k có low >= resistance - hold_above_res_atr x ATR,
    low <= close cao nhất từ SOS - min_pullback_atr x ATR, vol_ratio < max_vol_ratio,
    spread_atr < max_spread_atr. Xác nhận khi trong `confirm_bars` phiên sau có close > high[k].
    Mỗi SOS tối đa một LPS."""
    cfg = cfg or LPSConfig()
    r = _rounded(df, decimals)
    res_by_id = {rg.range_id: rg.resistance for rg in ranges}
    low = df["low"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    vr = r["vol_ratio"].to_numpy(dtype=float)
    sa = r["spread_atr"].to_numpy(dtype=float)
    last = len(df) - 1
    out: dict[int, Event] = {}
    for sos in sos_events:
        res = res_by_id.get(sos.range_id)
        if res is None:
            continue
        max_close = close[sos.idx]
        for k in range(sos.idx + 1, min(sos.idx + cfg.window, last) + 1):
            a = atr_ref[k]
            if (
                low[k] >= res - cfg.hold_above_res_atr * a - _EPS
                and low[k] <= max_close - cfg.min_pullback_atr * a + _EPS
                and vr[k] < cfg.max_vol_ratio
                and sa[k] < cfg.max_spread_atr
            ):
                conf = next((j for j in range(k + 1, min(k + cfg.confirm_bars, last) + 1) if close[j] > high[k]), None)
                if conf is None and k + cfg.confirm_bars > last:
                    break  # chưa đủ phiên để biết k có được xác nhận không -> không xét phiên sau (tránh look-ahead)
                if conf is not None:
                    if k not in out:
                        details = {
                            "sos_date": sos.date.strftime("%Y-%m-%d"),
                            "resistance": round(res, 4),
                            "low_vs_resistance_atr": round(float((low[k] - res) / a), 3),
                            "pullback_atr": round(float((max_close - low[k]) / a), 3),
                        }
                        # LPS không thể biết trước khi SOS của nó xác nhận (SOS follow-through, H5)
                        out[k] = _make_event(df, EventType.LPS, k, max(conf, sos.confirmed_idx), sos.range_id, details)
                    break
            max_close = max(max_close, close[k])
    return sorted(out.values(), key=lambda e: e.idx)


# ------------------------------------------------------------------------- UTAD

def _weakness(
    df: pd.DataFrame, ret: int, mid: float, highest: float, window: int
) -> tuple[int | None, StatusChange | None]:
    """H6: trong (ret, ret + window]: close > đỉnh upthrust -> vô hiệu; close < giữa range -> xác nhận.
    (None, None) = chưa đủ dữ liệu."""
    close = df["close"].to_numpy(dtype=float)
    last = len(df) - 1
    for j in range(ret + 1, min(ret + window, last) + 1):
        if close[j] > highest + _EPS:
            return None, _change(df, EventStatus.INVALIDATED, j,
                                 f"close {vn_num(close[j])} vượt đỉnh upthrust {vn_num(highest)}: breakout thật")
        if close[j] < mid - _EPS:
            return j, None
    if ret + window <= last:
        return None, _change(df, EventStatus.INVALIDATED, ret + window,
                             f"không có close dưới giữa range {vn_num(mid)} trong {window} phiên")
    return None, None


def detect_utad(
    df: pd.DataFrame, ranges: list[TradingRange], cfg: UTADConfig | None = None, exchange: str = "HOSE",
    decimals: int = 2, candidates: list[Event] | None = None,
) -> list[Event]:
    """Upthrust (đối xứng Spring): range đã xác nhận >= min_bars_after_confirm phiên; phiên đầu tiên
    high > resistance + max(min_penetration_atr x ATR, min_penetration_ticks x tick); trong
    `max_return_bars` phiên (tính cả phiên vượt) có close <= resistance - return_ticks x tick và
    close_pos <= max_close_pos.

    mode v2: mọi upthrust là UTAD; sự kiện tại phiên vượt, xác nhận tại phiên quay lại.
    mode ut_utad (H6): upthrust đầu tiên trong range = UT, từ lần thứ hai = UTAD; xác nhận khi có yếu kém
    (`_weakness`); upthrust không quay lại / không xác nhận / chưa đủ dữ liệu vào `candidates`."""
    cfg = cfg or UTADConfig()
    if cfg.mode not in UTAD_MODES:
        raise ValueError(f"utad.mode không hợp lệ: {cfg.mode}")
    split = cfg.mode == "ut_utad"
    r = _rounded(df, decimals)
    high = df["high"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    cp = r["close_pos"].to_numpy(dtype=float)
    last = len(df) - 1
    out: list[Event] = []
    for rng in ranges:
        res = rng.resistance
        mid = (rng.support + rng.resistance) / 2
        tick = tick_size(res, exchange)
        returned = 0      # số upthrust đã quay lại TR trong range này (biết trước phiên b)
        b = rng.confirmed_idx + cfg.min_bars_after_confirm
        while b <= last and rng.known_active_at(b, last):
            if np.isnan(atr_ref[b]) or np.isnan(atr_ref[b - 1]):
                b += 1
                continue
            pen = max(cfg.min_penetration_atr * atr_ref[b], cfg.min_penetration_ticks * tick)
            prev_pen = max(cfg.min_penetration_atr * atr_ref[b - 1], cfg.min_penetration_ticks * tick)
            if not (high[b] > res + pen + _EPS and high[b - 1] <= res + prev_pen + _EPS):
                b += 1
                continue
            kind = EventType.UTAD if (not split or returned > 0) else EventType.UT
            ret = None
            ended: StatusChange | None = None
            for k in range(b, min(b + cfg.max_return_bars, last + 1)):
                if not rng.known_active_at(k, last):
                    ended = _change(df, EventStatus.INVALIDATED, k, "range kết thúc trước khi quay lại")
                    break
                if close[k] <= res - cfg.return_ticks * tick + _EPS and cp[k] <= cfg.max_close_pos:
                    ret = k
                    break
            if ret is None:
                if split and candidates is not None:
                    end_k = b + cfg.max_return_bars - 1
                    if ended is None and end_k <= last:
                        ended = _change(df, EventStatus.INVALIDATED, end_k,
                                        f"không đóng cửa lại dưới resistance trong {cfg.max_return_bars} phiên")
                    hist = [_change(df, EventStatus.DETECTED, b, "vượt resistance")] + ([ended] if ended else [])
                    det = {"resistance": round(res, 4), "upthrust_no": returned + 1, "context": rng.context}
                    candidates.append(_candidate(df, kind, b, rng.range_id, det, hist))
                b += 1
                continue
            highest = float(high[b:ret + 1].max())
            details: dict[str, Any] = {
                "resistance": round(res, 4),
                "highest_high": highest,
                "penetration_atr": round(float((highest - res) / atr_ref[b]), 3),
                "return_date": df.index[ret].strftime("%Y-%m-%d"),
                "return_bars": ret - b + 1,
                "context": rng.context,
            }
            returned += 1
            if not split:
                out.append(_make_event(df, EventType.UTAD, b, ret, rng.range_id, details))
                b = ret + 1
                continue
            details["upthrust_no"] = returned
            details["range_mid"] = round(mid, 4)
            conf, ended = _weakness(df, ret, mid, highest, cfg.weakness_window)
            if conf is not None:
                details.update({"weakness_date": df.index[conf].strftime("%Y-%m-%d"),
                                "weakness_close": float(close[conf])})
                out.append(_make_event(df, kind, b, conf, rng.range_id, details))
            elif candidates is not None:
                hist = [_change(df, EventStatus.DETECTED, b, "vượt resistance")] if ret > b else []
                hist.append(_change(df, EventStatus.CANDIDATE, ret, "quay lại TR, chờ yếu kém"))
                candidates.append(_candidate(df, kind, b, rng.range_id, details, hist + ([ended] if ended else [])))
            b = ret + 1
    return sorted(out, key=lambda e: e.idx)
