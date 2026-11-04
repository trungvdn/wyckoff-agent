"""H8: điểm bằng chứng của range: trọng số, ngưỡng, đổi chiều, vô hiệu, chống look-ahead."""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from wyckoff.detectors.models import EventStatus, EventType, StatusChange
from wyckoff.evidence import ACC, DIST, WEIGHTS_A, WEIGHTS_B, evidence, evidence_for_range, range_events
from wyckoff.pipeline import analyze
from wyckoff.synthetic import make_wyckoff_accumulation, make_wyckoff_distribution


@pytest.fixture
def acc():  # noqa: ANN201
    return analyze(make_wyckoff_accumulation())


@pytest.fixture
def dist():  # noqa: ANN201
    return analyze(make_wyckoff_distribution())


def with_events(res, evs):  # noqa: ANN001, ANN201
    return dataclasses.replace(res, events=evs, distribution=[])


def fake(res, kind: EventType, t: int, rid: int, invalid: int | None = None, **details):  # noqa: ANN001, ANN003, ANN201
    base = res.events[0]
    d = res.df.index
    hist = (StatusChange(EventStatus.CONFIRMED, t, d[t]),) + (
        (StatusChange(EventStatus.INVALIDATED, invalid, d[invalid]),) if invalid is not None else ())
    return dataclasses.replace(base, kind=kind, idx=t, date=d[t], confirmed_idx=t, confirmed_date=d[t], range_id=rid,
                               history=hist, details=dict(details))


def test_weights_table_matches_preregistration() -> None:
    assert {k.value: v for k, v in WEIGHTS_A.items()} == {
        "SC": 1, "ST": 1, "Spring": 1, "Test": 1, "BC": -1, "ST(d)": -1, "UT": -1, "UTAD": -1}
    extra = {k.value: v for k, v in WEIGHTS_B.items() if k not in WEIGHTS_A}
    assert extra == {"SOS": 2, "LPS": 1, "SOW": -2, "LPSY": -1}


def test_threshold_and_flips(acc) -> None:  # noqa: ANN001
    r = acc.ranges[0]
    t0 = r.confirmed_idx + 2
    res = with_events(acc, [fake(acc, EventType.SPRING, t0, r.range_id), fake(acc, EventType.TEST, t0 + 5, r.range_id),
                            fake(acc, EventType.UTAD, t0 + 10, r.range_id), fake(acc, EventType.UTAD, t0 + 12, r.range_id),
                            fake(acc, EventType.UTAD, t0 + 14, r.range_id), fake(acc, EventType.UTAD, t0 + 16, r.range_id)])
    res = dataclasses.replace(res, phases=dataclasses.replace(res.phases, structures={}))
    ev = evidence_for_range(res, r, "h8a")
    at = lambda t: ev.states[t - ev.start]  # noqa: E731
    assert at(t0) is None and at(t0 + 5) == ACC and at(t0 + 10) is None and at(t0 + 14) is None and at(t0 + 16) == DIST
    assert [(t, s) for t, s, _ in ev.flips] == [(t0 + 5, ACC), (t0 + 16, DIST)]
    assert ev.first_of(DIST) == t0 + 16 and ev.final_state == DIST


def test_invalidated_event_stops_counting(acc) -> None:  # noqa: ANN001
    r = acc.ranges[0]
    t0 = r.confirmed_idx + 2
    res = with_events(acc, [fake(acc, EventType.SPRING, t0, r.range_id, invalid=t0 + 8), fake(acc, EventType.TEST, t0 + 1, r.range_id)])
    res = dataclasses.replace(res, phases=dataclasses.replace(res.phases, structures={}))
    ev = evidence_for_range(res, r, "h8a")
    assert ev.states[t0 + 1 - ev.start] == ACC and ev.states[t0 + 8 - ev.start] is None


def test_h8a_ignores_breakout_events(acc) -> None:  # noqa: ANN001
    r = acc.ranges[0]
    t0 = r.confirmed_idx + 2
    res = with_events(acc, [fake(acc, EventType.SOS, t0, r.range_id)])
    res = dataclasses.replace(res, phases=dataclasses.replace(res.phases, structures={}))
    assert evidence_for_range(res, r, "h8a").flips == ()
    assert [s for _, s, _ in evidence_for_range(res, r, "h8b").flips] == [ACC]


def test_reclaim_sos_not_counted(acc) -> None:  # noqa: ANN001
    r = acc.ranges[0]
    res = with_events(acc, [fake(acc, EventType.SOS, r.confirmed_idx + 2, r.range_id, reclaim=True)])
    res = dataclasses.replace(res, phases=dataclasses.replace(res.phases, structures={}))
    assert range_events(res, r, "h8b") == []


def test_window_stops_before_exit(acc) -> None:  # noqa: ANN001
    r = acc.ranges[0]
    ev = evidence_for_range(acc, r, "h8b")
    assert ev.start == r.confirmed_idx and len(ev.scores) == r.end_confirmed_idx - r.confirmed_idx


def test_demo_accumulation_leans_acc_before_exit(acc) -> None:  # noqa: ANN001
    ev = evidence(acc, "h8a")[0]
    assert ev.final_state == ACC and ev.first_of(ACC) < acc.ranges[0].end_confirmed_idx
    kinds = {e.kind for e in range_events(acc, acc.ranges[0], "h8a")}
    assert {EventType.SC, EventType.ST, EventType.SPRING} <= kinds


def test_demo_distribution_leans_dist(dist) -> None:  # noqa: ANN001
    ev = evidence(dist, "h8a")[0]
    assert ev.final_state == DIST
    assert {EventType.BC, EventType.ST_D, EventType.UTAD} <= {e.kind for e in range_events(dist, dist.ranges[0], "h8a")}
    assert evidence(dist, "h8b")[0].scores[-1] < evidence(dist, "h8a")[0].scores[-1]     # SOW -2


@pytest.mark.parametrize("make", [make_wyckoff_accumulation, make_wyckoff_distribution])
@pytest.mark.parametrize("mode", ["h8a", "h8b"])
def test_no_lookahead_demo(make, mode: str) -> None:  # noqa: ANN001
    raw = make()
    full = evidence(analyze(raw), mode)
    for cut in (135, 160, 178, 192):
        part = evidence(analyze(raw.iloc[:cut]), mode)
        assert len(part) == 1
        n = len(part[0].scores)
        assert part[0].scores == full[0].scores[:n]
        assert part[0].flips == tuple(f for f in full[0].flips if f[0] < cut)


def _noisy(seed: int, n: int = 1200) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 400 + np.cumsum(rng.normal(0, 1.2, n) + 0.8 * np.sin(np.arange(n) / 35))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.exponential(0.8, n)
    low = np.minimum(open_, close) - rng.exponential(0.8, n)
    vol = 1e6 * rng.lognormal(0, 0.45, n) * (1 + 3 * (rng.random(n) < 0.05))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol},
                        index=pd.bdate_range("2015-01-01", periods=n, name="date"))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_lookahead_noisy(seed: int) -> None:
    raw = _noisy(seed)
    full = {e.range_id: e for e in evidence(analyze(raw), "h8b")}
    assert full
    compared = 0
    for cut in (500, 800, 1100):
        for p in evidence(analyze(raw.iloc[:cut]), "h8b"):
            n = len(p.scores)
            assert p.scores == full[p.range_id].scores[:n]
            compared += n
    assert compared > 100
