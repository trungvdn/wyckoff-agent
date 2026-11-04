"""Pha theo sơ đồ phân phối và SOW chuỗi khóa sàn: chuyển pha, chống look-ahead, chỉ ghi nhận."""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from wyckoff.agent.payload import build_payload
from wyckoff.agent.report import template_explanation
from wyckoff.agent.validate import validate_explanation
from wyckoff.config import DistributionConfig
from wyckoff.detectors.distribution import detect_sow
from wyckoff.detectors.events import _make_event
from wyckoff.detectors.models import EventType, TradingRange
from wyckoff.indicators.core import add_indicators
from wyckoff.indicators.limits import add_limit_flags
from wyckoff.phases_distribution import classify_distribution_phases, current_distribution_phase
from wyckoff.pipeline import analyze
from wyckoff.synthetic import SC_IDX, SOS_IDX, SPRING_IDX, make_wyckoff_accumulation, make_wyckoff_distribution
from wyckoff.web.viewmodel import stage_view


def flat(n: int = 120, c: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-02", periods=n, name="date")
    rows = [(c, c + 1, c - 1, c + (0.2 if i % 2 else -0.2), 1e6) for i in range(n)]
    return add_limit_flags(add_indicators(pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])))


def tr(df: pd.DataFrame, rid: int = 0, conf: int = 40, end: int | None = None, direction: str | None = None,
       sup: float = 99.0, res: float = 101.0) -> TradingRange:
    d = df.index
    last = end if end is not None else len(df) - 1
    return TradingRange(rid, 20, d[20], last, d[last], conf, d[conf], sup, res, 1.0, end, None if end is None else d[end],
                        direction)  # type: ignore[arg-type]


def ev(df: pd.DataFrame, kind: EventType, i: int, conf: int | None = None, rid: int | None = 0, **details):  # noqa: ANN003, ANN201
    return _make_event(df, kind, i, i if conf is None else conf, rid, dict(details))


def phase(res, t: int) -> str:  # noqa: ANN001
    return res.series["phase"].iloc[t]


# ------------------------------------------------------------------ chuyển pha

def test_full_sequence_a_to_e() -> None:
    df = flat()
    d = lambda i: f"{df.index[i]:%Y-%m-%d}"  # noqa: E731
    r = tr(df, conf=40, end=100, direction="down")
    bc = dataclasses.replace(ev(df, EventType.BC, 22, rid=None), high=101.0)
    dist = [bc, ev(df, EventType.AR_D, 28, 31, rid=None, bc_date=d(22)), ev(df, EventType.ST_D, 35, rid=None, bc_date=d(22)),
            ev(df, EventType.SOW, 80), ev(df, EventType.LPSY, 85, 88, sow_date=d(80))]
    up = [ev(df, EventType.UTAD, 60, 62, highest_high=102.0)]
    res = classify_distribution_phases(df, [r], dist, up)
    assert [phase(res, t) for t in (21, 22, 34, 35, 40, 59, 62, 79, 80, 99, 100)] == [None, "A", "A", "B", "B", "B", "C", "C", "D", "D", "E"]
    assert res.structures[0].rng is r and len(res.structures) == 1
    assert {e.kind for e in res.structures[0].events} >= {EventType.BC, EventType.ST_D, EventType.UTAD, EventType.SOW, EventType.LPSY}


def test_range_without_bc_opens_phase_b() -> None:
    df = flat()
    res = classify_distribution_phases(df, [tr(df)], [], [])
    assert phase(res, 39) is None or pd.isna(phase(res, 39))
    assert phase(res, 40) == "B" and "không có BC" in res.series["reason"].iloc[40]


def test_exit_up_invalidates() -> None:
    df = flat()
    res = classify_distribution_phases(df, [tr(df, end=60, direction="up")], [], [])
    assert phase(res, 60) == "invalid" and "thoát lên" in res.series["reason"].iloc[60]


def test_spring_does_not_invalidate() -> None:
    df = flat()
    res = classify_distribution_phases(df, [tr(df)], [], [ev(df, EventType.SPRING, 60)])
    assert phase(res, 70) == "B"


def test_phase_c_invalid_above_upthrust_high() -> None:
    df = flat()
    df.iloc[70, df.columns.get_loc("close")] = 110.0
    res = classify_distribution_phases(df, [tr(df)], [], [ev(df, EventType.UTAD, 60, 62, highest_high=102.0)])
    assert phase(res, 69) == "C" and phase(res, 70) == "invalid"


def test_bc_inside_active_range_attaches_when_near_resistance() -> None:
    df = flat()
    r = tr(df)
    near = dataclasses.replace(ev(df, EventType.BC, 50, rid=None), high=101.0)
    res = classify_distribution_phases(df, [r], [near, ev(df, EventType.SOW, 60)], [])
    assert phase(res, 50) == "A" and phase(res, 60) == "D"
    far = dataclasses.replace(ev(df, EventType.BC, 50, rid=None), high=130.0)
    res = classify_distribution_phases(df, [r], [far, ev(df, EventType.SOW, 60)], [])
    assert phase(res, 60) == "A"


