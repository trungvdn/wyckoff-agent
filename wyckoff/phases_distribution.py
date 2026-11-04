"""Pha theo sơ đồ phân phối: state machine causal chạy song song với `wyckoff.phases`. Chỉ ghi nhận: không đổi pha tích lũy,
điểm tin cậy hay backtest. Mỗi range được theo dõi theo cả hai sơ đồ, vì chưa biết là giả thuyết nào cho đến khi range thoát.

Duyệt từng phiên t; thứ tự xử lý: range thoát -> range xác nhận -> sự kiện có `confirmed_idx == t` -> kiểm tra giá.

    A  BC xác nhận                        -> B khi có ST(d)
    B  ST(d), hoặc range xác nhận không BC -> C khi UT / UTAD, -> D khi SOW
    C  UT / UTAD                          -> D khi SOW
    D  SOW (LPSY ghi nhận)                -> E khi range thoát xuống
    E  range thoát xuống
    invalid: range thoát lên; pha C có close > đỉnh upthrust + k ATR (k = phase.spring_invalid_atr)

Khác phía tích lũy: Spring không vô hiệu cấu trúc phân phối (H6: vô hiệu ngay khi có sự kiện ngược chiều không có căn cứ);
không có "SOS reclaim" đối xứng; BC xuất hiện khi range đang hoạt động thì gắn vào range đó nếu đỉnh BC gần resistance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.config import PhaseConfig
from wyckoff.detectors.models import Event, EventType, TradingRange
from wyckoff.fmt import vn_num, vn_ts
from wyckoff.phases import PhaseResult, _segments

_ORDER = {
    EventType.BC: 0, EventType.BC_FAILED: 1, EventType.AR_D: 2, EventType.ST_D: 3,
    EventType.UT: 4, EventType.UTAD: 4, EventType.SOW: 5, EventType.LPSY: 6,
}


@dataclass
class DistStructure:
    """Một cấu trúc phân phối đang được theo dõi."""
    sid: int
    phase: str
    reason: str
    bc: Event | None = None
    rng: TradingRange | None = None
    upthrust_high: float | None = None
    sow: Event | None = None
    events: list[Event] = field(default_factory=list)


@dataclass(frozen=True)
class CurrentDistributionPhase:
    date: pd.Timestamp
    phase: str | None
    since: pd.Timestamp | None
    reason: str
    range_id: int | None
    events: tuple[Event, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase, "since": None if self.since is None else f"{self.since:%Y-%m-%d}", "reason": self.reason,
                "range_id": self.range_id,
                "events": [{"kind": e.kind.value, "date": f"{e.date:%Y-%m-%d}", "confirmed_date": f"{e.confirmed_date:%Y-%m-%d}",
                            "vol_ratio": round(e.vol_ratio, 2), "form": e.details.get("form")} for e in self.events]}


def _attach(bc: Event, rng: TradingRange, atr: float, cfg: PhaseConfig) -> bool:
    return abs(bc.idx - rng.start_idx) <= cfg.attach_max_bars and abs(bc.high - rng.resistance) <= cfg.attach_max_atr * atr


def classify_distribution_phases(df: pd.DataFrame, ranges: list[TradingRange], distribution: list[Event], events: list[Event],
                                 cfg: PhaseConfig | None = None) -> PhaseResult:
    """`distribution`: `result.distribution`; `events`: `result.events` (lấy UT / UTAD)."""
    cfg = cfg or PhaseConfig()
    n = len(df)
    close = df["close"].to_numpy(dtype=float)
    atr_ref = df["atr_ref"].to_numpy(dtype=float)
    by_conf: dict[int, list[Event]] = {}
    for e in distribution + [e for e in events if e.kind in (EventType.UT, EventType.UTAD)]:
        by_conf.setdefault(e.confirmed_idx, []).append(e)
    for lst in by_conf.values():
        lst.sort(key=lambda e: (_ORDER.get(e.kind, 99), e.idx))
    conf_at = {r.confirmed_idx: r for r in ranges}
    exit_at = {r.end_confirmed_idx: r for r in ranges if r.end_confirmed_idx is not None}

    structures: dict[int, DistStructure] = {}
    cur: DistStructure | None = None
    active: TradingRange | None = None

    def new(phase: str, reason: str, **kw: Any) -> DistStructure:
        s = DistStructure(len(structures), phase, reason, **kw)
        structures[s.sid] = s
        return s

    phase_col: list[str | None] = []
    sid_col: list[float] = []
    rid_col: list[float] = []
    reason_col: list[str] = []

    for t in range(n):
        ended = exit_at.get(t)
        if ended is not None:
            if active is not None and active.range_id == ended.range_id:
                active = None
            if cur is not None and cur.rng is not None and cur.rng.range_id == ended.range_id:
                if ended.exit_direction == "down":
                    cur.phase, cur.reason = "E", f"TR#{ended.range_id} thoát xuống ({vn_ts(df.index[t])})"
                else:
                    cur.phase, cur.reason = "invalid", f"TR#{ended.range_id} thoát lên ({vn_ts(df.index[t])})"

        rng = conf_at.get(t)
        if rng is not None:
            active = rng
            if cur is not None and cur.phase in ("A", "B") and cur.bc is not None and cur.rng is None \
                    and _attach(cur.bc, rng, atr_ref[cur.bc.idx], cfg):
                cur.rng = rng
            else:
                cur = new("B", f"TR#{rng.range_id} xác nhận, không có BC ({vn_ts(rng.confirmed_date)})", rng=rng)

        for e in by_conf.get(t, []):
            if e.kind == EventType.BC:
                near = active is not None and abs(e.high - active.resistance) <= cfg.attach_max_atr * atr_ref[e.idx]
                cur = new("A", f"BC {vn_ts(e.date)}", bc=e, rng=active if near else None)
                cur.events.append(e)
                continue
            if cur is None:
                continue
            same_range = cur.rng is not None and e.range_id == cur.rng.range_id
            same_bc = cur.bc is not None and e.details.get("bc_date") == f"{cur.bc.date:%Y-%m-%d}"
            if e.kind == EventType.BC_FAILED and same_bc:
                cur.events.append(e)
                if cur.phase == "A":
                    cur.reason = f"BC {vn_ts(cur.bc.date)}, vượt đỉnh BC {vn_ts(e.date)}: vùng climax kéo dài, chờ BC mới"
            elif e.kind in (EventType.AR_D, EventType.ST_D) and same_bc and cur.phase in ("A", "B"):
                cur.events.append(e)
                if e.kind == EventType.ST_D and cur.phase == "A":
                    cur.phase, cur.reason = "B", f"ST(d) {vn_ts(e.date)}"
            elif e.kind in (EventType.UT, EventType.UTAD) and same_range and cur.phase in ("A", "B", "C"):
                cur.events.append(e)
                top = e.details.get("highest_high", e.high)
                cur.upthrust_high = top if cur.upthrust_high is None else max(cur.upthrust_high, top)
                if cur.phase != "C":
                    cur.phase, cur.reason = "C", f"{e.kind.value} {vn_ts(e.date)}, xác nhận {vn_ts(e.confirmed_date)}"
            elif e.kind == EventType.SOW and same_range and cur.phase in ("A", "B", "C", "D"):
                cur.events.append(e)
                cur.sow = e
                if cur.phase != "D":
                    cur.phase, cur.reason = "D", f"SOW {vn_ts(e.date)}"
            elif e.kind == EventType.SOW and same_range and cur.phase == "E" and cur.sow is None:
                cur.events.append(e)        # SOW cùng phiên range thoát xuống: ghi bằng chứng, giữ pha E
                cur.sow = e
            elif e.kind == EventType.LPSY and same_range and cur.phase in ("D", "E"):
                cur.events.append(e)

        if cur is not None and cur.phase == "C" and cur.upthrust_high is not None and not np.isnan(atr_ref[t]) \
                and close[t] > cur.upthrust_high + cfg.spring_invalid_atr * atr_ref[t]:
            cur.phase, cur.reason = "invalid", f"close {vn_num(close[t])} vượt đỉnh upthrust ({vn_ts(df.index[t])})"

        phase_col.append(cur.phase if cur else None)
        sid_col.append(cur.sid if cur else np.nan)
        rid_col.append(cur.rng.range_id if cur and cur.rng else np.nan)
        reason_col.append(cur.reason if cur else "")

    series = pd.DataFrame({"phase": phase_col, "structure_id": sid_col, "range_id": rid_col, "reason": reason_col}, index=df.index)
    return PhaseResult(series=series, segments=_segments(series), structures=structures)  # type: ignore[arg-type]


def current_distribution_phase(phases: PhaseResult) -> CurrentDistributionPhase:
    row = phases.series.iloc[-1]
    date = phases.series.index[-1]
    if pd.isna(row["phase"]) or pd.isna(row["structure_id"]):
        return CurrentDistributionPhase(date, None, None, "chưa có cấu trúc", None, ())
    s = phases.structures[int(row["structure_id"])]
    since = next((g.start_date for g in reversed(phases.segments) if g.structure_id == s.sid and g.phase == s.phase), None)
    return CurrentDistributionPhase(date, s.phase, since, s.reason, s.rng.range_id if s.rng else None,
                                    tuple(e for e in s.events if e.confirmed_idx >= 0))
