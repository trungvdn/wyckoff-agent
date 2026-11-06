"""Sự kiện phía phân phối: đối xứng với phía tích lũy (lật giá), quy tắc VN của BC, vòng đời, chống look-ahead, chỉ ghi nhận."""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from wyckoff.agent.payload import build_payload
from wyckoff.config import ARConfig, Config, DistributionConfig, LPSConfig, SellingClimaxConfig, SOSConfig, STConfig
from wyckoff.detectors.distribution import detect_ar_d, detect_buying_climax, detect_lpsy, detect_sow, detect_st_d
from wyckoff.detectors.events import detect_selling_climax, detect_sos
from wyckoff.detectors.models import Event, EventStatus, EventType, TradingRange
from wyckoff.detectors.structure import detect_ar, detect_lps, detect_st
from wyckoff.indicators.core import add_indicators
from wyckoff.indicators.limits import add_limit_flags
from wyckoff.pipeline import analyze
from wyckoff.synthetic import SC_IDX, SOS_IDX, make_wyckoff_accumulation, make_wyckoff_distribution, mirror_prices


def noisy(seed: int, n: int = 1500, level: float = 800.0) -> pd.DataFrame:
    """Chuỗi xen kẽ đi ngang và xu hướng, có phiên đột biến volume cả hai chiều, đủ sự kiện để so đối xứng.
    Biên độ cộng và giá dương cả khi lật quanh `level`."""
    rng = np.random.default_rng(seed)
    rows, c, i = [], level / 2, 0
    while i < n:
        length, sideways = int(rng.integers(50, 130)), rng.random() < 0.6
        center, drift = c, 0.0 if sideways else rng.choice([-0.35, 0.35])
        for k in range(length):
            prev = c
            spike = rng.random() < 0.06
            if spike:
                side = rng.choice([-1, 1])
                c = prev + side * rng.uniform(1.5, 6)
                lo, hi = min(prev, c) - rng.uniform(0, 0.3), max(prev, c) + rng.uniform(0, 0.3)
                vol = rng.uniform(2.2, 5)
            else:
                pull = 0.12 * (center - prev) if sideways else drift
                c = prev + pull + rng.normal(0, 0.6)
                lo, hi = min(prev, c) - rng.exponential(0.5), max(prev, c) + rng.exponential(0.5)
                vol = rng.lognormal(-0.25, 0.3)
            rows.append((prev, hi, lo, c, 1e6 * vol))
        i += length
    idx = pd.bdate_range("2012-01-02", periods=len(rows), name="date")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"]).iloc[:n]


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    return add_limit_flags(add_indicators(df))


def flip_ranges(ranges: list[TradingRange], level: float) -> list[TradingRange]:
    return [dataclasses.replace(r, support=level - r.resistance, resistance=level - r.support) for r in ranges]


MIRROR_CFG = DistributionConfig(bc_exclude_ceiling_locked=False, sow_floor_chain_min_days=99)
LEVEL = 800.0
SEEDS = range(1, 13)


# ------------------------------------------------------------------ đối xứng: lật giá thì trùng phiên

def test_sow_lpsy_mirror_sos_lps() -> None:
    n_sos = n_lps = 0
    for seed in SEEDS:
        raw = noisy(seed)
        res = analyze(raw)
        df, flipped = res.df, prepare(mirror_prices(raw, LEVEL))
        sos = detect_sos(df, res.ranges, SOSConfig())
        sow = detect_sow(flipped, flip_ranges(res.ranges, LEVEL), MIRROR_CFG)
        assert [e.idx for e in sos] == [e.idx for e in sow]
        lps = detect_lps(df, res.ranges, sos, LPSConfig())
        lpsy = detect_lpsy(flipped, flip_ranges(res.ranges, LEVEL), sow, MIRROR_CFG)
        assert [(e.idx, e.confirmed_idx) for e in lps] == [(e.idx, e.confirmed_idx) for e in lpsy]
        n_sos, n_lps = n_sos + len(sos), n_lps + len(lps)
    assert n_sos >= 20 and n_lps >= 5      # test phải có sự kiện để so