def test_sow_on_exit_bar_recorded_keeps_e() -> None:
    df = flat()
    res = classify_distribution_phases(df, [tr(df, end=60, direction="down")], [ev(df, EventType.SOW, 60)], [])
    assert phase(res, 60) == "E" and res.structures[0].sow is not None


# ------------------------------------------------------------------ chuỗi tổng hợp, chống look-ahead

def test_demo_distribution_sequence() -> None:
    res = analyze(make_wyckoff_distribution())
    segs = [(g.phase, g.start_idx) for g in res.distribution_phases.segments]
    assert segs == [("A", SC_IDX), ("B", 113), ("C", SPRING_IDX + 1), ("D", SOS_IDX), ("E", 193)]
    cur = res.current_distribution_phase()
    assert cur.phase == "E" and EventType.SOW in {e.kind for e in cur.events}


def test_accumulation_demo_invalidates_distribution_track() -> None:
    res = analyze(make_wyckoff_accumulation())
    assert res.distribution_phases.series["phase"].iloc[-1] == "invalid"
    assert res.phases.series["phase"].iloc[-1] == "E"


@pytest.mark.parametrize("make", [make_wyckoff_distribution, make_wyckoff_accumulation])
def test_no_lookahead(make) -> None:  # noqa: ANN001
    raw = make()
    full = analyze(raw).distribution_phases.series
    for cut in (100, 130, 178, 192, 196, 205):
        part = analyze(raw.iloc[:cut]).distribution_phases.series
        pd.testing.assert_frame_equal(part, full.iloc[:cut])


def test_since_keeps_current(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    cut = res.since(ohlcv.index[150])
    assert len(cut.distribution_phases.series) == len(cut.df)
    assert cut.current_distribution_phase() == res.current_distribution_phase()


# ------------------------------------------------------------------ SOW chuỗi khóa sàn

def _floor_frame(locks: int, vol: float = 0.2) -> tuple[pd.DataFrame, TradingRange]:
    rows, c = [], 100.0
    for i in range(80):
        rows.append((c, c + 1, c - 1, c + (0.2 if i % 2 else -0.2), 1e6))
    p = 100.0
    for _ in range(locks):
        nxt = round(p * 0.93, 2)
        rows.append((nxt, nxt, nxt, nxt, vol * 1e6))
        p = nxt
    rows += [(p, p + 0.3, p - 0.3, p, 1e6)] * 3
    idx = pd.bdate_range("2023-01-02", periods=len(rows), name="date")
    df = add_limit_flags(add_indicators(pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])))
    return df, tr(df, conf=40, sup=99.0, res=101.0)


def test_single_floor_lock_is_not_sow() -> None:
    df, r = _floor_frame(1)
    assert bool(df["floor_locked"].iloc[80]) and detect_sow(df, [r]) == []


def test_floor_chain_is_sow_once_without_volume() -> None:
    df, r = _floor_frame(4)
    sow = detect_sow(df, [r])
    assert [e.idx for e in sow] == [81] and sow[0].details["form"] == "floor_chain" and sow[0].vol_ratio < 1


def test_floor_chain_can_be_disabled() -> None:
    df, r = _floor_frame(4)
    assert detect_sow(df, [r], DistributionConfig(sow_floor_chain_min_days=99)) == []


def test_floor_chain_needs_close_below_support() -> None:
    df, r = _floor_frame(4)
    low = dataclasses.replace(r, support=10.0, resistance=12.0)
    assert detect_sow(df, [low]) == []


# ------------------------------------------------------------------ chỉ ghi nhận, payload, view

def test_payload_only_while_in_range() -> None:
    raw = make_wyckoff_distribution()
    inside = build_payload(analyze(raw.iloc[:150]), "X")["current_stage"]
    assert inside["range_id"] is not None and inside["distribution_phase"]["phase"] in ("A", "B", "C", "D")
    assert build_payload(analyze(raw), "X")["current_stage"]["distribution_phase"] is None


def test_template_with_distribution_phase_passes_validator() -> None:
    p = build_payload(analyze(make_wyckoff_distribution().iloc[:150]), "X")
    t = template_explanation(p)
    assert "Theo sơ đồ phân phối: pha" in t["summary"] and validate_explanation(t, p) == []


def test_stage_view_has_distribution_steps() -> None:
    p = build_payload(analyze(make_wyckoff_distribution().iloc[:150]), "X")
    v = stage_view(p["current_stage"], p["stage_history"])["distribution_phase"]
    assert v["title"].startswith("Pha ") and sum(s["status"] == "current" for s in v["steps"]) == 1


def test_current_without_structure() -> None:
    df = flat(10)
    res = classify_distribution_phases(df, [], [], [])
    cur = current_distribution_phase(res)
    assert cur.phase is None and cur.reason == "chưa có cấu trúc" and np.isnan(res.series["range_id"].iloc[-1])
