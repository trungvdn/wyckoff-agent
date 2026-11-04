"""Xác định pha Wyckoff (sơ đồ tích lũy) bằng state machine causal.

Duyệt từng phiên t; chỉ dùng range đã xác nhận / đã kết thúc tại t và sự kiện có
`confirmed_idx == t`. Thứ tự xử lý trong một phiên: range thoát -> range xác nhận ->
sự kiện -> kiểm tra giá (vô hiệu pha C).

    A  SC xác nhận                       -> B khi có ST
    B  ST, hoặc range xác nhận không SC  -> C khi Spring, -> D khi SOS
    C  Spring (volume thấp / shakeout+Test) -> D khi SOS
    D  SOS (LPS ghi nhận)                -> E khi range thoát lên
    E  range thoát lên
    invalid: UTAD, range thoát xuống, pha C close < đáy Spring - k ATR
             -> D nếu trong `reclaim_window` phiên có SOS lấy lại resistance cũ (SOS reclaim). Range đã kết thúc nên
             sau đó E / invalid xét theo quy tắc thoát range của RangeConfig ngay trên biên cũ
             (SC failed chỉ vô hiệu khi phase.sc_failed_invalidates=True; mặc định giữ pha A
             như vùng climax kéo dài và chờ SC mới)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import D_INVALID_MODES, Config, PhaseConfig, RangeConfig
from wyckoff.detectors.models import SPRING_TYPE_LABEL, Event, EventType, TradingRange
from wyckoff.fmt import vn_g, vn_int, vn_num, vn_ts
from wyckoff.indicators.ticks import tick_size

PHASES = ("A", "B", "C", "D", "E", "invalid")

_EVENT_ORDER = {
    EventType.SC: 0, EventType.SC_FAILED: 1, EventType.PS: 2, EventType.AR: 3, EventType.ST: 4,
    EventType.SPRING: 5, EventType.TEST: 6, EventType.SOS: 7, EventType.LPS: 8, EventType.UTAD: 9,
}


@dataclass
class Structure:
    """Một cấu trúc tích lũy đang được theo dõi."""
    sid: int
    phase: str
    sc: Event | None = None
    ar: Event | None = None
    rng: TradingRange | None = None
    spring: Event | None = None
    sos: Event | None = None
    lps: Event | None = None
    events: list[Event] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class PhaseSegment:
    phase: str
    structure_id: int
    range_id: int | None
    start_idx: int
    start_date: pd.Timestamp
    end_idx: int
    end_date: pd.Timestamp
    reason: str                     # sự kiện / điều kiện mở pha, kèm ngày


@dataclass(frozen=True)
class Level:
    label: str
    condition: str
    price: float | None = None


@dataclass(frozen=True)
class CurrentPhase:
    date: pd.Timestamp
    phase: str | None
    since: pd.Timestamp | None
    reason: str
    range_id: int | None
    range_context: str | None
    support: float | None
    resistance: float | None
    atr: float
    evidence: list[str]
    confirm: list[Level]
    invalidate: list[Level]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["confirm"] = [lv.__dict__ for lv in self.confirm]
        d["invalidate"] = [lv.__dict__ for lv in self.invalidate]
        return d


@dataclass
class PhaseResult:
    series: pd.DataFrame            # mỗi phiên: phase, structure_id, range_id
    segments: list[PhaseSegment]
    structures: dict[int, Structure]


def _attach(sc: Event, rng: TradingRange, atr_at_sc: float, cfg: PhaseConfig) -> bool:
    return abs(sc.idx - rng.start_idx) <= cfg.attach_max_bars and abs(sc.low - rng.support) <= cfg.attach_max_atr * atr_at_sc


def _v(e: Event | pd.Timestamp) -> str:
    """Ngày hiển thị dd/mm/yyyy."""
    return vn_ts(e.date if isinstance(e, Event) else e)


def _d(e: Event | pd.Timestamp) -> str:
    ts = e.date if isinstance(e, Event) else e
    return f"{ts:%Y-%m-%d}"


def classify_phases(
    df: pd.DataFrame, ranges: list[TradingRange], events: list[Event], cfg: PhaseConfig | None = None,
    range_cfg: RangeConfig | None = None,
) -> PhaseResult:
    cfg = cfg or PhaseConfig()
    range_cfg = range_cfg or RangeConfig()
    n = len(df)
    close = df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)

    by_conf: dict[int, list[Event]] = {}
    for e in events:
        by_conf.setdefault(e.confirmed_idx, []).append(e)
    for lst in by_conf.values():
        lst.sort(key=lambda e: (_EVENT_ORDER.get(e.kind, 99), e.idx))
    conf_at = {r.confirmed_idx: r for r in ranges}
    exit_at = {r.end_confirmed_idx: r for r in ranges if r.end_confirmed_idx is not None}

    structures: dict[int, Structure] = {}
    cur: Structure | None = None

    def new(phase: str, reason: str, **kw: Any) -> Structure:
        s = Structure(sid=len(structures), phase=phase, reason=reason, **kw)
        structures[s.sid] = s
        return s

    def set_phase(s: Structure, phase: str, reason: str) -> None:
        s.phase, s.reason = phase, reason

    phase_col: list[str | None] = []
    sid_col: list[float] = []
    rid_col: list[float] = []
    reason_col: list[str] = []
    reclaim_dir: str | None = None    # chuỗi close ngoài biên sau SOS reclaim
    reclaim_run = 0

    for t in range(n):
        # 1. range thoát
        rng_exit = exit_at.get(t)
        if cur and rng_exit and cur.rng is not None and cur.rng.range_id == rng_exit.range_id:
            if rng_exit.exit_direction == "up":
                set_phase(cur, "E", f"TR#{rng_exit.range_id} thoát lên ({_v(df.index[t])})")
            elif cur.phase != "invalid":
                set_phase(cur, "invalid", f"TR#{rng_exit.range_id} thoát xuống ({_v(df.index[t])})")

        # 2. range xác nhận
        rng = conf_at.get(t)
        if rng is not None:
            if (
                cur and cur.phase in ("A", "B") and cur.sc is not None and cur.rng is None
                and _attach(cur.sc, rng, atr_ref[cur.sc.idx], cfg)
            ):
                cur.rng = rng
            else:
                cur = new("B", f"TR#{rng.range_id} xác nhận, không có SC ({_v(rng.confirmed_date)})", rng=rng)

        # 3. sự kiện xác nhận tại t
        for e in by_conf.get(t, []):
            same_range = cur is not None and cur.rng is not None and e.range_id == cur.rng.range_id
            if e.kind == EventType.SC:
                cur = new("A", f"SC {_v(e)}", sc=e)
                cur.events.append(e)
            elif cur is None:
                continue
            elif e.kind == EventType.SC_FAILED and cur.sc is not None and e.details.get("sc_date") == _d(cur.sc):
                cur.events.append(e)
                if cfg.sc_failed_invalidates:
                    set_phase(cur, "invalid", f"SC failed {_v(e)}")
                elif cur.phase == "A":
                    set_phase(cur, "A", f"SC {_v(cur.sc)}, thủng đáy SC {_v(e)}: vùng climax kéo dài, chờ SC mới")
            elif e.kind in (EventType.PS, EventType.AR, EventType.ST) and cur.sc is not None \
                    and e.details.get("sc_date") == _d(cur.sc) and cur.phase in ("A", "B"):
                cur.events.append(e)
                if e.kind == EventType.AR:
                    cur.ar = e
                if e.kind == EventType.ST and cur.phase == "A":
                    set_phase(cur, "B", f"ST {_v(e)}")
            elif e.kind in (EventType.SPRING, EventType.TEST) and same_range and cur.phase in ("A", "B", "C"):
                cur.events.append(e)
                if e.kind == EventType.SPRING:
                    if cur.spring is None or e.low < cur.spring.low:
                        cur.spring = e
                    if cur.phase != "C":
                        kind = SPRING_TYPE_LABEL.get(e.details.get("spring_type", ""), "")
                        set_phase(cur, "C", f"Spring ({kind}) {_v(e)}, xác nhận {_v(e.confirmed_date)}")
            elif e.kind == EventType.SOS and e.details.get("reclaim"):
                # Chỉ hồi sinh đúng cấu trúc vừa thoát xuống, chưa bị cấu trúc mới thay thế
                if same_range and cur.phase == "invalid":
                    cur.events.append(e)
                    cur.sos = e
                    reclaim_dir, reclaim_run = None, 0
                    set_phase(cur, "D", f"SOS reclaim {_v(e)}, sau khi TR#{e.range_id} thoát xuống {_v(pd.Timestamp(e.details['exit_date']))}")
            elif e.kind == EventType.SOS and same_range and cur.phase in ("A", "B", "C", "D"):
                cur.events.append(e)
                cur.sos = e
                if cur.phase != "D":
                    set_phase(cur, "D", f"SOS {_v(e)}")
            elif e.kind == EventType.LPS and same_range and cur.phase in ("D", "E"):
                cur.events.append(e)
                cur.lps = e
            elif e.kind == EventType.UTAD and same_range and cur.phase in ("A", "B", "C", "D"):
                cur.events.append(e)
                set_phase(cur, "invalid", f"UTAD {_v(e)}, xác nhận {_v(e.confirmed_date)}")

        # 4. kiểm tra giá: pha C vô hiệu khi thủng đáy Spring
        if cur and cur.phase == "C" and cur.spring is not None and not np.isnan(atr_ref[t]):
            if close[t] < cur.spring.details["lowest_low"] - cfg.spring_invalid_atr * atr_ref[t]:
                set_phase(cur, "invalid", f"close {vn_num(close[t])} thủng đáy Spring ({_v(df.index[t])})")

        # 5. sau SOS reclaim: range đã kết thúc, xét thoát lên / xuống theo biên cũ
        if cur and cur.phase == "D" and cur.sos is not None and cur.sos.details.get("reclaim") \
                and cur.sos.idx < t and cur.rng is not None and not np.isnan(atr[t]):
            thr = range_cfg.exit_atr * atr[t]
            side = "up" if close[t] > cur.rng.resistance + thr else "down" if close[t] < cur.rng.support - thr else None
            reclaim_run = reclaim_run + 1 if side is not None and side == reclaim_dir else (1 if side else 0)
            reclaim_dir = side
            if reclaim_run >= range_cfg.exit_bars:
                if side == "up":
                    set_phase(cur, "E", f"TR#{cur.rng.range_id} thoát lên sau SOS reclaim ({_v(df.index[t])})")
                else:
                    set_phase(cur, "invalid", f"SOS reclaim thất bại, close dưới support TR#{cur.rng.range_id} ({_v(df.index[t])})")

        phase_col.append(cur.phase if cur else None)
        sid_col.append(cur.sid if cur else np.nan)
        rid_col.append(cur.rng.range_id if cur and cur.rng else np.nan)
        reason_col.append(cur.reason if cur else "")

    series = pd.DataFrame(
        {"phase": phase_col, "structure_id": sid_col, "range_id": rid_col, "reason": reason_col}, index=df.index
    )
    return PhaseResult(series=series, segments=_segments(series), structures=structures)


def _segments(series: pd.DataFrame) -> list[PhaseSegment]:
    segs: list[PhaseSegment] = []
    key = list(zip(series["phase"], series["structure_id"].fillna(-1)))
    start = 0
    for i in range(1, len(key) + 1):
        if i == len(key) or key[i] != key[start]:
            ph = series["phase"].iloc[start]
            if not pd.isna(ph):
                rid = series["range_id"].iloc[i - 1]
                segs.append(PhaseSegment(
                    phase=ph, structure_id=int(series["structure_id"].iloc[start]),
                    range_id=None if np.isnan(rid) else int(rid),
                    start_idx=start, start_date=series.index[start], end_idx=i - 1, end_date=series.index[i - 1],
                    reason=series["reason"].iloc[start],
                ))
            start = i
    return segs


def _d_invalid_level(s: Structure, sup: float | None, res: float | None, atr: float,
                     cfg: PhaseConfig) -> tuple[float | None, str]:
    """Mức vô hiệu pha D theo `cfg.d_invalid_mode`.

    lps_or_res_atr: đáy LPS, chưa có LPS thì resistance - k ATR (v1, chặt)
    range_mid:      giữa range (support + resistance) / 2
    support:        support của range (gần như toàn bộ range)
    """
    mode = cfg.d_invalid_mode
    if mode not in D_INVALID_MODES:
        raise ValueError(f"phase.d_invalid_mode không hợp lệ: {mode!r}, chọn một trong {D_INVALID_MODES}")
    if mode == "lps_or_res_atr":
        if s.lps is not None:
            return s.lps.low, "Thủng đáy LPS"
        if res is None:
            return None, ""
        return res - cfg.d_invalid_atr * atr, f"Quay sâu vào range (resistance - {vn_g(cfg.d_invalid_atr)} ATR)"
    if sup is None or res is None:
        return None, ""
    if mode == "range_mid":
        return (sup + res) / 2, "Quay về giữa range"
    return sup, "Quay về support của range"


def current_phase(df: pd.DataFrame, phases: PhaseResult, cfg: Config | None = None) -> CurrentPhase:
    """Pha tại phiên cuối của `df`, kèm bằng chứng và mức xác nhận / vô hiệu tính sẵn bằng số."""
    cfg = cfg or Config()
    t = len(df) - 1
    date = df.index[t]
    atr = float(df["atr"].iloc[t])
    close = float(df["close"].iloc[t])
    vol_ma = float(df["vol_ma"].iloc[t])
    row = phases.series.iloc[t]
    if pd.isna(row["phase"]) or pd.isna(row["structure_id"]):
        return CurrentPhase(date, None, None, "chưa có cấu trúc", None, None, None, None, atr, [], [], [], [])
    s = phases.structures[int(row["structure_id"])]
    since = next((g.start_date for g in reversed(phases.segments) if g.structure_id == s.sid and g.phase == s.phase), None)

    if s.rng is not None:
        sup, res = s.rng.support, s.rng.resistance
    else:
        sup = s.sc.low if s.sc else None
        res = s.ar.high if s.ar else None
    tick = tick_size(sup if sup else close, cfg.data.exchange)
    sos_close = None if res is None else res + cfg.sos.min_breakout_atr * atr
    sos_rule = (
        f"close > {vn_num(sos_close)} (resistance + {vn_g(cfg.sos.min_breakout_atr)} ATR), nến tăng, "
        f"volume > {vn_int(cfg.sos.min_vol_ratio * vol_ma)} ({vn_g(cfg.sos.min_vol_ratio)}x TB20), "
        f"biên độ > {vn_g(cfg.sos.min_spread_atr)} ATR, close_pos >= {vn_g(cfg.sos.min_close_pos)}"
    ) if sos_close is not None else ""
    exit_dn = None if sup is None else sup - cfg.ranges.exit_atr * atr
    exit_up = None if res is None else res + cfg.ranges.exit_atr * atr

    confirm: list[Level] = []
    invalidate: list[Level] = []
    warnings: list[str] = []
    if s.phase == "A" and s.sc is not None:
        lo, hi = s.sc.low - cfg.st.band_below_atr * atr, s.sc.low + cfg.st.band_above_atr * atr
        confirm.append(Level("ST -> pha B", f"low trong [{vn_num(lo)}, {vn_num(hi)}], volume < {vn_int(cfg.st.max_vol_vs_sc * s.sc.volume)} "
                                          f"({vn_g(cfg.st.max_vol_vs_sc)}x volume SC), close >= {vn_num(s.sc.low)}", hi))
        lvl = s.sc.low - cfg.sc.fail_atr * atr
        rule = f"close < {vn_num(lvl)} (đáy SC - {vn_g(cfg.sc.fail_atr)} ATR) trước khi có AR"
        if cfg.phase.sc_failed_invalidates:
            invalidate.append(Level("SC failed", rule, lvl))
        else:
            invalidate.append(Level("Thủng đáy SC: vùng climax kéo dài (không phải vô hiệu)", rule + ", chờ SC mới", lvl))
    elif s.phase == "B":
        if sup is not None:
            pen = max(cfg.spring.min_penetration_atr * atr, cfg.spring.min_penetration_ticks * tick)
            confirm.append(Level("Spring -> pha C", f"low < {vn_num(sup - pen)} rồi trong {vn_g(cfg.spring.max_recovery_bars)} phiên close >= "
                                                   f"{vn_num(sup + cfg.spring.recovery_min_ticks * tick)} với close_pos >= {vn_g(cfg.spring.recovery_min_close_pos)}",
                                 sup - pen))
        if sos_close is not None:
            confirm.append(Level("SOS -> pha D", sos_rule, sos_close))
        if exit_dn is not None:
            invalidate.append(Level("Range thoát xuống", f"{vn_g(cfg.ranges.exit_bars)} phiên liên tiếp close < {vn_num(exit_dn)}", exit_dn))
    elif s.phase == "C" and s.spring is not None:
        if sos_close is not None:
            confirm.append(Level("SOS -> pha D", sos_rule, sos_close))
        lvl = s.spring.details["lowest_low"] - cfg.phase.spring_invalid_atr * atr
        invalidate.append(Level("Thủng đáy Spring", f"close < {vn_num(lvl)} (đáy Spring {vn_num(s.spring.details['lowest_low'])} - "
                                                    f"{vn_g(cfg.phase.spring_invalid_atr)} ATR)", lvl))
        pen = s.spring.details.get("penetration_atr")
        if pen is not None and pen >= cfg.phase.deep_spring_atr:
            warnings.append(f"Spring {vn_ts(s.spring.date)} xuyên sâu {vn_num(pen)} ATR dưới support "
                            f"(>= {vn_g(cfg.phase.deep_spring_atr)} ATR): nhóm Spring xuyên sâu có kết quả kém trong backtest")
    elif s.phase == "D":
        if exit_up is not None:
            confirm.append(Level("Thoát range -> pha E", f"{vn_g(cfg.ranges.exit_bars)} phiên liên tiếp close > {vn_num(exit_up)}", exit_up))
        lvl, label = _d_invalid_level(s, sup, res, atr, cfg.phase)
        if lvl is not None:
            invalidate.append(Level(label, f"close < {vn_num(lvl)}", lvl))
            if close < lvl:
                warnings.append(f"Close hiện tại {vn_num(close)} đã dưới mức {vn_num(lvl)}: SOS/LPS đang thất bại")
    elif s.phase == "E" and res is not None:
        invalidate.append(Level("Quay lại range", f"close < {vn_num(res)} (resistance cũ)", res))
        if close < res:
            warnings.append(f"Close hiện tại {vn_num(close)} đã quay lại dưới resistance cũ {vn_num(res)}")

    last_bar = df.iloc[t]
    if last_bar["close_pos"] <= 0.2 and last_bar["vol_ratio"] >= 1.2:
        warnings.append(f"Phiên cuối {vn_ts(date)} đóng cửa sát đáy (close_pos {vn_num(last_bar['close_pos'])}) "
                        f"với volume {vn_num(last_bar['vol_ratio'])}x TB20")
    return CurrentPhase(
        date=date, phase=s.phase, since=since, reason=s.reason,
        range_id=s.rng.range_id if s.rng else None, range_context=s.rng.context if s.rng else None,
        support=sup, resistance=res, atr=atr, evidence=[e.evidence() for e in s.events],
        confirm=confirm, invalidate=invalidate, warnings=warnings,
    )