def test_ar_st_mirror_when_anchored_on_same_climax() -> None:
    n_ar = n_st = 0
    for seed in SEEDS:
        raw = noisy(seed)
        df, flipped = prepare(raw), prepare(mirror_prices(raw, LEVEL))
        sc = detect_selling_climax(df, SellingClimaxConfig(min_decline=0.0, require_below_sma=False, lowest_low_lookback=30))

        def as_bc(e: Event) -> Event:
            kind = EventType.BC if e.kind == EventType.SC else EventType.BC_FAILED
            details = {k.replace("sc_", "bc_"): v for k, v in e.details.items()}
            return dataclasses.replace(e, kind=kind, high=float(LEVEL - e.low), low=float(LEVEL - e.high), details=details)

        bc = [as_bc(e) for e in sc]
        ar, ar_d = detect_ar(df, sc, ARConfig()), detect_ar_d(flipped, bc, MIRROR_CFG)
        assert [(e.idx, e.confirmed_idx) for e in ar] == [(e.idx, e.confirmed_idx) for e in ar_d]
        st, st_d = detect_st(df, sc, ar, STConfig()), detect_st_d(flipped, bc, ar_d, MIRROR_CFG)
        assert [(e.idx, e.confirmed_idx) for e in st] == [(e.idx, e.confirmed_idx) for e in st_d]
        n_ar, n_st = n_ar + len(ar), n_st + len(st)
    assert n_ar >= 10 and n_st >= 5


def test_bc_mirrors_sc_shape_when_pct_conditions_removed() -> None:
    n = 0
    for seed in SEEDS:
        raw = noisy(seed)
        df, flipped = prepare(raw), prepare(mirror_prices(raw, LEVEL))
        sc_cfg = SellingClimaxConfig(min_decline=-1.0, floor_chain_min_days=99)
        bc_cfg = DistributionConfig(bc_min_rise=-1.0, ceiling_chain_min_days=99, bc_exclude_ceiling_locked=False)
        sc = detect_selling_climax(df, sc_cfg)
        bc = detect_buying_climax(flipped, bc_cfg)
        pick = lambda ev, k: [(e.idx, e.confirmed_idx) for e in ev if e.kind == k]  # noqa: E731
        assert pick(sc, EventType.SC) == pick(bc, EventType.BC)
        assert pick(sc, EventType.SC_FAILED) == pick(bc, EventType.BC_FAILED)
        n += len(pick(sc, EventType.SC))
    assert n >= 8


# ------------------------------------------------------------------ chuỗi tổng hợp

@pytest.fixture
def dist() -> pd.DataFrame:
    return make_wyckoff_distribution()


def test_demo_sequence(dist: pd.DataFrame) -> None:
    res = analyze(dist)
    by = {k: [e for e in res.distribution if e.kind == k] for k in EventType}
    assert [e.idx for e in by[EventType.BC]] == [SC_IDX]
    assert by[EventType.BC][0].high == pytest.approx(86.0)
    assert by[EventType.AR_D] and by[EventType.AR_D][0].idx > SC_IDX
    assert [e.idx for e in by[EventType.SOW]] == [SOS_IDX]
    assert by[EventType.SOW][0].close < 76.0
    assert res.current_stage().stage == "Markdown"
    label = res.stages.ranges[-1]
    assert label.exit_direction == "down" and label.stage == "Distribution" and label.prior_stage == "Markup"


def test_mirrored_chain_on_real_shape_matches_accumulation_counts() -> None:
    acc = analyze(make_wyckoff_accumulation())
    dis = analyze(make_wyckoff_distribution())
    n = lambda res, k: sum(e.kind == k for e in res)  # noqa: E731
    assert n(acc.events, EventType.SOS) == n(dis.distribution, EventType.SOW)
    assert n(acc.events, EventType.SC) == n(dis.distribution, EventType.BC)
    assert n(acc.events, EventType.AR) == n(dis.distribution, EventType.AR_D)


# ------------------------------------------------------------------ BC: quy tắc riêng

