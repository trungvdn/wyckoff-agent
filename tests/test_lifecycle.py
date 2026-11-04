"""Vòng đời event: ID ổn định, quan hệ, trạng thái, không nhìn trước."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from wyckoff.config import Config
from wyckoff.detectors.lifecycle import base_event_id
from wyckoff.detectors.models import EventStatus, EventType
from wyckoff.pipeline import AnalysisResult, analyze
from wyckoff.synthetic import SC_IDX, SOS_IDX, SPRING_CONFIRM_IDX, SPRING_IDX, make_wyckoff_accumulation

BASE = Config()
NO_RECOVERY = replace(BASE, spring=replace(BASE.spring, max_recovery_bars=1))   # phiên thủng không tự hồi -> Spring thất bại
SHAKEOUT = replace(BASE, spring=replace(BASE.spring, max_vol_ratio=0.5))       # Spring 0,6x -> shakeout, chờ Test
ZONE_SC = replace(BASE, sc=replace(BASE.sc, min_close_pos=0.7))                # SC xác nhận dạng vùng ở phiên sau
CONFIGS = {"base": BASE, "no_recovery": NO_RECOVERY, "shakeout": SHAKEOUT, "zone_sc": ZONE_SC}


def _by_kind(res: AnalysisResult, kind: EventType, candidates: bool = False):
    return [e for e in (res.candidates if candidates else res.events) if e.kind == kind]


def test_behavior_unchanged_events_are_confirmed() -> None:
    res = analyze(make_wyckoff_accumulation())
    assert all(e.is_confirmed for e in res.events)
    assert all(e.history and e.history[0].idx <= e.confirmed_idx for e in res.events)
    assert all(not e.is_confirmed and e.confirmed_idx == -1 for e in res.candidates)


def test_ids_unique_and_formatted() -> None:
    res = analyze(make_wyckoff_accumulation())
    ids = [e.event_id for e in res.events + res.candidates]
    assert len(ids) == len(set(ids)) and all(ids)
    sc = _by_kind(res, EventType.SC)[0]
    assert sc.event_id == f"SC-{sc.date:%Y%m%d}"
    spring = _by_kind(res, EventType.SPRING)[0]
    rng = next(r for r in res.ranges if r.range_id == spring.range_id)
    assert spring.event_id == f"SPRING-{spring.date:%Y%m%d}-TR{rng.start_date:%Y%m%d}"


def test_ids_stable_when_data_starts_later() -> None:
    """range_id đổi theo dữ liệu, ID thì không: chạy lại từ phiên muộn hơn cho cùng ID."""
    full = make_wyckoff_accumulation()
    a, b = analyze(full), analyze(full.iloc[5:])
    key = lambda r: {(e.kind, e.date): e.event_id for e in r.events}  # noqa: E731
    ka, kb = key(a), key(b)
    common = ka.keys() & kb.keys()
    assert {EventType.SC, EventType.SPRING, EventType.SOS} <= {k for k, _ in common}
    assert all(ka[k] == kb[k] for k in common)


def test_relations() -> None:
    res = analyze(make_wyckoff_accumulation())
    sc = _by_kind(res, EventType.SC)[0]
    for st in _by_kind(res, EventType.ST):
        assert st.test_of_event_id == sc.event_id and sc.event_id in st.related_event_ids
        assert st.event_id in sc.related_event_ids
    ar = _by_kind(res, EventType.AR)[0]
    assert ar.related_event_ids == (sc.event_id,) and ar.test_of_event_id is None

    sh = analyze(make_wyckoff_accumulation(), SHAKEOUT)
    for t in _by_kind(sh, EventType.TEST):
        sp = next(e for e in sh.events if e.event_id == t.test_of_event_id)
        assert sp.kind == EventType.SPRING and t.event_id in sp.related_event_ids


def test_spring_history_low_volume() -> None:
    res = analyze(make_wyckoff_accumulation())
    sp = _by_kind(res, EventType.SPRING)[0]
    assert [(h.status, h.idx) for h in sp.history][:2] == [
        (EventStatus.DETECTED, SPRING_IDX), (EventStatus.CONFIRMED, SPRING_CONFIRM_IDX)]
    assert sp.status_at(SPRING_IDX - 1) is None
    assert sp.status_at(SPRING_IDX) == EventStatus.DETECTED
    assert sp.status_at(SPRING_CONFIRM_IDX) == EventStatus.CONFIRMED


def test_failed_spring_is_candidate_not_event() -> None:
    res = analyze(make_wyckoff_accumulation(), NO_RECOVERY)
    assert not _by_kind(res, EventType.SPRING)
    c = _by_kind(res, EventType.SPRING, candidates=True)[0]
    assert c.idx == SPRING_IDX and c.status == EventStatus.INVALIDATED
    assert "1 phiên" in c.history[-1].reason


def test_shakeout_without_test_expires() -> None:
    res = analyze(make_wyckoff_accumulation(), SHAKEOUT)
    c = next(e for e in _by_kind(res, EventType.SPRING, candidates=True) if e.idx == SPRING_IDX)
    assert [h.status for h in c.history] == [EventStatus.DETECTED, EventStatus.CANDIDATE, EventStatus.INVALIDATED]
    assert c.history[1].idx == SPRING_CONFIRM_IDX
    # chạy trên dữ liệu cắt ngay sau phiên hồi: candidate còn mở, chưa bị đóng
    part = analyze(make_wyckoff_accumulation().iloc[:SPRING_CONFIRM_IDX + 3], SHAKEOUT)
    pc = next(e for e in part.candidates if e.event_id == c.event_id)
    assert pc.status == EventStatus.CANDIDATE


def test_zone_sc_detected_then_confirmed() -> None:
    res = analyze(make_wyckoff_accumulation(), ZONE_SC)
    sc = _by_kind(res, EventType.SC)[0]
    assert sc.idx == SC_IDX and sc.confirmed_idx > SC_IDX
    assert [h.status for h in sc.history][:2] == [EventStatus.DETECTED, EventStatus.CONFIRMED]


def test_sos_invalidated_when_back_below_range_mid() -> None:
    df = make_wyckoff_accumulation()
    df.loc[df.index[SOS_IDX + 10]:, ["open", "high", "low", "close"]] = [68.0, 69.0, 67.0, 68.0]  # quay về giữa range (69)
    res = analyze(df)
    sos = _by_kind(res, EventType.SOS)[0]
    inv = sos.invalidated
    assert inv is not None and inv.idx == SOS_IDX + 10 and "giữa range" in inv.reason
    assert sos.status_at(SOS_IDX + 9) == EventStatus.CONFIRMED


def test_frame_has_lifecycle_columns() -> None:
    res = analyze(make_wyckoff_accumulation(), NO_RECOVERY)
    f = res.events_frame(include_candidates=True)
    assert {"event_id", "status", "history", "related_event_ids", "structure_id", "invalidated_date"} <= set(f.columns)
    assert f["structure_id"].notna().any()
    assert (f["status"] == "INVALIDATED").any()


def test_base_event_id_uses_dates_only() -> None:
    res = analyze(make_wyckoff_accumulation())
    rngs = {r.range_id: r for r in res.ranges}
    e = _by_kind(res, EventType.SOS)[0]
    assert base_event_id(replace(e, range_id=e.range_id), rngs) == e.event_id


@pytest.mark.parametrize("name", list(CONFIGS))
@pytest.mark.parametrize("cutoff", [SC_IDX + 1, SC_IDX + 30, SPRING_IDX + 1, SPRING_CONFIRM_IDX + 1,
                                    SPRING_CONFIRM_IDX + 8, SOS_IDX + 1, SOS_IDX + 15])
def test_lifecycle_no_lookahead(name: str, cutoff: int) -> None:
    """Trạng thái tại phiên t trên dữ liệu đầy đủ == trạng thái cuối khi chỉ có dữ liệu đến t."""
    cfg = CONFIGS[name]
    df = make_wyckoff_accumulation()
    full, part = analyze(df, cfg), analyze(df.iloc[:cutoff], cfg)
    t = cutoff - 1
    want = {e.event_id: e.status_at(t) for e in full.events + full.candidates if e.status_at(t) is not None}
    got = {e.event_id: e.status for e in part.events + part.candidates}
    assert got == want
    assert [(e.event_id, s) for e, s in part.snapshot()] == [(e.event_id, s) for e, s in full.snapshot(t)]


def test_snapshot_by_date() -> None:
    res = analyze(make_wyckoff_accumulation())
    d = res.df.index[SPRING_IDX]
    snap = dict((e.kind, s) for e, s in res.snapshot(d))
    assert snap[EventType.SPRING] == EventStatus.DETECTED and snap[EventType.SC] == EventStatus.CONFIRMED
    assert all(s is not None for _, s in res.snapshot(pd.Timestamp(d)))
