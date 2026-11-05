"""H6: tách UT / UTAD, xác nhận bằng yếu kém (docs/h6-preregistration.md)."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from wyckoff.config import Config, UTADConfig
from wyckoff.detectors.models import EventStatus, EventType
from wyckoff.pipeline import analyze
from wyckoff.synthetic import make_wyckoff_accumulation

BASE = Config()
H6 = replace(BASE, utad=replace(BASE.utad, mode="ut_utad"))
U1, U2 = 166, 168          # đỉnh nhịp dao động trong range (resistance 74, giữa range 69)
WEAK = 172                 # close đầu tiên < 69 sau U1 (68,1)
UPTHRUSTS = (EventType.UT, EventType.UTAD)


def _set(df: pd.DataFrame, i: int, o: float, h: float, lo: float, c: float) -> None:
    df.iloc[i, df.columns.get_indexer(["open", "high", "low", "close"])] = [o, h, lo, c]


def _df(*bars: int) -> pd.DataFrame:
    """Upthrust: vượt lên 75,5 rồi đóng cửa 73,0 (close_pos 0,17, dưới resistance)."""
    df = make_wyckoff_accumulation()
    for i in bars:
        _set(df, i, 73.0, 75.5, 72.5, 73.0)
    return df


def _ups(res, candidates: bool = False):
    return [e for e in (res.candidates if candidates else res.events) if e.kind in UPTHRUSTS]


def test_default_mode_is_v2_unchanged() -> None:
    assert UTADConfig().mode == "v2"
    res = analyze(_df(U1))
    (u,) = _ups(res)
    assert u.kind == EventType.UTAD and u.idx == u.confirmed_idx == U1
    assert res.phases.series["phase"].iloc[U1] == "invalid"


def test_first_upthrust_is_ut_confirmed_by_weakness() -> None:
    res = analyze(_df(U1), H6)
    (u,) = _ups(res)
    assert u.kind == EventType.UT and u.idx == U1 and u.confirmed_idx == WEAK
    assert u.details["upthrust_no"] == 1 and u.details["weakness_date"] == f"{res.df.index[WEAK]:%Y-%m-%d}"
    assert [h.status for h in u.history] == [EventStatus.CANDIDATE, EventStatus.CONFIRMED]   # quay lại ngay phiên vượt
    ph = res.phases.series["phase"]
    assert ph.iloc[WEAK - 1] != "invalid" and ph.iloc[WEAK] == "invalid"
    assert u.event_id.startswith(f"UT-{res.df.index[U1]:%Y%m%d}")


def test_second_upthrust_is_utad() -> None:
    res = analyze(_df(U1, U2), H6)
    kinds = sorted((e.idx, e.kind, e.details["upthrust_no"]) for e in _ups(res) + _ups(res, True) if e.idx < 190)
    assert kinds == [(U1, EventType.UT, 1), (U2, EventType.UTAD, 2)]
    # phiên SOS (191) cũng vượt resistance nhưng không quay lại: chỉ là candidate INVALIDATED
    sos_bar = next(e for e in _ups(res, True) if e.idx == 191)
    assert sos_bar.status == EventStatus.INVALIDATED and "không đóng cửa lại" in sos_bar.history[-1].reason


def test_breakout_above_upthrust_high_invalidates() -> None:
    df = _df(U1)
    for k in range(U1 + 1, U1 + 4):
        _set(df, k, 75.0, 76.5, 74.8, 76.0)       # close 76 > đỉnh upthrust 75,5
    res = analyze(df, H6)
    assert not _ups(res)
    c = next(e for e in _ups(res, True) if e.idx == U1)
    assert c.status == EventStatus.INVALIDATED and c.history[-1].idx == U1 + 1
    assert "breakout thật" in c.history[-1].reason
    # v2: vẫn UTAD và vô hiệu cấu trúc ngay
    assert [e.kind for e in _ups(analyze(df))] == [EventType.UTAD]


def test_no_weakness_expires() -> None:
    df = _df(U1)
    for k in range(U1 + 1, U1 + 17):
        _set(df, k, 72.5, 73.5, 71.5, 72.5)       # đi ngang trên giữa range, dưới đỉnh upthrust
    res = analyze(df, H6)
    c = next(e for e in _ups(res, True) if e.idx == U1)
    assert c.status == EventStatus.INVALIDATED and c.history[-1].idx == U1 + 15
    assert "15 phiên" in c.history[-1].reason


def test_open_candidate_when_data_ends() -> None:
    res = analyze(_df(U1).iloc[:U1 + 3], H6)
    (c,) = _ups(res, True)
    assert c.status == EventStatus.CANDIDATE and not _ups(res)


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        analyze(_df(U1), replace(BASE, utad=replace(BASE.utad, mode="xyz")))


@pytest.mark.parametrize("cutoff", [U1 + 1, U2 + 1, WEAK, WEAK + 1, WEAK + 20])
def test_ut_utad_no_lookahead(cutoff: int) -> None:
    for df in (_df(U1), _df(U1, U2)):
        full, part = analyze(df, H6), analyze(df.iloc[:cutoff], H6)
        t = cutoff - 1
        key = lambda evts: [(e.kind, e.idx, e.confirmed_idx) for e in evts]  # noqa: E731
        assert key(part.events) == key([e for e in full.events if e.confirmed_idx <= t])
        want = {e.event_id: e.status_at(t) for e in full.events + full.candidates if e.status_at(t) is not None}
        assert {e.event_id: e.status for e in part.events + part.candidates} == want
        pd.testing.assert_series_equal(part.phases.series["phase"], full.phases.series["phase"].iloc[:cutoff])