def _rally(n: int = 100, start: float = 50.0, step: float = 0.5) -> list[tuple[float, float, float, float, float]]:
    rows, prev = [], start
    for i in range(n):
        c = start + step * (i + 1)
        rows.append((prev, c + 0.6, prev - 0.2, c, 1e6))
        prev = c
    return rows


def _frame(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    idx = pd.bdate_range("2022-01-03", periods=len(rows), name="date")
    return prepare(pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"]))


def _kinds(events, kind=EventType.BC):  # noqa: ANN001, ANN201
    return [e for e in events if e.kind == kind]


def test_bc_same_bar_when_close_low() -> None:
    c = 100.0
    df = _frame(_rally() + [(c, c + 5, c - 0.5, c + 0.5, 4e6)])
    bc = _kinds(detect_buying_climax(df))
    assert [e.idx for e in bc] == [100] and bc[0].details["confirmation"] == "same_bar"


def test_bc_zone_confirms_on_reversal_not_before() -> None:
    c = 100.0
    climax = (c, c + 5, c - 0.2, c + 4.6, 4e6)
    assert not _kinds(detect_buying_climax(_frame(_rally() + [climax])))
    df = _frame(_rally() + [climax, (c + 4.6, c + 4.7, c + 1, c + 1.5, 1e6)])
    bc = _kinds(detect_buying_climax(df))
    assert [(e.idx, e.confirmed_idx) for e in bc] == [(100, 101)] and bc[0].details["confirmation"] == "zone"


def test_bc_zone_cancelled_by_new_high() -> None:
    c = 100.0
    climax = (c, c + 5, c - 0.2, c + 4.6, 4e6)
    df = _frame(_rally() + [climax, (c + 4.6, c + 6, c + 1, c + 1.5, 1e6)])
    assert 100 not in [e.idx for e in _kinds(detect_buying_climax(df))]


def test_bc_needs_min_rise() -> None:
    c = 100.0
    df = _frame(_rally() + [(c, c + 5, c - 0.5, c + 0.5, 4e6)])
    assert _kinds(detect_buying_climax(df, DistributionConfig(bc_min_rise=0.30)))
    assert not _kinds(detect_buying_climax(df, DistributionConfig(bc_min_rise=2.0)))


def test_ceiling_locked_bar_is_not_climax_unless_disabled() -> None:
    c = 100.0
    locked = (c, c * 1.07, c, c * 1.07, 4e6)
    reversal = (c * 1.07, c * 1.07, c * 1.0, c * 1.01, 1e6)
    df = _frame(_rally() + [locked, reversal])
    assert bool(df["ceiling_locked"].iloc[100])
    assert not _kinds(detect_buying_climax(df))
    assert [e.idx for e in _kinds(detect_buying_climax(df, DistributionConfig(bc_exclude_ceiling_locked=False)))] == [100]


def test_ceiling_chain_confirms_on_rollover() -> None:
    rows = _rally()
    p = rows[-1][3]
    for _ in range(3):
        rows.append((p, p * 1.07, p, p * 1.07, 1e6))
        p *= 1.07
    rows.append((p, p * 1.02, p * 0.99, p * 0.995, 5e6))
    df = _frame(rows)
    bc = _kinds(detect_buying_climax(df))
    assert [e.idx for e in bc] == [103] and bc[0].details["confirmation"] == "ceiling_chain"


def test_bc_failed_on_close_above_high_before_reaction() -> None:
    c = 100.0
    rows = _rally() + [(c, c + 5, c - 0.5, c + 0.5, 4e6)]
    p = c + 0.5
    for _ in range(6):
        rows.append((p, p + 2.2, p - 0.1, p + 2, 1e6))
        p += 2
    events = detect_buying_climax(_frame(rows))
    failed = _kinds(events, EventType.BC_FAILED)
    assert failed and failed[0].details["bc_date"] == events[0].date.strftime("%Y-%m-%d")


def test_cooldown_keeps_only_higher_high() -> None:
    c = 100.0
    first = (c, c + 5, c - 0.5, c + 0.5, 4e6)
    lower = (c + 0.5, c + 4, c - 1, c, 4e6)
    assert len(_kinds(detect_buying_climax(_frame(_rally() + [first, lower])))) == 1


# ------------------------------------------------------------------ vòng đời

def test_lifecycle_ids_relations_and_invalidation(dist: pd.DataFrame) -> None:
    res = analyze(dist)
    ids = [e.event_id for e in res.distribution]
    assert len(ids) == len(set(ids)) and all(ids)
    bc = next(e for e in res.distribution if e.kind == EventType.BC)
    ar = next(e for e in res.distribution if e.kind == EventType.AR_D)
    assert ar.event_id in bc.related_event_ids and bc.event_id in ar.related_event_ids
    assert ar.event_id.startswith("ARD-") and f"BC{bc.date:%Y%m%d}" in ar.event_id
    assert bc.status == EventStatus.CONFIRMED


def test_sow_invalidated_when_close_back_above_mid(dist: pd.DataFrame) -> None:
    tail = dist.iloc[-1]
    p = float(tail["close"])
    extra = []
    for _ in range(12):
        extra.append((p, p + 2.5, p - 0.2, p + 2.2, 1e6))
        p += 2.2
    idx = pd.bdate_range(dist.index[-1] + pd.offsets.BDay(), periods=len(extra), name="date")
    longer = pd.concat([dist, pd.DataFrame(extra, index=idx, columns=dist.columns)])
    sow = next(e for e in analyze(longer).distribution if e.kind == EventType.SOW)
    assert sow.status == EventStatus.INVALIDATED and "breakdown thất bại" in sow.invalidated.reason


# ------------------------------------------------------------------ chống look-ahead

@pytest.mark.parametrize("seed", [1, 2, 5])
def test_no_lookahead(seed: int) -> None:
    raw = noisy(seed)
    full = analyze(raw).distribution
    assert len(full) >= 3 or seed != 1
    for cut in (400, 700, 1000, 1300):
        part = analyze(raw.iloc[:cut]).distribution
        want = {(e.kind, e.idx, e.confirmed_idx) for e in full if e.confirmed_idx < cut}
        assert {(e.kind, e.idx, e.confirmed_idx) for e in part} == want
        for e in part:
            f = next(x for x in full if (x.kind, x.idx) == (e.kind, e.idx))
            assert e.event_id == f.event_id and e.status == f.status_at(cut - 1)


# ------------------------------------------------------------------ chỉ ghi nhận

def test_distribution_is_record_only(dist: pd.DataFrame) -> None:
    res = analyze(dist)
    assert res.distribution
    new_kinds = {EventType.BC, EventType.BC_FAILED, EventType.AR_D, EventType.ST_D, EventType.SOW, EventType.LPSY}
    assert not {e.kind for e in res.events + res.candidates} & new_kinds
    assert not {s.kind for s in res.phases.structures.values() for s in s.events} & new_kinds
    # Phần nhật ký của payload và điểm tin cậy không có sự kiện phân phối; chỉ khối revision (ghi nhận) mới có
    payload = build_payload(res, "X")
    payload.pop("revision")
    text = str(payload)
    assert "BC failed" not in text and "'SOW'" not in text and "'LPSY'" not in text


def test_phases_unchanged_by_distribution_config(dist: pd.DataFrame) -> None:
    a = analyze(dist)
    b = analyze(dist, Config(distribution=DistributionConfig(bc_min_rise=9.0, sow_min_vol_ratio=9.0)))
    pd.testing.assert_frame_equal(a.phases.series, b.phases.series)
    assert [e.event_id for e in a.events] == [e.event_id for e in b.events]
    assert len(b.distribution) < len(a.distribution)


def test_since_filters_distribution(dist: pd.DataFrame) -> None:
    res = analyze(dist)
    cut = res.since(dist.index[150])
    assert all(e.date >= dist.index[150] for e in cut.distribution)
    assert any(e.kind == EventType.SOW for e in cut.distribution) and not any(e.kind == EventType.BC for e in cut.distribution)
    assert not cut.distribution_frame().empty
