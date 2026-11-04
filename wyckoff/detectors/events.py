"""Bộ phát hiện sự kiện Wyckoff. Mỗi sự kiện một hàm thuần, ngưỡng lấy từ config.

Yêu cầu `df` đã qua `add_indicators` (cột atr_ref, vol_ratio, spread_atr, close_pos, sma).
Mọi điều kiện tại phiên t chỉ dùng dữ liệu <= t. Sự kiện cần phiên sau để xác nhận
(SC dạng vùng, Spring, Test) mang `confirmed_idx` = phiên xác nhận; trước phiên đó
sự kiện không tồn tại.

Các tỉ số (vol_ratio, spread_atr, close_pos) được làm tròn `decimals` chữ số trước khi so
ngưỡng, khớp với cách hiển thị bằng chứng (0,698 -> 0,70).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import SOS_CONFIRM_MODES, SellingClimaxConfig, SOSConfig, SpringConfig
from wyckoff.detectors.models import Event, EventStatus, EventType, StatusChange, TradingRange
from wyckoff.indicators.limits import limit_label
from wyckoff.indicators.ticks import tick_size


def _rounded(df: pd.DataFrame, decimals: int) -> pd.DataFrame:
    return df[["vol_ratio", "spread_atr", "close_pos"]].round(decimals)


def _make_event(
    df: pd.DataFrame, kind: EventType, i: int, confirmed_i: int, range_id: int | None, details: dict[str, Any]
) -> Event:
    row = df.iloc[i]
    if "limit_up" in df.columns:
        lab = limit_label(row)
        if lab is not None:
            details["limit"] = lab      # sửa tại chỗ: các detector còn cập nhật `details` sau khi tạo event
    return Event(
        kind=kind, idx=i, date=df.index[i], confirmed_idx=confirmed_i, confirmed_date=df.index[confirmed_i],
        open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
        volume=float(row["volume"]), vol_ratio=float(row["vol_ratio"]), spread_atr=float(row["spread_atr"]),
        close_pos=float(row["close_pos"]), range_id=range_id, details=details,
    )


def _change(df: pd.DataFrame, status: EventStatus, i: int, reason: str = "") -> StatusChange:
    return StatusChange(status, i, df.index[i], reason)


def _candidate(
    df: pd.DataFrame, kind: EventType, i: int, range_id: int | None, details: dict[str, Any],
    history: list[StatusChange],
) -> Event:
    """Event chưa (hoặc không bao giờ) được xác nhận: confirmed_idx = -1. Chỉ nằm trong
    `AnalysisResult.candidates`, không đi vào pha / tin cậy / backtest."""
    e = _make_event(df, kind, i, i, range_id, details)
    return replace(e, confirmed_idx=-1, confirmed_date=pd.NaT, history=tuple(history))


# --------------------------------------------------------------------------- SC

def floor_days(df: pd.DataFrame, price_limit: float = 0.07, tolerance: float = 0.005) -> pd.Series:
    """Phiên giảm sàn: close/close_trước - 1 <= -(price_limit - tolerance)."""
    return df["close"].pct_change() <= -(price_limit - tolerance)


def detect_selling_climax(
    df: pd.DataFrame,
    cfg: SellingClimaxConfig | None = None,
    decimals: int = 2,
    price_limit: float = 0.07,
    limit_tolerance: float = 0.005,
    candidates: list[Event] | None = None,
) -> list[Event]:
    """SC và SC failed.

    Điều kiện nền (mọi dạng): giảm >= min_decline từ close cao nhất `trend_lookback` phiên,
    close < SMA (nếu bật), low thấp nhất `lowest_low_lookback` phiên, volume > min_vol_ratio x TB20.

    Dạng 1 - climax: biên độ (True Range hoặc high-low, theo `spread_measure`) > min_spread_atr x ATR.
      Xác nhận ngay nếu close_pos >= min_close_pos; hoặc trong `zone_bars` phiên sau có close >
      điểm giữa nến climax mà không thủng đáy climax quá `zone_undercut_atr` x ATR (xác nhận tại phiên đó;
      đáy SC là đáy thấp nhất của cả vùng).
    Dạng 2 - chuỗi giảm sàn (đặc thù VN, biên độ bị trần/sàn chặn): >= floor_chain_min_days phiên
      giảm sàn trong `floor_chain_window` phiên trước, phiên hiện tại close_pos >= min_close_pos
      (rút chân). Không xét biên độ.
    SC failed: sau xác nhận, trong `fail_window` phiên và trước khi có AR (close cao nhất >=
      đáy SC + ar_min_atr x ATR), có close < đáy SC - fail_atr x ATR.

    `candidates` (tùy chọn): nhận các SC không thành event – climax dạng vùng chưa/không xác nhận
    (DETECTED, rồi INVALIDATED khi hết `zone_bars` hoặc thủng đáy) và SC bị gộp trong cooldown (REVISED).
    Kết quả trả về không đổi.
    """
    cfg = cfg or SellingClimaxConfig()
    r = _rounded(df, decimals)
    if cfg.spread_measure == "true_range":
        width = (df["tr"] / df["atr_ref"]).round(decimals)
    elif cfg.spread_measure == "range":
        width = r["spread_atr"]
    else:
        raise ValueError(f"spread_measure không hợp lệ: {cfg.spread_measure}")
    max_close = df["close"].rolling(cfg.trend_lookback, min_periods=cfg.trend_lookback).max()
    decline = 1 - df["close"] / max_close
    lowest = df["low"].rolling(cfg.lowest_low_lookback, min_periods=cfg.lowest_low_lookback).min()
    floors = floor_days(df, price_limit, limit_tolerance).astype(int)
    floor_count = floors.shift(1).rolling(cfg.floor_chain_window, min_periods=1).sum()

    base = (r["vol_ratio"] > cfg.min_vol_ratio) & (decline >= cfg.min_decline) & (df["low"] <= lowest)
    if cfg.require_below_sma:
        base &= df["close"] < df["sma"]
    base = base.fillna(False)
    climax = (base & (width > cfg.min_spread_atr)).to_numpy()
    chain = (base & (floor_count >= cfg.floor_chain_min_days) & (r["close_pos"] >= cfg.min_close_pos)).to_numpy()

    close = df["close"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    last = len(df) - 1
    candidates_: list[Event] = []
    for c in range(len(df)):
        if not (climax[c] or chain[c]):
            continue
        details: dict[str, Any] = {
            "decline_from_high": round(float(decline.iloc[c]), 4),
            "width_atr": float(width.iloc[c]),
            "spread_measure": cfg.spread_measure,
            "floor_days_before": int(floor_count.iloc[c]),
        }
        if climax[c] and r["close_pos"].iloc[c] >= cfg.min_close_pos:
            details["confirmation"] = "same_bar"
            candidates_.append(_make_event(df, EventType.SC, c, c, None, details))
            continue
        if chain[c]:
            details["confirmation"] = "floor_chain"
            candidates_.append(_make_event(df, EventType.SC, c, c, None, details))
            continue
        mid = (high[c] + low[c]) / 2
        floor = low[c] - cfg.zone_undercut_atr * df["atr_ref"].iloc[c]
        zone_low = low[c]
        ended: StatusChange | None = None
        confirmed = False
        for k in range(c + 1, min(c + cfg.zone_bars, last) + 1):
            if low[k] < floor:
                ended = _change(df, EventStatus.INVALIDATED, k, "thủng đáy nến climax trước khi xác nhận")
                break  # đáy mới thấp hơn -> nến climax này không còn là đáy
            zone_low = min(zone_low, low[k])
            if close[k] > mid:
                details.update({"confirmation": "zone", "climax_mid": round(mid, 4), "reversal_close": close[k]})
                event = _make_event(df, EventType.SC, c, k, None, details)
                if zone_low < low[c]:
                    details["climax_bar_low"] = float(low[c])
                    event = replace(event, low=float(zone_low))
                candidates_.append(event)
                confirmed = True
                break
        if candidates is not None and not confirmed:
            if ended is None and c + cfg.zone_bars <= last:
                ended = _change(df, EventStatus.INVALIDATED, c + cfg.zone_bars,
                                f"không có close > điểm giữa nến climax trong {cfg.zone_bars} phiên")
            hist = [_change(df, EventStatus.DETECTED, c, "climax đóng cửa thấp, chờ xác nhận vùng")]
            candidates.append(_candidate(df, EventType.SC, c, None, details, hist + ([ended] if ended else [])))

    # Gộp theo thứ tự xác nhận (causal): SC mới trong cooldown chỉ giữ nếu đáy thấp hơn.
    scs: list[Event] = []
    for e in sorted(candidates_, key=lambda e: (e.confirmed_idx, e.idx)):
        if scs and e.idx - scs[-1].idx < cfg.cooldown_bars and e.low >= scs[-1].low:
            if candidates is not None:
                hist = ([_change(df, EventStatus.DETECTED, e.idx)] if e.confirmed_idx > e.idx else []) + [
                    _change(df, EventStatus.REVISED, e.confirmed_idx,
                            f"gộp vào SC {scs[-1].date:%d/%m/%Y} (trong {cfg.cooldown_bars} phiên, đáy không thấp hơn)")]
                candidates.append(replace(e, confirmed_idx=-1, confirmed_date=pd.NaT, history=tuple(hist),
                                          details={**e.details, "merged_into_date": scs[-1].date.strftime("%Y-%m-%d")}))
            continue
        scs.append(e)
    return sorted(scs + _sc_failures(df, scs, cfg), key=lambda e: (e.idx, e.kind.value))


def _sc_failures(df: pd.DataFrame, scs: list[Event], cfg: SellingClimaxConfig) -> list[Event]:
    close = df["close"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    last = len(df) - 1
    out: list[Event] = []
    for sc in scs:
        ar_level = sc.low + cfg.ar_min_atr * atr_ref[sc.idx]
        max_close = -np.inf
        for j in range(sc.confirmed_idx + 1, min(sc.confirmed_idx + cfg.fail_window, last) + 1):
            if max_close >= ar_level:
                break  # đã có AR -> thủng đáy SC lúc này thuộc về range (ST/Spring), không phải SC thất bại
            if close[j] < sc.low - cfg.fail_atr * atr_ref[j]:
                details = {
                    "sc_date": sc.date.strftime("%Y-%m-%d"),
                    "sc_low": sc.low,
                    "below_sc_low_atr": round(float((sc.low - close[j]) / atr_ref[j]), 3),
                }
                out.append(_make_event(df, EventType.SC_FAILED, j, j, None, details))
                break
            max_close = max(max_close, close[j])
    return out


# ----------------------------------------------------------------------- Spring

def detect_spring(
    df: pd.DataFrame,
    ranges: list[TradingRange],
    cfg: SpringConfig | None = None,
    exchange: str = "HOSE",
    decimals: int = 2,
    candidates: list[Event] | None = None,
) -> list[Event]:
    """Spring và Test. Với mỗi range đã xác nhận có bối cảnh thuộc `allowed_contexts`:

    1. Phiên thủng b: b >= confirmed_idx + min_bars_after_confirm; phiên b-1 chưa thủng;
       low_b < support - pen, với pen = max(min_penetration_atr x ATR, min_penetration_ticks x tick).
    2. Phiên hồi r trong [b, b + max_recovery_bars - 1]: phiên đầu tiên có
       close >= support + recovery_min_ticks x tick và close_pos >= recovery_min_close_pos.
    3. Phiên thủng = các phiên trong [b, r] có low < support.
       - Mọi phiên thủng có vol_ratio < max_vol_ratio  -> Spring (low_volume), xác nhận tại r.
       - Ngược lại -> Shakeout: cần Test trong (r, r + test_window], không phiên nào trước Test
         thủng đáy shakeout; Test: low >= đáy shakeout,
         low <= support + test_proximity_atr x ATR, volume < test_vol_factor x volume phiên thủng lớn nhất,
         support <= close <= resistance. Có Test -> Spring (shakeout) + Test, xác nhận tại phiên Test.
    4. Gộp (causal): Spring mới có phiên thủng cách Spring trước < merge_bars phiên chỉ giữ
       nếu đáy thấp hơn.

    `candidates` (tùy chọn): nhận mọi phiên thủng không thành Spring – DETECTED tại phiên thủng,
    CANDIDATE tại phiên hồi (shakeout chờ Test), INVALIDATED khi không hồi / không có Test / thủng
    đáy shakeout / range kết thúc; Spring bị gộp -> REVISED. Chưa hết thời hạn chờ -> để mở.
    Kết quả trả về không đổi.
    """
    cfg = cfg or SpringConfig()
    r_ = _rounded(df, decimals)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    vol_ratio = r_["vol_ratio"].to_numpy(dtype=float)
    close_pos = r_["close_pos"].to_numpy(dtype=float)
    last = len(df) - 1
    eps = 1e-9

    found: list[tuple[Event, Event | None]] = []  # (Spring, Test hoặc None)
    for rng in ranges:
        if rng.context not in cfg.allowed_contexts:
            continue  # vd. range phân phối: thủng support không được coi là Spring
        sup, res = rng.support, rng.resistance
        tick = tick_size(sup, exchange)
        b = max(rng.confirmed_idx + cfg.min_bars_after_confirm, 1)
        while b <= last and rng.known_active_at(b, last):
            if np.isnan(atr_ref[b]):
                b += 1
                continue
            pen = max(cfg.min_penetration_atr * atr_ref[b], cfg.min_penetration_ticks * tick)
            prev_pen = max(cfg.min_penetration_atr * atr_ref[b - 1], cfg.min_penetration_ticks * tick) \
                if not np.isnan(atr_ref[b - 1]) else pen
            if not (low[b] < sup - pen - eps and low[b - 1] >= sup - prev_pen - eps):
                b += 1
                continue

            recovery = None
            ended: StatusChange | None = None
            for k in range(b, min(b + cfg.max_recovery_bars, last + 1)):
                if not rng.known_active_at(k, last):
                    ended = _change(df, EventStatus.INVALIDATED, k, "range kết thúc trước khi hồi")
                    break
                if close[k] >= sup + cfg.recovery_min_ticks * tick - eps and close_pos[k] >= cfg.recovery_min_close_pos:
                    recovery = k
                    break
            if recovery is None:
                if candidates is not None:
                    end_k = b + cfg.max_recovery_bars - 1
                    if ended is None and end_k <= last:
                        ended = _change(df, EventStatus.INVALIDATED, end_k,
                                        f"không đóng cửa lại trên support trong {cfg.max_recovery_bars} phiên")
                    hist = [_change(df, EventStatus.DETECTED, b, "thủng support")] + ([ended] if ended else [])
                    det = {"support": round(sup, 4),
                           "penetration_atr": round(float((sup - low[b]) / atr_ref[b]), 3), "lowest_low": float(low[b])}
                    candidates.append(_candidate(df, EventType.SPRING, b, rng.range_id, det, hist))
                b += 1
                continue

            pen_bars = [k for k in range(b, recovery + 1) if low[k] < sup]
            max_vr = float(max(vol_ratio[k] for k in pen_bars))
            spring_low = float(low[b:recovery + 1].min())
            details: dict[str, Any] = {
                "support": round(sup, 4),
                "penetration_atr": round(float((sup - spring_low) / atr_ref[b]), 3),
                "lowest_low": spring_low,
                "max_vol_ratio_below_support": round(max_vr, 3),
                "recovery_date": df.index[recovery].strftime("%Y-%m-%d"),
                "recovery_bars": recovery - b + 1,
                "recovery_close": float(close[recovery]),
                "recovery_close_pos": float(close_pos[recovery]),
            }
            if max_vr < cfg.max_vol_ratio:
                details["spring_type"] = "low_volume"
                found.append((_make_event(df, EventType.SPRING, b, recovery, rng.range_id, details), None))
            else:
                shake_vol = float(max(volume[k] for k in pen_bars))
                test = None
                for k in range(recovery + 1, min(recovery + cfg.test_window, last) + 1):
                    if not rng.known_active_at(k, last) or np.isnan(atr_ref[k]):
                        ended = _change(df, EventStatus.INVALIDATED, k, "range kết thúc trước khi có Test")
                        break
                    if low[k] < spring_low:
                        ended = _change(df, EventStatus.INVALIDATED, k, "thủng đáy shakeout trước khi có Test")
                        break  # đáy shakeout bị phá trước khi có Test -> shakeout thất bại
                    if (
                        low[k] >= spring_low
                        and low[k] <= sup + cfg.test_proximity_atr * atr_ref[k] + eps
                        and volume[k] < cfg.test_vol_factor * shake_vol
                        and sup - eps <= close[k] <= res + eps
                    ):
                        test = k
                        break
                if test is not None:
                    details.update({"spring_type": "shakeout", "test_date": df.index[test].strftime("%Y-%m-%d")})
                    spring = _make_event(df, EventType.SPRING, b, test, rng.range_id, details)
                    test_details = {
                        "spring_date": df.index[b].strftime("%Y-%m-%d"),
                        "spring_low": spring_low,
                        "volume_vs_shakeout": round(float(volume[test] / shake_vol), 3),
                        "support": round(sup, 4),
                    }
                    found.append((spring, _make_event(df, EventType.TEST, test, test, rng.range_id, test_details)))
                elif candidates is not None:
                    if ended is None and recovery + cfg.test_window <= last:
                        ended = _change(df, EventStatus.INVALIDATED, recovery + cfg.test_window,
                                        f"không có Test trong {cfg.test_window} phiên")
                    details["spring_type"] = "shakeout"
                    hist = [_change(df, EventStatus.DETECTED, b, "thủng support")] if recovery > b else []
                    hist.append(_change(df, EventStatus.CANDIDATE, recovery, "shakeout volume cao, chờ Test"))
                    candidates.append(_candidate(df, EventType.SPRING, b, rng.range_id, details,
                                                 hist + ([ended] if ended else [])))
            b = recovery + 1

    events: list[Event] = []
    kept: list[Event] = []
    for spring, test in sorted(found, key=lambda p: (p[0].confirmed_idx, p[0].idx)):
        near = [s for s in kept if s.range_id == spring.range_id and abs(spring.idx - s.idx) < cfg.merge_bars]
        if near and spring.details["lowest_low"] >= min(s.details["lowest_low"] for s in near):
            if candidates is not None:
                into = min(near, key=lambda s: s.details["lowest_low"])
                hist = [_change(df, EventStatus.DETECTED, spring.idx, "thủng support")] \
                    if spring.confirmed_idx > spring.idx else []
                hist.append(_change(df, EventStatus.REVISED, spring.confirmed_idx,
                                    f"gộp vào Spring {into.date:%d/%m/%Y} (cách < {cfg.merge_bars} phiên, đáy không thấp hơn)"))
                candidates.append(replace(spring, confirmed_idx=-1, confirmed_date=pd.NaT, history=tuple(hist),
                                          details={**spring.details, "merged_into_date": into.date.strftime("%Y-%m-%d")}))
            continue
        kept.append(spring)
        events.append(spring)
        if test is not None:
            events.append(test)
    return sorted(events, key=lambda e: (e.idx, e.kind.value))


# -------------------------------------------------------------------------- SOS

def _sos_bar(row: pd.Series, rr: pd.Series, resistance: float, cfg: SOSConfig) -> bool:
    return bool(
        row["close"] > row["open"]
        and row["close"] > resistance + cfg.min_breakout_atr * row["atr_ref"]
        and rr["spread_atr"] > cfg.min_spread_atr
        and rr["vol_ratio"] > cfg.min_vol_ratio
        and rr["close_pos"] >= cfg.min_close_pos
    )


def _needs_follow_through(df: pd.DataFrame, i: int, cfg: SOSConfig) -> bool:
    if cfg.confirm_mode not in SOS_CONFIRM_MODES:
        raise ValueError(f"sos.confirm_mode không hợp lệ: {cfg.confirm_mode}")
    if cfg.confirm_mode == "follow_through":
        return True
    return cfg.confirm_mode == "locked_follow_through" and bool(df["ceiling_locked"].iloc[i]) \
        if "ceiling_locked" in df.columns else False


def _follow_through(
    df: pd.DataFrame, i: int, resistance: float, cfg: SOSConfig
) -> tuple[int | None, StatusChange | None, str]:
    """(phiên xác nhận, mốc thất bại, cách xác nhận). Cả hai None = chưa đủ dữ liệu (còn candidate).
    Trong (i, i + N]: close < resistance -> thất bại; close > high[i] -> xác nhận; giữ đủ N phiên -> xác nhận tại i + N."""
    close = df["close"].to_numpy(dtype=float)
    hi = float(df["high"].iloc[i])
    last = len(df) - 1
    n = cfg.follow_through_bars
    for j in range(i + 1, min(i + n, last) + 1):
        if close[j] < resistance:
            return None, _change(df, EventStatus.INVALIDATED, j,
                                 f"close {close[j]:.2f} quay lại dưới resistance {resistance:.2f} trong {n} phiên"), ""
        if close[j] > hi:
            return j, None, "close vượt high phiên breakout"
    if i + n <= last:
        return i + n, None, f"giữ trên resistance {n} phiên"
    return None, None, ""


def _sos_event(
    df: pd.DataFrame, i: int, rng: TradingRange, cfg: SOSConfig, details: dict[str, Any],
    candidates: list[Event] | None,
) -> tuple[Event | None, Event | None]:
    """(SOS đã xác nhận, candidate). Phiên không cần follow-through -> xác nhận ngay như v2."""
    if not _needs_follow_through(df, i, cfg):
        return _make_event(df, EventType.SOS, i, i, rng.range_id, details), None
    conf, ended, how = _follow_through(df, i, rng.resistance, cfg)
    if conf is not None:
        details.update({"follow_through": how, "follow_through_bars": conf - i})
        return _make_event(df, EventType.SOS, i, conf, rng.range_id, details), None
    hist = [_change(df, EventStatus.DETECTED, i, "breakout, chờ follow-through")] + ([ended] if ended else [])
    return None, _candidate(df, EventType.SOS, i, rng.range_id, details, hist)


def detect_sos(
    df: pd.DataFrame, ranges: list[TradingRange], cfg: SOSConfig | None = None, decimals: int = 2,
    candidates: list[Event] | None = None,
) -> list[Event]:
    """SOS: trong range đã xác nhận (hoặc trong chuỗi phiên đang phá range), nến tăng
    close > open, close > resistance + min_breakout_atr x ATR, spread > min_spread_atr x ATR,
    volume > min_vol_ratio x TB20, close_pos >= min_close_pos.

    `confirm_mode` (H5): same_bar -> xác nhận tại phiên breakout; follow_through / locked_follow_through ->
    xác nhận theo `_follow_through`, phiên breakout thất bại hoặc chưa đủ dữ liệu vào `candidates`."""
    cfg = cfg or SOSConfig()
    r = _rounded(df, decimals)
    last = len(df) - 1
    events: list[Event] = []
    for rng in ranges:
        lo = rng.confirmed_idx + 1
        hi = rng.end_confirmed_idx if rng.end_confirmed_idx is not None else last
        if lo > hi:
            continue
        seg, rs = df.iloc[lo:hi + 1], r.iloc[lo:hi + 1]
        cond = (
            (seg["close"] > seg["open"])
            & (seg["close"] > rng.resistance + cfg.min_breakout_atr * seg["atr_ref"])
            & (rs["spread_atr"] > cfg.min_spread_atr)
            & (rs["vol_ratio"] > cfg.min_vol_ratio)
            & (rs["close_pos"] >= cfg.min_close_pos)
        ).fillna(False)
        for k in np.flatnonzero(cond.to_numpy()):
            i = lo + int(k)
            details = {
                "resistance": round(rng.resistance, 4),
                "breakout_atr": round(float((df["close"].iloc[i] - rng.resistance) / df["atr_ref"].iloc[i]), 3),
            }
            ev, cand = _sos_event(df, i, rng, cfg, details, candidates)
            if ev is not None:
                events.append(ev)
            elif candidates is not None:
                candidates.append(cand)
    return sorted(events, key=lambda e: e.idx)


def detect_sos_reclaim(
    df: pd.DataFrame, ranges: list[TradingRange], cfg: SOSConfig | None = None, window: int = 30, decimals: int = 2,
    candidates: list[Event] | None = None,
) -> list[Event]:
    """SOS reclaim: range đã thoát xuống nhưng trong `window` phiên sau (chưa có range mới xác nhận) có phiên
    thỏa đúng quy tắc SOS so với resistance cũ -> nhịp thoát xuống là cú rũ kéo dài, không phải phá vỡ.
    Mỗi range tối đa một sự kiện: phiên đầu tiên (same_bar), hoặc candidate được xác nhận sớm nhất (follow-through;
    candidate khác chưa kết thúc tại đó -> REVISED). `window` <= 0: tắt."""
    if window <= 0:
        return []
    cfg = cfg or SOSConfig()
    r = _rounded(df, decimals)
    confirmed = [q.confirmed_idx for q in ranges]
    last = len(df) - 1
    events: list[Event] = []
    for rng in ranges:
        if rng.exit_direction != "down" or rng.end_confirmed_idx is None:
            continue
        x = rng.end_confirmed_idx
        next_range = min((c for c in confirmed if c > x), default=last + 1)
        found: list[tuple[Event | None, Event | None]] = []
        for i in range(x + 1, min(x + window, last, next_range - 1) + 1):
            if found and found[0][0] is not None and i > found[0][0].confirmed_idx:
                break     # đã có SOS reclaim xác nhận trước phiên này
            row, rr = df.iloc[i], r.iloc[i]
            if not _sos_bar(row, rr, rng.resistance, cfg):
                continue
            details = {
                "reclaim": True,
                "resistance": round(rng.resistance, 4),
                "breakout_atr": round(float((row["close"] - rng.resistance) / row["atr_ref"]), 3),
                "exit_date": df.index[x].strftime("%Y-%m-%d"),
                "bars_after_exit": i - x,
            }
            pair = _sos_event(df, i, rng, cfg, details, candidates)
            found.append(pair)
            found.sort(key=lambda p: (p[0].confirmed_idx, p[0].idx) if p[0] is not None else (10**9, 0))
            if pair[0] is not None and pair[0].confirmed_idx == i:
                break     # xác nhận ngay (same_bar): như v2
        chosen = found[0][0] if found and found[0][0] is not None else None
        if chosen is not None:
            events.append(chosen)
        if candidates is None:
            continue
        for ev, cand in found:
            if ev is chosen and ev is not None:
                continue
            item = cand if cand is not None else replace(ev, confirmed_idx=-1, confirmed_date=pd.NaT, history=(
                _change(df, EventStatus.DETECTED, ev.idx, "breakout, chờ follow-through"),))
            if chosen is not None:
                hist = [h for h in item.history if h.idx < chosen.confirmed_idx]
                ended = any(h.status == EventStatus.INVALIDATED for h in hist)
                if not ended:
                    hist.append(_change(df, EventStatus.REVISED, chosen.confirmed_idx,
                                        f"đã có SOS reclaim {chosen.date:%d/%m/%Y} xác nhận"))
                item = replace(item, history=tuple(hist))
            candidates.append(item)
    return sorted(events, key=lambda e: e.idx)
